#!/usr/bin/env python3
from mastodon import Mastodon
import MySQLdb
import requests
from multiprocessing import Pool
import json

cfg = json.load(open('config.json'))

def scrape_posts(handle, outbox):
	# check for min_id
	last_post = 0
	r = requests.get(outbox)
	j = r.json()
	pleroma = 'next' not in j
	if pleroma:
		j = j['first']
	else:
		uri = "{}&min_id={}".format(outbox, last_post)
		r = requests.get(uri)
		j = r.json()

print("Establishing DB connection")
db = MySQLdb.connect(
	host = cfg['db_host'],
	user=cfg['db_user'],
	passwd=cfg['db_pass'],
	db=cfg['db_name']
)

c = db.cursor()

print("Downloading posts")
