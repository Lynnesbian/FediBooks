from flask import session, render_template, request, redirect
import requests
from mastodon import Mastodon

def bot_accounts_add(mysql):
	if request.method == 'POST':
		if session['step'] == 1:
			if request.form['account'] == session['bot']:
				error = "Bots cannot learn from themselves."
				return render_template("bot/accounts_add.html", error = error)

			# look up user
			handle_list = request.form['account'].split('@')
			if len(handle_list) != 3:
				# not formatted correctly
				error = "Incorrectly formatted handle."
				return render_template("bot/accounts_add.html", error = error)

			username = handle_list[1]
			instance = handle_list[2]

			# gab check
			try:
				r = requests.get("https://{}/api/v1/instance".format(instance), timeout=10)
			except requests.exceptions.ConnectionError:
				error = "Couldn't connect to {}.".format(instance)
				return render_template("bot/accounts_add.html", error = error)
			except:
				error = "An unknown error occurred."
				return render_template("bot/accounts_add.html", error = error)

			if r.status_code == 200:
				j = r.json()
				if 'contact_account' in j and 'is_pro' in j['contact_account']:
					# gab instance
					error = "Gab instances are not supported."
					return render_template("bot/accounts_add.html", error = error)

			# 1. download host-meta to find webfinger URL
			r = requests.get("https://{}/.well-known/host-meta".format(instance), timeout=10)
			if r.status_code != 200:
				error = "Couldn't get host-meta."
				return render_template("bot/accounts_add.html", error = error)

			# 2. use webfinger to find user's info page
			#TODO: use more reliable method
			try:
				uri = re.search(r'template="([^"]+)"', r.text).group(1)
				uri = uri.format(uri = "{}@{}".format(username, instance))
			except:
				error = "Couldn't find WebFinger URL."
				return render_template("bot/accounts_add.html", error = error)

			r = requests.get(uri, headers={"Accept": "application/json"}, timeout=10)
			try:
				j = r.json()
			except:
				error = "Invalid WebFinger response."
				return render_template("bot/accounts_add.html", error = error)

			found = False
			for link in j['links']:
				if link['rel'] == 'self':
					#this is a link formatted like "https://instan.ce/users/username", which is what we need
					uri = link['href']
					found = True
					break
			if not found:
				error = "Couldn't find a valid ActivityPub outbox URL."
				return render_template("bot/accounts_add.html", error = error)

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
				return render_template("bot/accounts_add.html", error = error)
	else:
		# new account add request
		session['step'] = 1

	return render_template("bot/accounts_add.html", error = session.pop('error', None))
