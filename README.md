# FediBooks

A web UI for creating your very own ebooks bots.

# Selfhosting

1. Install ``python3`` and ``mariadb``. If you're installing on Windows, make sure to check "Add Python to PATH" during Python installation.

2. Install the requirements, using ``pip``:

```
# pip3 install -r ./requirements.txt
```

If this doesn't work, try using ``pip`` instead. If it still doesn't work, you might have to install an additional package (for example, ``python-pip`` on Arch Linux).

3. Copy the ``app/config.sample.json`` file to ``app/config.json``.

4. Fill in the ``app/config.json`` file.

5. Run ``python3 app/setup.py`` and follow the on-screen prompts.

6. Open the MySQL prompt (using the ``mysql`` command) and type in the following commands:

```
CREATE DATABASE `fedibooks`;
CREATE USER 'myuser' IDENTIFIED BY 'mypassword';
GRANT USAGE ON *.* TO 'myuser'@localhost IDENTIFIED BY 'mypassword';
GRANT ALL privileges ON `fedibooks`.* TO 'myuser'@localhost;
FLUSH PRIVILEGES;
exit
```

where ``fedibooks`` is your database name, ``myuser`` is your database username and ``mypassword`` is your database user's password.

7. Run

```
# mysql -u USERNAME -p DATABASE < db/setup.sql
```

where USERNAME is your database username and DATABASE is your database name.

8. Run ``./run.sh`` to start FediBooks.
