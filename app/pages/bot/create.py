from flask import request, session, render_template, redirect, url_for
import requests
from mastodon import Mastodon
import re

def bot_create(mysql, cfg, scopes, scopes_pleroma):
	if request.method == 'POST':
		if session['step'] == 1:
			# strip leading https://, if provided
			session['instance'] = re.match(r"^(?:https?:\/\/)?(.*)", request.form['instance']).group(1)
			
			# check for mastodon/pleroma
			try:
				r = requests.get("https://{}/api/v1/instance".format(session['instance']), timeout=10)
			except requests.ConnectionError:
				session['error'] = "Couldn't connect to https://{}.".format(session['instance'])
				return render_template("bot/create.html", error = session.pop('error', None))
			except:
				session['error'] = "An unknown error occurred while trying to load https://{}".format(session['instance'])
				return render_template("bot/create.html", error = session.pop('error', None))

			if r.status_code == 200:
				j = r.json()
				if "Pleroma" in j['version']:
					session['instance_type'] = "Pleroma"
					session['step'] += 1
				else:
					if 'contact_account' in j and 'is_pro' in j['contact_account']:
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
					scopes=scopes if session['instance_type'] == 'Mastodon' else scopes_pleroma,
					redirect_uris=[redirect_uri],
					website=cfg['base_uri']
				)

				client = Mastodon(
					client_id=session['client_id'],
					client_secret=session['client_secret'],
					api_base_url="https://{}".format(session['instance'])
				)

				url = client.auth_request_url(
					client_id=session['client_id'],
					redirect_uris=redirect_uri,
					scopes=scopes if session['instance_type'] == 'Mastodon' else scopes_pleroma
				)
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
				session['secret'] = client.log_in(
					code = session['code'],
					scopes=scopes if session['instance_type'] == 'Mastodon' else scopes_pleroma,
					redirect_uri='{}/do/authenticate_bot'.format(cfg['base_uri'])
				)
				username = client.account_verify_credentials()['username']
				handle = "@{}@{}".format(username, session['instance'])
			except:
				# authentication error occurred
				error = "Authentication failed."
				session['step'] = 3
				return render_template("bot/create.html", error = error)

			c = mysql.connection.cursor()
			c.execute("SELECT COUNT(*) FROM bots WHERE handle = %s", (handle,))
			count = c.fetchone()
			if count != None and count[0] == 1:
				session['error'] = "{} is currently in use by another FediBooks bot.".format(handle)
				session['step'] = 1
				return redirect(url_for("render_bot_create"), 303)

			# authentication success!!
			c.execute("INSERT INTO `credentials` (client_id, client_secret, secret) VALUES (%s, %s, %s)", (session['client_id'], session['client_secret'], session['secret']))
			credentials_id = c.lastrowid
			mysql.connection.commit()

			# get webpush url
			privated, publicd = client.push_subscription_generate_keys()
			private = privated['privkey']
			public = publicd['pubkey']
			secret = privated['auth']
			client.push_subscription_set("{}/push/{}".format(cfg['base_uri'], handle), publicd, mention_events = True)

			c.execute("INSERT INTO `bots` (handle, user_id, credentials_id, push_public_key, push_private_key, push_secret, instance_type) VALUES (%s, %s, %s, %s, %s, %s, %s)", (handle, session['user_id'], credentials_id, public, private, secret, session['instance_type']))
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


	return render_template("bot/create.html", error = session.pop('error', None))
