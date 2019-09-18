from flask import render_template, session, request, redirect, url_for
import bcrypt
import MySQLdb
import hashlib

def settings(mysql):
	if request.method == 'GET':
		dc = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
		dc.execute("SELECT * FROM `users` WHERE id = %s", (session['user_id'],))
		user = dc.fetchone()
		dc.close()
		return render_template("settings.html", user = user, error = session.pop('error', None), success = session.pop('success', None))

	else:
		# update settings
		c = mysql.connection.cursor()

		c.execute("SELECT COUNT(*) FROM users WHERE email = %s AND id != %s", (request.form['email'], session['user_id']))
		if c.fetchone()[0] > 0:
			session['error'] = "Email address already in use."
			return redirect(url_for("render_settings"), 303)

		for setting in [request.form['fetch-error'], request.form['submit-error'], request.form['reply-error'], request.form['generation-error']]:
			if setting not in ['once', 'always', 'never']:
				session['error'] = 'Invalid option "{}".'.format(setting)
				return redirect(url_for('render_settings'), 303)

		if request.form['password'] != '':
			# user is updating their password
			if len(request.form['password']) < 8:
				session['error'] = "Password too short."
				return redirect(url_for("render_settings"), 303)

			pw_hashed = hashlib.sha256(request.form['password'].encode('utf-8')).digest().replace(b"\0", b"\1")
			pw = bcrypt.hashpw(pw_hashed, bcrypt.gensalt(12))
			c.execute("UPDATE users SET password = %s WHERE id = %s", (pw, session['user_id']))

		# don't require email verification again if the new email address is the same as the old one
		c.execute("SELECT email_verified FROM users WHERE id = %s", (session['user_id'],))
		if c.fetchone()[0]:
			c.execute("SELECT email FROM users WHERE id = %s", (session['user_id'],))
			previous_email = c.fetchone()[0]

			email_verified = (previous_email == request.form['email'])
		else:
			email_verified = False
		
		try:
			c.execute("UPDATE users SET email = %s, email_verified = %s, `fetch` = %s, submit = %s, generation = %s, reply = %s WHERE id = %s", (
				request.form['email'],
				email_verified,
				request.form['fetch-error'],
				request.form['submit-error'],
				request.form['generation-error'],
				request.form['reply-error'],
				session['user_id']
			))
			c.close()
			mysql.connection.commit()
		except:
			session['error'] = "Encountered an error while updating the database."
			return redirect(url_for('render_settings'), 303)

		session['success'] = True
		return redirect(url_for('render_settings'), 303)
