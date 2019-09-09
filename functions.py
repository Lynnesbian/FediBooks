from bs4 import BeautifulSoup
import MySQLdb
import markovify
from mastodon import Mastodon
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
	text = re.sub("https://([^/]+)/(@[^ ]+)", r"\2@\1", text) # put mastodon-style mentions back in
	text = re.sub("https://([^/]+)/users/([^ ]+)", r"@\2@\1", text) # put pleroma-style mentions back in
	text = text.rstrip("\n") # remove trailing newline(s)
	return text

def make_post(handle):
	handle = handle[0]
	db = MySQLdb.connect(
		host = cfg['db_host'],
		user=cfg['db_user'],
		passwd=cfg['db_pass'],
		db=cfg['db_name']
	)
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
