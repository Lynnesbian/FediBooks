from flask import Flask, render_template, session, request, redirect, url_for, send_file
from flask_mysqldb import MySQL

from mastodon import Mastodon

import requests
import MySQLdb
import bcrypt
import json, hashlib, re

import functions
from pages.home import home
from pages.settings import settings
from pages.bot.edit import bot_edit
from pages.bot.accounts_add import accounts_add
from pages.bot.create import create

cfg = json.load(open("config.json"))

app = Flask(__name__)
app.secret_key = cfg['secret_key']

app.config['MYSQL_HOST'] = cfg['db_host']
app.config['MYSQL_DB'] = cfg['db_name']
app.config['MYSQL_USER'] = cfg['db_user']
app.config['MYSQL_PASSWORD'] = cfg['db_pass']

mysql = MySQL(app)

scopes = ['write:statuses', 'write:accounts', 'read:accounts', 'read:notifications', 'read:statuses', 'push']
scopes_pleroma = ['read', 'write', 'push']

@app.before_request
def login_check():
	if request.path not in ['/', '/about', '/welcome', '/login', '/signup', '/do/login', '/do/signup', '/static/style.css'] and not request.path.startswith("/push"):
		# page requires authentication
		if 'user_id' not in session:
			return redirect(url_for('home'))

@app.route("/")
def render_home():
	return home(mysql)

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
def render_settings():
	return settings(mysql)

@app.route("/bot/edit/<id>", methods = ['GET', 'POST'])
def render_bot_edit(id):
	return bot_edit(id, mysql)

@app.route("/bot/delete/<id>", methods=['GET', 'POST'])
def bot_delete(id):
	if bot_check(id):
		if request.method == 'GET':
			instance = id.split("@")[2]
			return render_template("bot/delete.html", instance = instance)
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

		return render_template("bot/accounts.html", users = users, post_count = post_count)

@app.route("/bot/accounts/add", methods = ['GET', 'POST'])
def render_bot_accounts_add():
	return bot_accounts_add(mysql)

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
		return render_template("bot/accounts_delete.html", user = id, instance = instance)
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
def render_bot_create():
	return bot_create(mysql, cfg, scopes, scopes_pleroma)

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

	c.execute("SELECT push_private_key, push_secret, replies_enabled FROM bots WHERE handle = %s", (id,))
	bot = c.fetchone()
	if not bot[2]:
		return "Replies disabled."

	params = {
		'privkey': int(bot[0].rstrip("\0")),
		'auth': bot[1]
	}
	push_object = client.push_subscription_decrypt_push(request.data, params, request.headers['Encryption'], request.headers['Crypto-Key'])
	notification = client.notifications(id = push_object['notification_id'])
	me = client.account_verify_credentials()['id']

	# first, check how many times the bot has posted in this thread.
	# if it's over 15, don't reply.
	# this is to stop endless reply chains between two bots.
	try:
		context = client.status_context(notification['status']['id'])
		my_posts = 0
		for post in context['ancestors']:
			if post['account']['id'] == me:
				my_posts += 1
			if my_posts >= 15:
				# don't reply
				return "Didn't reply."
	except:
		# failed to fetch context
		# assume we haven't been participating in this thread
		pass

	functions.make_post([id, notification['status']['id'], notification['status']['visibility'], "@" + notification['account']['acct']])

	return "Success!"

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

	pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest().replace(b"\0", b"\1")
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
	pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest().replace(b"\0", b"\1")
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

@app.route("/help/settings")
def help_settings():
	return render_template("help/settings.html")

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
