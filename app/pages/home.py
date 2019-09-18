from flask import render_template, session
import MySQLdb

def home(mysql):
	if 'user_id' in session:
		c = mysql.connection.cursor()
		c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s", (session['user_id'],))
		bot_count = c.fetchone()[0]
		active_count = None
		bots = {}
		bot_users = {}
		next_posts = {}

		if bot_count > 0:
			c.execute("SELECT COUNT(*) FROM `bots` WHERE user_id = %s AND enabled = TRUE", (session['user_id'],))
			active_count = c.fetchone()[0]
			dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
			dc.execute("SELECT `handle`, `enabled`, `last_post`, `post_frequency`, `icon` FROM `bots` WHERE user_id = %s", (session['user_id'],))
			bots = dc.fetchall()
			dc.close()

			for bot in bots:
				# multiple SELECTS is slow, maybe SELECT all at once and filter with python?
				c.execute("SELECT COUNT(*) FROM `bot_learned_accounts` WHERE bot_id = %s", (bot['handle'],))
				bot_users[bot['handle']] = c.fetchone()[0]
				c.execute("SELECT post_frequency - TIMESTAMPDIFF(MINUTE, last_post, CURRENT_TIMESTAMP()) FROM bots WHERE TIMESTAMPDIFF(MINUTE, last_post, CURRENT_TIMESTAMP()) <= post_frequency AND enabled = TRUE AND handle = %s", (bot['handle'],))
				next_post = c.fetchone()
				if next_post is not None:
					next_posts[bot['handle']] = next_post

		c.close()
		return render_template("home.html", bot_count = bot_count, active_count = active_count, bots = bots, bot_users = bot_users, next_posts = next_posts)
	else:
		return render_template("front_page.html")
