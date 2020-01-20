from bs4 import BeautifulSoup
import MySQLdb
import markovify
from mastodon import Mastodon, MastodonUnauthorizedError
import html, re, json

cfg = json.load(open('config.json'))

class nlt_fixed(markovify.NewlineText): # modified version of NewlineText that never rejects sentences
	def test_sentence_input(self, sentence):
		return True # all sentences are valid <3

def extract_post(post):
	post = html.unescape(post) # convert HTML escape codes to text
	soup = BeautifulSoup(post, "html.parser")
	for lb in soup.select("br"): # replace <br> with linebreak
		lb.insert_after("\n")
		lb.decompose()

	for p in soup.select("p"): # ditto for <p>
		p.insert_after("\n")
		p.unwrap()

	for ht in soup.select("a.hashtag"): # convert hashtags from links to text
		ht.unwrap()

	for link in soup.select("a"): #ocnvert <a href='https://example.com>example.com</a> to just https://example.com
		link.insert_after(link["href"])
		link.decompose()

	text = soup.get_text()
	text = re.sub(r"https://([^/]+)/(@[^\s]+)", r"\2@\1", text) # put mastodon-style mentions back in
	text = re.sub(r"https://([^/]+)/users/([^\s/]+)", r"@\2@\1", text) # put pleroma-style mentions back in
	text = text.rstrip("\n") # remove trailing newline(s)
	return text

def generate_output(handle):
	db = MySQLdb.connect(
		host = cfg['db_host'],
		user=cfg['db_user'],
		passwd=cfg['db_pass'],
		db=cfg['db_name']
	)
	# print("Generating post for {}".format(handle))
	dc = db.cursor(MySQLdb.cursors.DictCursor)
	c = db.cursor()
	dc.execute("""
	SELECT
		learn_from_cw,
		length,
		fake_mentions,
		fake_mentions_full,
		post_privacy,
		content_warning,
		client_id,
		client_secret,
		secret
	FROM
		bots, credentials
	WHERE
		bots.handle = %s
		AND bots.credentials_id = credentials.id
	""", (handle,))

	bot = dc.fetchone()

	# by default, only select posts that don't have CWs.
	# if learn_from_cw, then also select posts with CWs
	cw_list = [False]
	if bot['learn_from_cw']:
		cw_list = [False, True]

	# select 1000 random posts for the bot to learn from
	c.execute("SELECT content FROM posts WHERE fedi_id IN (SELECT fedi_id FROM bot_learned_accounts WHERE bot_id = %s) AND cw IN %s ORDER BY RAND() LIMIT 1000", (handle, cw_list))

	# this line is a little gross/optimised but here's what it does
	# 1. fetch all of the results from the above query
	# 2. turn (('this',), ('format')) into ('this', 'format')
	# 3. convert the tuple to a list
	# 4. join the list into a string separated by newlines
	posts = "\n".join(list(sum(c.fetchall(), ())))
	if len(posts) == 0:
		print("{} - No posts to learn from.".format(handle))
		return

	if bot['fake_mentions'] == 'never':
		# remove all mentions from the training data before the markov model sees it
		posts = re.sub(r"(?<!\S)@\w+(@[\w.]+)?\s?", "", posts)

	model = nlt_fixed(posts)
	tries = 0
	post = None

	# even with such a high tries value for markovify, it still sometimes returns none.
	# so we implement our own tries function as well, and try ten times.
	while post is None and tries < 10:
		post = model.make_short_sentence(bot['length'], tries = 1000)
		tries += 1

	if post == None:
		# TODO: send an error email
		pass
	else:
		if "@" in post and bot['fake_mentions'] != 'never':
			# the unicode zero width space is a (usually) invisible character
			# we can insert it between the @ symbols in a handle to make it appear fine while not mentioning the user
			zws = "\u200B"
			if bot['fake_mentions'] == 'middle':
				# remove mentions at the start of a post
				post = re.sub(r"^(@\w+(@[\w.]+)?\s*)+", "", post)
			# TODO: does this regex catch all valid handles?
			if bot['fake_mentions_full']:
				post = re.sub(r"@(\w+)@([\w.]+)", r"@{}\1@{}\2".format(zws, zws), post)
			else:
				post = re.sub(r"@(\w+)@([\w.]+)", r"@{}\1".format(zws), post)
			# also format handles without instances, e.g. @user instead of @user@instan.ce
			post = re.sub(r"(?<!\S)@(\w+)", r"@{}\1".format(zws), post)

	return bot, post


def make_post(args):
	id = None
	acct = None
	if len(args) > 1:
		id = args[1]
		acct = args[3]
	handle = args[0]

	# print("Generating post for {}".format(handle))

	bot, post = generate_output(handle)

	client = Mastodon(
		client_id = bot['client_id'],
		client_secret = bot['client_secret'],
		access_token = bot['secret'],
		api_base_url = "https://{}".format(handle.split("@")[2])
	)

	db = MySQLdb.connect(
		host = cfg['db_host'],
		user=cfg['db_user'],
		passwd=cfg['db_pass'],
		db=cfg['db_name']
	)
	c = db.cursor()

	# print(post)
	visibility = bot['post_privacy'] if len(args) == 1 else args[2]
	visibilities = ['public', 'unlisted', 'private']
	if visibilities.index(visibility) < visibilities.index(bot['post_privacy']):
		# if post_privacy is set to a more restricted level than the visibility of the post we're replying to, use the user's setting
		visibility = bot['post_privacy']
	if acct is not None:
		post = "{} {}".format(acct, post)

	# ensure post isn't longer than bot['length']
	# TODO: ehhhhhhhhh
	post = post[:bot['length']]
	# send toot!!
	try:
		client.status_post(post, id, visibility = visibility, spoiler_text = bot['content_warning'])
	except MastodonUnauthorizedError:
		# user has revoked the token given to the bot
		# this needs to be dealt with properly later on, but for now, we'll just disable the bot
		c.execute("UPDATE bots SET enabled = FALSE WHERE handle = %s", (handle,))
	except:
		print("Failed to create post for {}".format(handle))

	if id == None:
		# this wasn't a reply, it was a regular post, so update the last post date
		c.execute("UPDATE bots SET last_post = CURRENT_TIMESTAMP() WHERE handle = %s", (handle,))
		db.commit()
	c.close()
