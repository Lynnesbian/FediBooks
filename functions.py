from bs4 import BeautifulSoup
import html, re

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
