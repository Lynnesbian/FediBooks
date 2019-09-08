#!/usr/bin/env python3
from mastodon import Mastodon
import MySQLdb
import requests
import markovify
from multiprocessing import Pool
import json, re
import functions

cfg = json.load(open('config.json'))

class nlt_fixed(markovify.NewlineText): # modified version of NewlineText that never rejects sentences
	def test_sentence_input(self, sentence):
		return True # all sentences are valid <3

def scrape_posts(account):
	handle = account[0]
	outbox = account[1]
	print("Scraping {}".format(handle))
	c = db.cursor()
	last_post = 0
	c.execute("SELECT COUNT(*) FROM `posts` WHERE `fedi_id` = %s", (handle,))
	if c.fetchone()[0] > 0:
		# we've downloaded this user's posts before
		# find out the most recently downloaded post of theirs
		c.execute("SELECT `post_id` FROM `posts` WHERE `fedi_id` = %s ORDER BY `id` DESC LIMIT 1", (handle,))
		last_post = c.fetchone()[0]

	r = requests.get(outbox)
	j = r.json()
	# check for pleroma
	pleroma = 'next' not in j
	if pleroma:
		j = j['first']
	else:
		uri = "{}&min_id={}".format(outbox, last_post)
		r = requests.get(uri)
		j = r.json()

		# here we go!
		# warning: scraping posts from outbox.json is messy stuff
		done = False
		while not done and len(j['orderedItems']) > 0:
			for oi in j['orderedItems']:
				if oi['type'] == "Create":
					# this is a status/post/toot/florp/whatever
					# first, check to see if we already have this in the database
					post_id = re.search(r"([^\/]+)/?$", oi['object']['id']).group(1) # extract 123 from https://example.com/posts/123/
					c.execute("SELECT COUNT(*) FROM `posts` WHERE `fedi_id` = %s AND `post_id` = %s", (handle, post_id))
					if c.fetchone()[0] > 0:
						# this post is already in the DB.
						# we'll set done to true because we've caught up to where we were last time.
						done = True
						# we'll still iterate over the rest of the posts, though, in case there are still some new ones on this page.
						continue

					content = oi['object']['content']
					# remove HTML tags and such from post
					content = functions.extract_post(content)

					if len(content) > 65535:
						# post is too long to go into the DB
						continue

					try:
						c.execute("INSERT INTO `posts` (`fedi_id`, `post_id`, `content`, `cw`) VALUES (%s, %s, %s, %s)", (
							handle,
							post_id,
							content,
							1 if (oi['object']['summary'] != None and oi['object']['summary'] != "") else 0
						))
					except:
						#TODO: error handling
						raise

			if not done:
				if pleroma:
					r = requests.get(j['next'], timeout = 10)
				else:
					r = requests.get(j['prev'], timeout = 10)

				if r.status_code == 429:
					# we are now being ratelimited, move on to the next user
					done = True
				else:
					j = r.json()

		db.commit()
		c.close()

def make_post(handle):
	handle = handle[0]
	print("Generating post for {}".format(handle))
	c = db.cursor()
	c.execute("""
	SELECT 
			learn_from_cw, client_id, client_secret, secret
	FROM
			bots, credentials
	WHERE
			bots.credentials_id = (SELECT 
							credentials_id
					FROM
							bots
					WHERE
							handle = %s)
	""", (handle,))

	bot = c.fetchone()
	client = Mastodon(
		client_id = bot[1],
		client_secret = bot[2],
		access_token = bot[3],
		api_base_url = "https://{}".format(handle.split("@")[2])
	)

	# by default, only select posts that don't have CWs.
	# if learn_from_cw, then also select posts with CWs
	cw_list = [False]
	if bot[0]:
		cw_list = [False, True]

	# select 1000 random posts for the bot to learn from
	c.execute("SELECT content FROM posts WHERE fedi_id IN (SELECT fedi_id FROM bot_learned_accounts WHERE bot_id = %s) AND cw IN %s ORDER BY RAND() LIMIT 1000", (handle, cw_list))

	# this line is a little gross/optimised but here's what it does
	# 1. fetch all of the results from the above query
	# 2. turn (('this',), ('format')) into ('this', 'format')
	# 3. convert the tuple to a list
	# 4. join the list into a string separated by newlines
	posts = "\n".join(list(sum(c.fetchall(), ())))

	model = nlt_fixed(posts)
	tries = 0
	sentence = None
	# even with such a high tries value for markovify, it still sometimes returns none.
	# so we implement our own tries function as well, and try ten times.
	while sentence is None and tries < 10:
		sentence = model.make_short_sentence(500, tries = 10000)
		tries += 1

	# TODO: mention handling

	if sentence == None:
		# TODO: send an error email
		pass
	else:
		client.status_post(sentence)

	# TODO: update date of last post

print("Establishing DB connection")
db = MySQLdb.connect(
	host = cfg['db_host'],
	user=cfg['db_user'],
	passwd=cfg['db_pass'],
	db=cfg['db_name']
)

print("Cleaning up database")
# delete any fedi accounts we no longer need
cursor = db.cursor()
cursor.execute("DELETE FROM fedi_accounts WHERE handle NOT IN (SELECT fedi_id FROM bot_learned_accounts);")

print("Downloading posts")
cursor.execute("SELECT `handle`, `outbox` FROM `fedi_accounts` ORDER BY RAND()")
accounts = cursor.fetchall()
# with Pool(8) as p:
# 	p.map(scrape_posts, accounts)

print("Generating posts")
cursor.execute("SELECT handle FROM bots WHERE enabled = TRUE")
bots = cursor.fetchall()

with Pool(8) as p:
	p.map(make_post, bots)

#TODO: other cron tasks should be done here, like updating profile pictures
