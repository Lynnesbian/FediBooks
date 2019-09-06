from flask import Flask, render_template, session, request, redirect, url_for, send_file
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

scopes = ['write:statuses', 'write:accounts', 'read:accounts', 'read:notifications', 'read:statuses', 'push']

@app.route("/")
def home():
	if 'user_id' in session:
		session['step'] = 1
		c = mysql.connection.cursor()
		c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s", (session['user_id'],))
		bot_count = c.fetchone()[0]
		active_count = None
		bots = {}
		bot_users = None

		if bot_count > 0:
			c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s AND enabled = TRUE", (session['user_id'],))
			active_count = c.fetchone()[0]
			dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
			dc.execute("SELECT `handle`, `enabled` FROM `bots` WHERE user_id = %s", (session['user_id'],))
			bots = dc.fetchall()
			dc.close()
			bot_users = {}

			for bot in bots:
				# multiple SELECTS is slow, maybe SELECT all at once and filter with python?
				c.execute("SELECT COUNT(*) FROM `bot_learned_accounts` WHERE bot_id = %s", (bot['handle'],))
				bot_users[bot['handle']] = c.fetchone()[0]

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
	error = None
	if 'error' in session:
		error = session.pop('error')
	return render_template("login.html", signup = False, error = error)

@app.route("/signup")
def show_signup_page():
	error = None
	if 'error' in session:
		error = session.pop('error')
	return render_template("login.html", signup = True, error = error)

@app.route("/settings")
def settings():
	return render_template("coming_soon.html")
	dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
	dc.execute("SELECT * FROM `users` WHERE id = %s", (session['user_id'],))
	user = dc.fetchone()
	dc.close()
	return render_template("settings.html", user = user)

@app.route("/bot/edit/<id>")
def bot_edit(id):
	return render_template("coming_soon.html")

@app.route("/bot/delete/<id>", methods=['GET', 'POST'])
def bot_delete(id):
	if bot_check(id):
		if request.method == 'GET':
			instance = id.split("@")[2]
			return render_template("bot_delete.html", instance = instance)
		else:
			# delete bot by deleting its credentials
			# FK constraint will delete bot
			c = mysql.connection.cursor()
			c.execute("SELECT `credentials_id` FROM `bots` WHERE `handle` = %s", (id,))
			credentials_id = c.fetchone()[0]
			c.execute("DELETE FROM `credentials` WHERE `id` = %s", (credentials_id,))
			c.close()
			mysql.connection.commit()

			return redirect(url_for("home"), 303)

@app.route("/bot/toggle/<id>")
def bot_toggle(id):
	if bot_check(id):
		c = mysql.connection.cursor()
		c.execute("UPDATE `bots` SET `enabled` = NOT `enabled` WHERE `handle` = %s", (id,))
		mysql.connection.commit()
		c.close()
		return redirect(url_for("home"), 303)

@app.route("/bot/chat/<id>")
def bot_chat(id):
	return render_template("coming_soon.html")

@app.route("/bot/blacklist/<id>")
def bot_blacklist(id):
	return render_template("coming_soon.html")

@app.route("/bot/accounts/<id>")
def bot_accounts(id):
	if bot_check(id):
		session['bot'] = id
		c = mysql.connection.cursor()
		c.execute("SELECT COUNT(*) FROM `bot_learned_accounts` WHERE `bot_id` = %s", (id,))
		user_count = c.fetchone()[0]
		users = {}
		post_count = {}

		if user_count > 0:
			dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
			dc.execute("SELECT `fedi_id`, `enabled` FROM `bot_learned_accounts` WHERE `bot_id` = %s", (id,))
			users = dc.fetchall()
			dc.close()

			post_count = {}
			for user in users:
				c.execute("SELECT COUNT(*) FROM `posts` WHERE `fedi_id` = %s", (user['fedi_id'],))
				post_count[user['fedi_id']] = c.fetchone()[0]

		c.close()

		return render_template("bot_accounts.html", users = users, post_count = post_count)

@app.route("/bot/accounts/add", methods = ['GET', 'POST'])
def bot_accounts_add():
	error = None
	if request.method == 'POST':
		if session['step'] == 1:
			if request.form['account'] == session['bot']:
				error = "Bots cannot learn from themselves."
				return render_template("bot_accounts_add.html", error = error)

			# look up user
			handle_list = request.form['account'].split('@')
			username = handle_list[1]
			instance = handle_list[2]

			# 1. download host-meta to find webfinger URL
			r = requests.get("https://{}/.well-known/host-meta".format(instance), timeout=10)
			# 2. use webfinger to find user's info page
			#TODO: use more reliable method
			uri = re.search(r'template="([^"]+)"', r.text).group(1)
			uri = uri.format(uri = "{}@{}".format(username, instance))
			r = requests.get(uri, headers={"Accept": "application/json"}, timeout=10)
			j = r.json()
			found = False
			for link in j['links']:
				if link['rel'] == 'self':
					#this is a link formatted like "https://instan.ce/users/username", which is what we need
					uri = link['href']
					found = True
					break
			if not found:
				error = "Couldn't find a valid ActivityPub outbox URL."
				return render_template("bot_accounts_add.html", error = error)

			# 3. format as outbox URL and check to make sure it works
			outbox = "{}/outbox?page=true".format(uri)
			r = requests.get(uri, headers={"Accept": "application/json"}, timeout=10)
			if r.status_code == 200:
				# success!!
				c = mysql.connection.cursor()
				c.execute("INSERT INTO `fedi_accounts` (`handle`, `outbox`) VALUES (%s, %s)", (request.form['account'], outbox))
				c.execute("INSERT INTO `bot_learned_accounts` (`bot_id`, `fedi_id`) VALUES (%s, %s)", (session['bot'], request.form['account']))
				c.close()
				mysql.connection.commit()
				return redirect("/bot/accounts/{}".format(session['bot']), 303)
			else:
				error = "Couldn't access ActivityPub outbox. {} may require authenticated fetches, which FediBooks doesn't support yet."
				return render_template("bot_accounts_add.html", error = error)

	return render_template("bot_accounts_add.html", error = error)

@app.route("/bot/accounts/toggle/<id>")
def bot_accounts_toggle(id):
	c = mysql.connection.cursor()
	c.execute("UPDATE `bot_learned_accounts` SET `enabled` = NOT `enabled` WHERE `fedi_id` = %s AND `bot_id` = %s", (id, session['bot']))
	mysql.connection.commit()
	c.close()
	return redirect("/bot/accounts/{}".format(session['bot']), 303)

@app.route("/bot/accounts/delete/<id>", methods=['GET', 'POST'])
def bot_accounts_delete(id):
	if request.method == 'GET':
		instance = id.split("@")[2]
		return render_template("bot_accounts_delete.html", user = id, instance = instance)
	else:
		#NOTE: when user credential support is added, we'll need to delete the creds too
		c = mysql.connection.cursor()
		c.execute("DELETE FROM `bot_learned_accounts` WHERE `fedi_id` = %s AND bot_id = %s", (id, session['bot']))
		# check to see if anyone else is learning from this account
		c.execute("SELECT COUNT(*) FROM `bot_learned_accounts` WHERE `fedi_id` = %s", (id,))
		if c.fetchone()[0] == 0:
			# nobody else learns from this account, remove it from the db
			c.execute("DELETE FROM `fedi_accounts` WHERE `handle` = %s", (id,))
		c.close()
		mysql.connection.commit()

		return redirect("/bot/accounts/{}".format(session['bot']), 303)

@app.route("/bot/create/", methods=['GET', 'POST'])
def bot_create():
	error = None
	if request.method == 'POST':
		if session['step'] == 1:
			# strip leading https://, if provided
			session['instance'] = re.match(r"^(?:https?:\/\/)?(.*)", request.form['instance']).group(1)
			
			# check for mastodon/pleroma
			r = requests.get("https://{}/api/v1/instance".format(session['instance']), timeout=10)
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
				session['error'] = "Unsupported instance type. Misskey support is planned."

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
				return redirect(url_for("bot_create"), 303)

	else:
		if session['step'] == 4:
			try:
				# test authentication
				client = Mastodon(client_id=session['client_id'], client_secret=session['client_secret'], api_base_url=session['instance'])
				session['secret'] = client.log_in(code = session['code'], scopes=scopes, redirect_uri='{}/do/authenticate_bot'.format(cfg['base_uri']))
				username = client.account_verify_credentials()['username']
				handle = "@{}@{}".format(username, session['instance'])
			except:
				# authentication error occurred
				error = "Authentication failed."
				session['step'] = 3
				return render_template("bot_create.html", error = error)

			# authentication success!!
			c = mysql.connection.cursor()
			c.execute("INSERT INTO `credentials` (client_id, client_secret, secret) VALUES (%s, %s, %s)", (session['client_id'], session['client_secret'], session['code']))
			credentials_id = c.lastrowid
			mysql.connection.commit()

			# get webpush url
			privated, publicd = client.push_subscription_generate_keys()
			private = privated['privkey']
			public = publicd['pubkey']
			secret = privated['auth']
			# replace fedibooks.com with cfg['base_uri'] on release
			client.push_subscription_set("https://fedibooks.com/push/{}".format(handle), publicd, mention_events = True)

			c.execute("INSERT INTO `bots` (handle, user_id, credentials_id, push_public_key, push_private_key, push_secret) VALUES (%s, %s, %s, %s, %s, %s)", (handle, session['user_id'], credentials_id, public, private, secret))
			mysql.connection.commit()
			c.close()

			# clean up unneeded variables
			del session['code']
			del session['instance']
			del session['instance_type']
			del session['client_id']
			del session['client_secret']

	if 'error' in session:
		error = session.pop('error')
	return render_template("bot_create.html", error = error)

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
		session['error'] = "Invalid email address."
		return redirect(url_for("show_signup_page"), 303)

	if len(request.form['password']) < 8:
		session['error'] = "Password too short."
		return redirect(url_for("show_signup_page"), 303)

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
	if data == None:
		session['error'] = "Incorrect login information."
		return redirect(url_for("show_login_page"), 303)
	
	if bcrypt.checkpw(pw_hashed, data['password']):
		session['user_id'] = data['id']
		return redirect(url_for("home"))

	else:
		session['error'] = "Incorrect login information."
		return redirect(url_for("show_login_page"), 303)

@app.route("/img/bot_generic.png")
def img_bot_generic():
	return send_file("static/bot_generic.png", mimetype="image/png")

def bot_check(bot):
	# check to ensure bot is owned by user
	c = mysql.connection.cursor()
	c.execute("SELECT COUNT(*) FROM `bots` WHERE `handle` = %s AND `user_id` = %s", (bot, session['user_id']))
	return c.fetchone()[0] == 1
