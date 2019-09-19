#!/usr/bin/env python3

from mastodon import Mastodon
import json

cfg = json.load(open("config.json"))

scopes = ["write:statuses"]

print("FediBooks needs access to an account to notify users when they've been added to bots.")
print("What instance would you like FediBooks' account to be on?")
instance = input("https://")
client_id, client_secret = Mastodon.create_app(
	"FediBooks",
	api_base_url="https://{}".format(instance),
	scopes=scopes,
	website=cfg['base_uri']
)

client = Mastodon(
	client_id=client_id,
	client_secret=client_secret,
	api_base_url="https://{}".format(instance)
)

url = client.auth_request_url(
	client_id=client_id,
	scopes=scopes
)
print("Create an account on {}, then click this link to give FediBooks access to the account: {}".format(instance, url))
print("Authorise FediBooks to access the account, then paste the code below.")
code = input("Code: ")

print("Authenticating...")

secret = client.log_in(
	code = code,
	scopes=scopes
)
client.status_post("FediBooks has successfully been set up to use this account.")

cfg['account'] = {
	'client_id': client_id,
	'client_secret': client_secret,
	'secret': secret,
	'instance': instance
}

json.dump(cfg, open('config.json', 'w'))

print("Done! Thanks for using FediBooks!")
