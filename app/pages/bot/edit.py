from flask import session, request, redirect, render_template
import MySQLdb

def bot_edit(id, mysql):
	if request.method == "GET":
		dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
		dc.execute("SELECT * FROM bots WHERE handle = %s", (id,))
		return render_template("bot/edit.html", bot = dc.fetchone(), error = session.pop('error', None), success = session.pop('success', None))
	else:
		# update stored settings
		replies_enabled = 'replies' in request.form
		learn_from_cw = 'cw-learning' in request.form

		if request.form['fake-mention-style'] not in ['full', 'brief']:
			session['error'] = "Invalid setting for fake mention style."
			return redirect("/bot/edit/{}".format(id), 303)

		if request.form['fake-mentions'] not in ['always', 'middle', 'never']:
			session['error'] = "Invalid setting for fake mentions."
			return redirect("/bot/edit/{}".format(id), 303)

		if request.form['privacy'] not in ['public', 'unlisted', 'private']:
			session['error'] = "Invalid setting for post privacy."
			return redirect("/bot/edit/{}".format(id), 303)
		
		if int(request.form['length']) < 100 or int(request.form['length']) > 5000:
			session['error'] = "Invalid setting for maximum post length."
			return redirect("/bot/edit/{}".format(id), 303)

		if int(request.form['freq']) < 15 or int(request.form['freq']) > 240 or int(request.form['freq']) % 5:
			session['error'] = "Invalid setting for post frequency."
			return redirect("/bot/edit/{}".format(id), 303)

		if len(request.form['cw']) > 128:
			session['error'] = "Content warning cannot exceed 128 characters."
			return redirect("/bot/edit/{}".format(id), 303)

		c = mysql.connection.cursor()
		try:
			c.execute("UPDATE bots SET replies_enabled = %s, post_frequency = %s, content_warning = %s, length = %s, fake_mentions = %s, fake_mentions_full = %s, post_privacy = %s, learn_from_cw = %s WHERE handle = %s", (
				replies_enabled,
				request.form['freq'],
				request.form['cw'] if request.form['cw'] != "" else None,
				request.form['length'],
				request.form['fake-mentions'],
				request.form['fake-mention-style'] == 'full',
				request.form['privacy'],
				learn_from_cw,
				id
			))
			mysql.connection.commit()
			c.close()
		except:
			session['error'] = "Couldn't save your settings."
			return redirect("/bot/edit/{}".format(id), 303)

		session['success'] = True
		return redirect("/bot/edit/{}".format(id), 303)
