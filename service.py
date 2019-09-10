#!/usr/bin/env python3
import MySQLdb
from multiprocessing import Pool
import json
import functions

cfg = json.load(open('config.json'))

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

print("Generating posts")
cursor.execute("SELECT handle FROM bots WHERE enabled = TRUE AND TIMESTAMPDIFF(MINUTE, last_post, CURRENT_TIMESTAMP()) > post_frequency")
bots = cursor.fetchall()

with Pool(cfg['service_threads']) as p:
	p.map(functions.make_post, bots)

#TODO: other cron tasks should be done here, like updating profile pictures
