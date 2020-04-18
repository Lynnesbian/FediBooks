import json
import os

import MySQLdb

SQL_SETUP_PATH = "setup.sql"

cfg = json.load(open('config.json'))


def get_mysql():
    return MySQLdb.connect(
        host=cfg['db_host'],
        user=cfg['db_user'],
        passwd=cfg['db_pass'],
        use_unicode=True,
        charset="utf8mb4"
    )

    
def setup_db(db):
    cursor = db.cursor()

    db_exists = cursor.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME=%s", (cfg['db_name'],))
    if db_exists:
        if not os.environ.get("FEDIBOOKS_TEST_OVERWRITE_DB"):
            cursor.close()
            db.close()
            raise Exception("Database exists, I'm not touching this because tests destroy data!")
        else:
            cursor.execute("DROP DATABASE %s" % cfg["db_name"])

    cursor.execute("CREATE DATABASE %s" % cfg["db_name"])

    cursor.execute(open(SQL_SETUP_PATH).read())
    cursor.close()

    db.autocommit(True)
    return db


def cleanup_db(db):
    cursor = db.cursor()

    cursor.execute("DROP DATABASE %s" % cfg["db_name"])
    cursor.close()
    db.close()
