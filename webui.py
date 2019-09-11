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

@app.before_request
def login_check():
	if request.path not in ['/', '/about', '/welcome', '/login', '/signup', '/do/login', '/do/signup', '/static/style.css'] and not request.path.startswith("/push"):
		# page requires authentication
		if 'user_id' not in session:
			return redirect(url_for('home'))

@app.route("/")
def home():
	if 'user_id' in session:
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
	return render_template("login.html", signup = False, error = session.pop('error', None))

@app.route("/signup")
def show_signup_page():
	return render_template("login.html", signup = True, error = session.pop('error', None))

@app.route("/settings", methods=['GET', 'POST'])
def settings():
	if request.method == 'GET':
		dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
		dc.execute("SELECT * FROM `users` WHERE id = %s", (session['user_id'],))
		user = dc.fetchone()
		dc.close()
		return render_template("settings.html", user = user, error = session.pop('error', None), success = session.pop('success', None))

	else:
		# update settings
		c = mysql.connection.cursor()

		c.execute("SELECT COUNT(*) FROM users WHERE email = %s AND id != %s", (request.form['email'], session['user_id']))
		if c.fetchone()[0] > 0:
			session['error'] = "Email address already in use."
			return redirect(url_for("settings"), 303)

		for setting in [request.form['fetch-error'], request.form['submit-error'], request.form['reply-error'], request.form['generation-error']]:
			if setting not in ['once', 'always', 'never']:
				session['error'] = 'Invalid option "{}".'.format(setting)
				return redirect(url_for('settings'), 303)

		if request.form['password'] != '':
			# user is updating their password
			if len(request.form['password']) < 8:
				session['error'] = "Password too short."
				return redirect(url_for("settings"), 303)

			pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest()
			pw = bcrypt.hashpw(pw_hashed, bcrypt.gensalt(12))
			c.execute("UPDATE users SET password = %s WHERE id = %s", (pw, session['user_id']))

		# don't require email verification again if the new email address is the same as the old one
		c.execute("SELECT email_verified FROM users WHERE id = %s", (session['user_id'],))
		if c.fetchone()[0]:
			c.execute("SELECT email FROM users WHERE id = %s", (session['user_id'],))
			previous_email = c.fetchone()[0]

			email_verified = (previous_email == request.form['email'])
		else:
			email_verified = False
		
		try:
			c.execute("UPDATE users SET email = %s, email_verified = %s, `fetch` = %s, submit = %s, generation = %s, reply = %s WHERE id = %s", (
				request.form['email'],
				email_verified,
				request.form['fetch-error'],
				request.form['submit-error'],
				request.form['generation-error'],
				request.form['reply-error'],
				session['user_id']
			))
			c.close()
			mysql.connection.commit()
		except:
			session['error'] = "Encountered an error while updating the database."
			return redirect(url_for('settings'), 303)

		session['success'] = True
		return redirect(url_for('settings'), 303)

@app.route("/bot/edit/<id>", methods = ['GET', 'POST'])
def bot_edit(id):
	if request.method == "GET":
		dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
		dc.execute("SELECT * FROM bots WHERE handle = %s", (id,))
		return render_template("bot_edit.html", bot = dc.fetchone(), error = session.pop('error', None), success = session.pop('success', None))
	else:
		# update stored settings
		replies_enabled = 'replies' in request.form
		learn_from_cw = 'cw-learning' in request.form

		if request.form['fake-mention-style'] not in ['full', 'brief']:
			session['error'] = "Invalid setting for fake mention style."
			return redirect("/bot/edit/{}".format(id), 303)

		if request.form['fake-mentions'] not in ['always', 'middle', 'never']:
			session['error'] = "Invalid setting for fake mentions."
			return redirect("/bot/edit/{}".format(id), 303)

		if request.form['privacy'] not in ['public', 'unlisted', 'private']:
			session['error'] = "Invalid setting for post privacy."
			return redirect("/bot/edit/{}".format(id), 303)
		
		if int(request.form['length']) < 100 or int(request.form['length']) > 5000:
			session['error'] = "Invalid setting for maximum post length."
			return redirect("/bot/edit/{}".format(id), 303)

		if int(request.form['freq']) < 15 or int(request.form['freq']) > 240 or int(request.form['freq']) % 5:
			session['error'] = "Invalid setting for post frequency."
			return redirect("/bot/edit/{}".format(id), 303)

		if len(request.form['cw']) > 128:
			session['error'] = "Content warning cannot exceed 128 characters."
			return redirect("/bot/edit/{}".format(id), 303)

		c = mysql.connection.cursor()
		try:
			c.execute("UPDATE bots SET replies_enabled = %s, post_frequency = %s, content_warning = %s, length = %s, fake_mentions = %s, fake_mentions_full = %s, post_privacy = %s, learn_from_cw = %s WHERE handle = %s", (
				replies_enabled,
				request.form['freq'],
				request.form['cw'] if request.form['cw'] != "" else None,
				request.form['length'],
				request.form['fake-mentions'],
				request.form['fake-mention-style'] == 'full',
				request.form['privacy'],
				learn_from_cw,
				id
			))
			mysql.connection.commit()
			c.close()
		except:
			session['error'] = "Couldn't save your settings."
			return redirect("/bot/edit/{}".format(id), 303)

		session['success'] = True
		return redirect("/bot/edit/{}".format(id), 303)

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
	if request.method == 'POST':
		if session['step'] == 1:
			if request.form['account'] == session['bot']:
				error = "Bots cannot learn from themselves."
				return render_template("bot_accounts_add.html", error = error)

			# look up user
			handle_list = request.form['account'].split('@')
			if len(handle_list) != 3:
				# not formatted correctly
				error = "Incorrectly formatted handle."
				return render_template("bot_accounts_add.html", error = error)

			username = handle_list[1]
			instance = handle_list[2]

			# gab check
			try:
				r = requests.get("https://{}/api/v1/instance".format(instance), timeout=10)
			except requests.exceptions.ConnectionError:
				error = "Couldn't connect to {}.".format(instance)
				return render_template("bot_accounts_add.html", error = error)
			except:
				error = "An unknown error occurred."
				return render_template("bot_accounts_add.html", error = error)

			if r.status_code == 200:
				j = r.json()
				if 'is_pro' in j['contact_account']:
					# gab instance
					error = "Gab instances are not supported."
					return render_template("bot_accounts_add.html", error = error)

			# 1. download host-meta to find webfinger URL
			r = requests.get("https://{}/.well-known/host-meta".format(instance), timeout=10)
			if r.status_code != 200:
				error = "Couldn't get host-meta."
				return render_template("bot_accounts_add.html", error = error)

			# 2. use webfinger to find user's info page
			#TODO: use more reliable method
			try:
				uri = re.search(r'template="([^"]+)"', r.text).group(1)
				uri = uri.format(uri = "{}@{}".format(username, instance))
			except:
				error = "Couldn't find WebFinger URL."
				return render_template("bot_accounts_add.html", error = error)

			r = requests.get(uri, headers={"Accept": "application/json"}, timeout=10)
			try:
				j = r.json()
			except:
				error = "Invalid WebFinger response."
				return render_template("bot_accounts_add.html", error = error)

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
				c.execute("REPLACE INTO `fedi_accounts` (`handle`, `outbox`) VALUES (%s, %s)", (request.form['account'], outbox))
				c.execute("INSERT INTO `bot_learned_accounts` (`bot_id`, `fedi_id`) VALUES (%s, %s)", (session['bot'], request.form['account']))
				c.close()
				mysql.connection.commit()
				return redirect("/bot/accounts/{}".format(session['bot']), 303)
			else:
				error = "Couldn't access ActivityPub outbox. {} may require authenticated fetches, which FediBooks doesn't support yet.".format(instance)
				return render_template("bot_accounts_add.html", error = error)
	else:
		# new account add request
		session['step'] = 1

	return render_template("bot_accounts_add.html", error = session.pop('error', None))

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
						session['error'] = "Gab instances are not supported."
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
				# take them back home
				del session['instance']
				del session['instance_type']
				session['step'] = 1
				return redirect(url_for("home"), 303)

	else:
		if 'step' in session and session['step'] == 4:
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
			c.execute("INSERT INTO `credentials` (client_id, client_secret, secret) VALUES (%s, %s, %s)", (session['client_id'], session['client_secret'], session['secret']))
			credentials_id = c.lastrowid
			mysql.connection.commit()

			# get webpush url
			privated, publicd = client.push_subscription_generate_keys()
			private = privated['privkey']
			public = publicd['pubkey']
			secret = privated['auth']
			client.push_subscription_set("{}/push/{}".format(cfg['base_uri'], handle), publicd, mention_events = True)

			c.execute("INSERT INTO `bots` (handle, user_id, credentials_id, push_public_key, push_private_key, push_secret) VALUES (%s, %s, %s, %s, %s, %s)", (handle, session['user_id'], credentials_id, public, private, secret))
			mysql.connection.commit()
			c.close()

			# clean up unneeded variables
			del session['code']
			del session['instance']
			del session['instance_type']
			del session['client_id']
			del session['client_secret']
		else:
			# user is starting a new bot create request
			session['step'] = 1


	return render_template("bot_create.html", error = session.pop('error', None))

@app.route("/bot/create/back")
def bot_create_back():
	session['step'] -= 1
	return redirect(url_for("bot_create"), 303)

@app.route("/do/authenticate_bot")
def do_authenticate_bot():
	session['code'] = request.args.get('code')
	session['step'] = 4
	return redirect(url_for("bot_create"), 303)

@app.route("/push/<id>", methods = ['POST'])
def push(id):
	c = mysql.connection.cursor()
	c.execute("SELECT client_id, client_secret, secret FROM credentials WHERE id = (SELECT credentials_id FROM bots WHERE handle = %s)", (id,))
	login = c.fetchone()
	client = Mastodon(
		client_id = login[0],
		client_secret = login[1],
		access_token = login[2],
		api_base_url = "https://{}".format(id.split("@")[2])
	)

	c.execute("SELECT push_private_key, push_secret FROM bots WHERE handle = %s", (id,))
	p = c.fetchone()
	params = {
		'privkey': int(p[0].rstrip("\0")),
		'auth': p[1]
	}
	push_object = client.push_subscription_decrypt_push(request.data, params, request.headers['Encryption'], request.headers['Crypto-Key'])

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

	c = mysql.connection.cursor()
	c.execute("SELECT COUNT(*) FROM users WHERE email = %s", (request.form['email'],))
	if c.fetchone()[0] > 0:
		session['error'] = "Email address already in use."
		return redirect(url_for("show_signup_page"), 303)

	pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest()
	pw = bcrypt.hashpw(pw_hashed, bcrypt.gensalt(12))

	# try to sign up
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

@app.route("/issue/bug")
def report_bug():
	return render_template("report_bug.html")

@app.route("/img/bot_generic.png")
def img_bot_generic():
	return send_file("static/bot_generic.png", mimetype="image/png")

@app.route("/favicon.ico")
def favicon():
	return send_file("static/favicon.ico")

def bot_check(bot):
	# check to ensure bot is owned by user
	c = mysql.connection.cursor()
	c.execute("SELECT COUNT(*) FROM `bots` WHERE `handle` = %s AND `user_id` = %s", (bot, session['user_id']))
	return c.fetchone()[0] == 1
