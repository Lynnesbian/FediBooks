#!/usr/bin/env python3
import MySQLdb
from mastodon import Mastodon
from multiprocessing import Pool
import json
import functions

cfg = json.load(open('config.json'))

def update_icon(bot):
	db = MySQLdb.connect(
		host = cfg['db_host'],
		user=cfg['db_user'],
		passwd=cfg['db_pass'],
		db=cfg['db_name'],
		use_unicode=True,
		charset="utf8mb4"
	)

	print("Updating cached icon for {}".format(bot['handle']))
	client = Mastodon(
		client_id = bot['client_id'],
		client_secret = bot['client_secret'],
		access_token = bot['secret'],
		api_base_url = "https://{}".format(bot['handle'].split("@")[2])
	)

	avatar = client.account_verify_credentials()['avatar']
	c = db.cursor()
	c.execute("UPDATE bots SET icon = %s, icon_update_time = CURRENT_TIMESTAMP() WHERE handle = %s", (avatar, bot['handle']))
	db.commit()

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
bots = cursor.fetchall()

with Pool(cfg['service_threads']) as p:
	p.map(functions.make_post, bots)

print("Updating cached icons")
dc = db.cursor(MySQLdb.cursors.DictCursor)
dc.execute("""
SELECT handle, instance_type, client_id, client_secret, secret
FROM bots
INNER JOIN credentials
ON bots.credentials_id = credentials.id
WHERE TIMESTAMPDIFF(HOUR, icon_update_time, CURRENT_TIMESTAMP()) > 2""")
bots = dc.fetchall()

with Pool(cfg['service_threads']) as p:
	p.map(update_icon, bots)

db.commit()
