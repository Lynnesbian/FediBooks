#!/usr/bin/env python3
import json

import MySQLdb
from mastodon import Mastodon
import requests

import functions

cfg = json.load(open('config.json'))

def update_icon(bot):
	try:
		db = MySQLdb.connect(
			host = cfg['db_host'],
			user=cfg['db_user'],
			passwd=cfg['db_pass'],
			db=cfg['db_name'],
			use_unicode=True,
			charset="utf8mb4"
		)
	except:
		print("Failed to connect to database.")
		return


	url = "https://{}".format(bot['handle'].split("@")[2])
	try:
		r = requests.head(url, timeout=10, allow_redirects = True)
		if r.status_code != 200:
			raise
	except:
		print("{} is down - can't update icon for {}.".format(url, handle))
		return

	client = Mastodon(
		client_id = bot['client_id'],
		client_secret = bot['client_secret'],
		access_token = bot['secret'],
		api_base_url = url
	)


	c = db.cursor()
	try:
		avatar = client.account_verify_credentials()['avatar']
	except:
		c.execute("UPDATE bots SET icon_update_time = CURRENT_TIMESTAMP() WHERE handle = %s", (bot['handle'],))
		db.commit()
		c.close()
		return
	c.execute("UPDATE bots SET icon = %s, icon_update_time = CURRENT_TIMESTAMP() WHERE handle = %s", (avatar, bot['handle']))
	db.commit()
	c.close()

print("Establishing DB connection")
db = MySQLdb.connect(
	host = cfg['db_host'],
	user=cfg['db_user'],
	passwd=cfg['db_pass'],
	db=cfg['db_name'],
	use_unicode=True,
	charset="utf8mb4"
)

print("Cleaning up database")
# delete any fedi accounts we no longer need
cursor = db.cursor()
cursor.execute("DELETE FROM fedi_accounts WHERE handle NOT IN (SELECT fedi_id FROM bot_learned_accounts)")
db.commit()

print("Generating posts")
cursor.execute("SELECT handle FROM bots WHERE enabled = TRUE AND TIMESTAMPDIFF(MINUTE, last_post, CURRENT_TIMESTAMP()) >= post_frequency")
# cursor.execute("SELECT handle FROM bots WHERE enabled = TRUE")
bots = cursor.fetchall()

functions.do_in_pool(functions.make_post, bots, 15)

print("Updating cached icons")
dc = db.cursor(MySQLdb.cursors.DictCursor)
dc.execute("""
SELECT handle, instance_type, client_id, client_secret, secret
FROM bots
INNER JOIN credentials
ON bots.credentials_id = credentials.id
WHERE TIMESTAMPDIFF(HOUR, icon_update_time, CURRENT_TIMESTAMP()) > 2""")
bots = dc.fetchall()

functions.do_in_pool(update_icon, bots)

db.commit()
