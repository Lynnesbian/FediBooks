from flask import Flask, render_template, session, request, redirect, url_for
from flask_mysqldb import MySQL
import requests
import MySQLdb
import bcrypt
import json, hashlib

cfg = json.load(open("config.json"))

app = Flask(__name__)
app.secret_key = cfg['secret_key']

app.config['MYSQL_HOST'] = cfg['db_host']
app.config['MYSQL_DB'] = cfg['db_name']
app.config['MYSQL_USER'] = cfg['db_user']
app.config['MYSQL_PASSWORD'] = cfg['db_pass']

mysql = MySQL(app)

@app.route("/")
def home():
	if 'userid' in session:
		session['step'] = 1
		c = mysql.connection.cursor()
		c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s", (session['userid'],))
		bot_count = c.fetchone()[0]
		active_count = None
		if bot_count > 0:
			c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s AND enabled = TRUE", (session['userid'],))
			active_count = c.fetchone()[0]
		c.close()
		return render_template("home.html", bot_count = bot_count, active_count = active_count)
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

@app.route("/bot/create/")
def bot_create():
	return render_template("bot_create.html")

@app.route("/do/signup", methods=['POST'])
def do_signup():
	# email validation is basically impossible without actually sending an email to the address
	# because fedibooks can't send email yet, we'll just check if the string contains an @ ;)
	if "@" not in request.form['email']:
		return show_signup_page("Invalid email address.")

	if len(request.form['password']) < 8:
		return show_signup_page("Password too short.")

	user_id = hashlib.sha256(request.form['email'].encode('utf-8')).digest()

	pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest()
	pw = bcrypt.hashpw(pw_hashed, bcrypt.gensalt(12))

	# try to sign up
	c = mysql.connection.cursor()
	c.execute("INSERT INTO `users` (email, password) VALUES (%s, %s)", (request.form['email'], pw))
	mysql.connection.commit()
	c.close()

	# success!
	session['userid'] = user_id
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
		session['userid'] = data['id']
		return redirect(url_for("home"))

	else:
		return "invalid login"
