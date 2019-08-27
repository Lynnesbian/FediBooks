from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def hello():
	return render_template("front_page.html")
