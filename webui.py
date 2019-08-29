from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def hello():
	return render_template("front_page.html")

@app.route("/welcome")
def welcome():
	return render_template("welcome.html")

@app.route("/login")
def show_login_page():
	return render_template("login.html")
