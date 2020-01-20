from flask import session, render_template, request, redirect, url_for
import requests
from mastodon import Mastodon
import re, json

def bot_accounts_add(mysql, cfg):
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

			session['username'] = handle_list[1]
			session['instance'] = handle_list[2]
			session['handle'] = request.form['account']

			if session['instance'] in json.load(open("blacklist.json")):
				session['error'] = "Learning from accounts on this instance is not allowed."
				return redirect(url_for("render_bot_accounts_add"))

			try:
				r = requests.get("https://{}/api/v1/instance".format(session['instance']), timeout=10)
			except requests.exceptions.ConnectionError:
				error = "Couldn't connect to {}.".format(session['instance'])
				return render_template("bot/accounts_add.html", error = error)
			except:
				error = "An unknown error occurred."
				return render_template("bot/accounts_add.html", error = error)

			if r.status_code == 200:
				j = r.json()
				if "Pleroma" in j['version']:
					session['instance_type'] = "Pleroma"
					session['step'] += 1
				else:
					if 'contact_account' in j and 'is_pro' in j['contact_account']:
						# gab instance
						session['error'] = "Gab instances are not supported."
						return render_template("bot/accounts_add.html", error = error)
					else:
						session['instance_type'] = "Mastodon"
						session['step'] += 1

			else:
				error = "Unsupported instance type. Misskey support is planned."
				return render_template("bot/accounts_add.html", error = error)

			session['client_id'], session['client_secret'] = Mastodon.create_app(
				"FediBooks User Authenticator",
				api_base_url="https://{}".format(session['instance']),
				scopes=["read:statuses", "read:accounts"] if session['instance_type'] == 'Mastodon' else ["read"],
				website=cfg['base_uri']
			)

			client = Mastodon(
				client_id=session['client_id'],
				client_secret=session['client_secret'],
				api_base_url="https://{}".format(session['instance'])
			)

			session['url'] = client.auth_request_url(
				client_id=session['client_id'],
				scopes=["read:statuses", "read:accounts"] if session['instance_type'] == 'Mastodon' else ["read"]
			)

		elif session['step'] == 2:
			# test authentication
			try:
				client = Mastodon(client_id=session['client_id'], client_secret=session['client_secret'], api_base_url=session['instance'])
				session['secret'] = client.log_in(
					code = request.form['code'],
					scopes=["read:statuses", "read:accounts"] if session['instance_type'] == 'Mastodon' else ["read"],
				)
				username = client.account_verify_credentials()['username']
				if username != session['username']:
					error = "Please authenticate as {}.".format(session['username'])
					if username.lower() == session['username'].lower():
						error += " Make sure you capitalised the name properly - @user and @USER are different."
					return render_template("bot/accounts_add.html", error = error)
			except:
				session['step'] = 1
				error = "Authentication failed."
				return render_template("bot/accounts_add.html", error = error)

			# 1. download host-meta to find webfinger URL
			r = requests.get("https://{}/.well-known/host-meta".format(session['instance']), timeout=10)
			if r.status_code != 200:
				error = "Couldn't get host-meta."
				return render_template("bot/accounts_add.html", error = error)

			# 2. use webfinger to find user's info page
			#TODO: use more reliable method
			try:
				uri = re.search(r'template="([^"]+)"', r.text).group(1)
				uri = uri.format(uri = "{}@{}".format(session['username'], session['instance']))
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
			r = requests.get(outbox, headers={"Accept": "application/json,application/activity+json"}, timeout=10)
			if r.status_code == 200:
				# success!!
				c = mysql.connection.cursor()
				c.execute("REPLACE INTO `fedi_accounts` (`handle`, `outbox`) VALUES (%s, %s)", (session['handle'], outbox))
				c.execute("INSERT INTO `bot_learned_accounts` (`bot_id`, `fedi_id`) VALUES (%s, %s)", (session['bot'], session['handle']))
				c.close()
				mysql.connection.commit()

				return redirect("/bot/accounts/{}".format(session['bot']), 303)
			else:
				error = "Couldn't access ActivityPub outbox. {} may require authenticated fetches, which FediBooks doesn't support yet.".format(session['instance'])
				return render_template("bot/accounts_add.html", error = error)
	else:
		# new account add request
		session['step'] = 1

	return render_template("bot/accounts_add.html", error = session.pop('error', None))
