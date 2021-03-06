from bs4 import BeautifulSoup
import MySQLdb
from pebble import ProcessPool
from concurrent.futures import TimeoutError
import markovify
import requests
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from Crypto.Signature import PKCS1_v1_5
from base64 import b64decode, b64encode
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
		lb.replace_with("\n")

	for p in soup.select("p"): # ditto for <p>
		p.replace_with("\n")

	for ht in soup.select("a.hashtag"): # convert hashtags from links to text
		ht.unwrap()

	for link in soup.select("a"): #ocnvert <a href='https://example.com>example.com</a> to just https://example.com
		if 'href' in link:
			# apparently not all a tags have a href, which is understandable if you're doing normal web stuff, but on a social media platform??
			link.replace_with(link["href"])

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
		db=cfg['db_name'],
		use_unicode=True,
		charset="utf8mb4"
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
		return bot, None

	if bot['fake_mentions'] == 'never':
		# remove all mentions from the training data before the markov model sees it
		posts = re.sub(r"(?<!\S)@\w+(@[\w.]+)?\s?", "", posts)

	model = nlt_fixed(posts)
	tries = 0
	post = None

	# even with such a high tries value for markovify, it still sometimes returns none.
	# so we implement our own tries function as well, and try five times.
	while post is None and tries < 5:
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

	# post will be None if there's no posts for the bot to learn from.
	# in such a case, we should just exit without doing anything.
	if post == None: return

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
		db=cfg['db_name'],
		use_unicode=True,
		charset="utf8mb4"
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
		print("Failed to submit post for {}".format(handle))

	if id == None:
		# this wasn't a reply, it was a regular post, so update the last post date
		c.execute("UPDATE bots SET last_post = CURRENT_TIMESTAMP() WHERE handle = %s", (handle,))
		db.commit()
	c.close()

def task_done(future):
	try:
		result = future.result()  # blocks until results are ready
	except TimeoutError as error:
		if not future.silent: print("Timed out on {}.".format(future.function_data))

def do_in_pool(function, data, timeout=30, silent=False):
	with ProcessPool(max_workers=5, max_tasks=10) as pool:
		for i in data:
			future = pool.schedule(function, args=[i], timeout=timeout)
			future.silent = silent
			future.function_data = i
			future.add_done_callback(task_done)

def get_key():
	db = MySQLdb.connect(
		host = cfg['db_host'],
		user=cfg['db_user'],
		passwd=cfg['db_pass'],
		db=cfg['db_name'],
		use_unicode=True,
		charset="utf8mb4"
	)

	dc = db.cursor(MySQLdb.cursors.DictCursor)
	dc.execute("SELECT * FROM http_auth_key")
	key = dc.fetchone()
	if key == None:
		# generate new key
		key = {}
		privkey = RSA.generate(4096)

		key['private'] = privkey.exportKey('PEM').decode('utf-8')
		key['public'] = privkey.publickey().exportKey('PEM').decode('utf-8')

		dc.execute("INSERT INTO http_auth_key (private, public) VALUES (%s, %s)", (key['private'], key['public']))

	dc.close()
	db.commit()

	return key

def signed_get(url, timeout = 10, additional_headers = {}, request_json = True):
	headers = {}
	if request_json:
		headers = {
			"Accept": "application/json",
			"Content-Type": "application/json"
		}

	headers = {**headers, **additional_headers}

	# sign request headers
	key = RSA.importKey(get_key()['private'])
	sigstring = ''
	for header, value in headers.items():
		sigstring += '{}: {}\n'.format(header.lower(), value)

	sigstring.rstrip("\n")

	pkcs = PKCS1_v1_5.new(key)
	h = SHA256.new()
	h.update(sigstring.encode('ascii'))

	signed_sigstring = b64encode(pkcs.sign(h)).decode('ascii')

	sig = {
		'keyId': "{}/actor".format(cfg['base_uri']),
		'algorithm': 'rsa-sha256',
		'headers': ' '.join(headers.keys()),
		'signature': signed_sigstring
	}

	sig_header = ['{}="{}"'.format(k, v) for k, v in sig.items()]
	headers['signature'] = ','.join(sig_header)

	r = requests.Request('GET', url, headers)
	return r.headers
	# return requests.get(url, timeout = timeout)
