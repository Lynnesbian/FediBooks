from flask import Flask, render_template, session, request, redirect, url_for
from flask_mysqldb import MySQL
from mastodon import Mastodon
import requests
import MySQLdb
import bcrypt
import json, hashlib, re

cfg = json.load(open("config.json"))

app = Flask(__name__)
app.secret_key = cfg['secret_key']

app.config['MYSQL_HOST'] = cfg['db_host']
app.config['MYSQL_DB'] = cfg['db_name']
app.config['MYSQL_USER'] = cfg['db_user']
app.config['MYSQL_PASSWORD'] = cfg['db_pass']

mysql = MySQL(app)

scopes = ['write:statuses', 'write:accounts', 'read:accounts', 'read:notifications', 'read:statuses']

@app.route("/")
def home():
	if 'user_id' in session:
		session['step'] = 1
		c = mysql.connection.cursor()
		c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s", (session['user_id'],))
		bot_count = c.fetchone()[0]
		active_count = None
		bots = None
		bot_users = None

		if bot_count > 0:
			c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s AND enabled = TRUE", (session['user_id'],))
			active_count = c.fetchone()[0]
			dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
			dc.execute("SELECT * FROM `bots` WHERE user_id = %s", (session['user_id'],))
			bots = dc.fetchall()
			dc.close()
			bot_users = {}

			for bot in bots:
				# multiple SELECTS is slow, maybe SELECT all at once and filter with python?
				c.execute("SELECT COUNT(*) FROM `bot_learned_accounts` WHERE bot_id = %s", (bot['id'],))
				bot_users[bot['id']] = c.fetchone()[0]

		c.close()
		return render_template("home.html", bot_count = bot_count, active_count = active_count, bots = bots, bot_users = bot_users)
	else:
		return render_template("front_page.html")

@app.route("/welcome")
def welcome():
	return render_template("welcome.html")

@app.route("/about")
def about():
	return render_template("about.html")

@app.route("/login")
def show_login_page():
	return render_template("login.html", signup = False)

@app.route("/signup")
def show_signup_page(error = None):
	#TODO: display error if any
	return render_template("login.html", signup = True)

@app.route("/settings")
def settings():
	return render_template("settings.html")

@app.route("/bot/edit/<id>")
def bot_edit(id):
	return render_template("bot_edit.html")

@app.route("/bot/delete/<id>")
def bot_delete(id):
	return render_template("bot_delete.html")

@app.route("/bot/accounts/<id>")
def bot_accounts(id):
	return render_template("bot_accounts.html")

@app.route("/bot/accounts/add")
def bot_accounts_add():
	return render_template("bot_accounts_add.html")

@app.route("/bot/create/", methods=['GET', 'POST'])
def bot_create():
	#TODO: error handling
	if request.method == 'POST':
		if session['step'] == 1:
			# strip leading https://, if provided
			session['instance'] = re.match(r"^(?:https?:\/\/)?(.*)", request.form['instance']).group(1)
			
			# check for mastodon/pleroma
			r = requests.get("https://{}/api/v1/instance".format(session['instance']))
			if r.status_code == 200:
				j = r.json()
				if "Pleroma" in j['version']:
					session['instance_type'] = "Pleroma"
					session['step'] += 1
				else:
					if 'is_pro' in j['contact_account']:
						# gab instance
						session['error'] = "Eat shit and die, fascist scum."
					else:
						session['instance_type'] = "Mastodon"
						session['step'] += 1

			else:
				# not a masto/pleroma instance
				# misskey is currently unsupported
				# all other instance types are also unsupported
				# return an error message
				#TODO: misskey
				session['error'] = "Unsupported instance type."

		elif session['step'] == 2:
			# nothing needs to be done here, this step just informs the user that their instance type is supported
			session['step'] += 1

		elif session['step'] == 3:
			# authenticate with the given instance and obtain credentials
			if session['instance_type'] in ['Mastodon', 'Pleroma']:
				redirect_uri = '{}/do/authenticate_bot'.format(cfg['base_uri'])

				session['client_id'], session['client_secret'] = Mastodon.create_app(
					"FediBooks",
					api_base_url="https://{}".format(session['instance']),
					scopes=scopes,
					redirect_uris=[redirect_uri],
					website=cfg['base_uri']
				)

				client = Mastodon(
					client_id=session['client_id'],
					client_secret=session['client_secret'],
					api_base_url="https://{}".format(session['instance'])
				)

				url = client.auth_request_url(client_id=session['client_id'], redirect_uris=redirect_uri, scopes=scopes)
				return redirect(url, code=303)

			elif session['instance_type'] == 'Misskey':
				# todo
				pass

			else:
				# the user clicked next on step 2 while having an unsupported instance type
				# take them back to step 1
				del session['instance']
				del session['instance_type']
				session['step'] = 1
				return bot_create()

		elif session['step'] == 4:
			try:
				# test authentication
				client = Mastodon(client_id=session['client_id'], client_secret=session['client_secret'], api_base_url=session['instance'])
				session['secret'] = client.log_in(code = session['code'], scopes=scopes, redirect_uri='{}/do/authenticate_bot'.format(cfg['base_uri']))
				username = client.account_verify_credentials()['username']
				handle = "@{}@{}".format(username, session['instance'])
			except:
				# authentication error occurred
				return render_template("bot_oauth_error.html")

			# authentication success!!
			c = mysql.connection.cursor()
			c.execute("INSERT INTO `credentials` (client_id, client_secret, secret) VALUES (%s, %s, %s)", (session['client_id'], session['client_secret'], session['code']))
			credentials_id = c.lastrowid
			mysql.connection.commit()

			bot_id = hashlib.sha256(handle.encode('utf-8')).digest()
			c.execute("INSERT INTO `bots` (id, user_id, credentials_id, handle) VALUES (%s, %s, %s, %s)", (bot_id, session['user_id'], credentials_id, handle))
			mysql.connection.commit()

			c.close()

			# clean up unneeded variables
			del session['code']
			del session['instance']
			del session['instance_type']
			del session['client_id']
			del session['client_secret']

	return render_template("bot_create.html")

@app.route("/bot/create/back")
def bot_create_back():
	session['step'] -= 1
	return redirect(url_for("bot_create"), 303)

@app.route("/do/authenticate_bot")
def do_authenticate_bot():
	session['code'] = request.args.get('code')
	session['step'] = 4
	return redirect(url_for("bot_create"), 303)

@app.route("/do/signup", methods=['POST'])
def do_signup():
	# email validation is basically impossible without actually sending an email to the address
	# because fedibooks can't send email yet, we'll just check if the string contains an @ ;)
	if "@" not in request.form['email']:
		return show_signup_page("Invalid email address.")

	if len(request.form['password']) < 8:
		return show_signup_page("Password too short.")

	pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest()
	pw = bcrypt.hashpw(pw_hashed, bcrypt.gensalt(12))

	# try to sign up
	c = mysql.connection.cursor()
	c.execute("INSERT INTO `users` (email, password) VALUES (%s, %s)", (request.form['email'], pw))
	user_id = c.lastrowid
	mysql.connection.commit()
	c.close()

	# success!
	session['user_id'] = user_id
	return redirect(url_for('home'))

@app.route("/do/signout")
def do_signout():
	session.clear()
	return redirect(url_for("home"))

@app.route("/do/login", methods=['POST'])
def do_login():
	pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest()
	c = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
	c.execute("SELECT * FROM users WHERE email = %s", (request.form['email'],))
	data = c.fetchone()
	c.close()
	if bcrypt.checkpw(pw_hashed, data['password']):
		session['user_id'] = data['id']
		return redirect(url_for("home"))

	else:
		return "invalid login"
