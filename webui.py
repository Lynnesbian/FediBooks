from flask import Flask, render_template, session
from flask_mysqldb import MySQL
import json

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
		return render_template("home.html")
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
def show_signup_page():
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
