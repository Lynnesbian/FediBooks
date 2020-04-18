def test_homepage(client):
    response = client.get("/")
    assert response.status_code == 200


def test_homepage_logged_in_no_bots(client, database):
    with client.session_transaction() as session:
        session["user_id"] = "123"
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hi there! You have 0 bots." in response.data


def test_home_logged_in_has_bots(client, database):
    cursor = database.cursor()

    # TODO move these lines into a factory
    cursor.execute("INSERT INTO `users` (email, password) VALUES (%s, %s)", ("user1@localhost", "pass1"))
    user1_id = cursor.lastrowid
    cursor.execute("INSERT INTO `users` (email, password) VALUES (%s, %s)", ("user2@localhost", "pass2"))
    user2_id = cursor.lastrowid

    cursor.execute("INSERT INTO `credentials` (client_id, client_secret, secret) VALUES (%s, %s, %s)", ("123", "123", "123"))
    fake_credentials = cursor.lastrowid

    cursor.execute("INSERT INTO `bots` (handle, user_id, enabled, credentials_id, push_public_key, push_private_key, push_secret) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                   ("handle1", user1_id, False, fake_credentials, "pubkey", "privkey", "pushsecret"))
    cursor.execute("INSERT INTO `bots` (handle, user_id, enabled, credentials_id, push_public_key, push_private_key, push_secret) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                   ("handle2", user2_id, True, fake_credentials, "pubkey", "privkey", "pushsecret"))


    with client.session_transaction() as session:
        session["user_id"] = user1_id
    response = client.get("/")
    assert response.status_code == 200
    assert b"Hi there! You have 1 bot, 0 of which are currently active." in response.data

    cursor.execute("UPDATE `bots` SET enabled = %s WHERE user_id = %s", (True, user1_id))

    response = client.get("/")
    assert response.status_code == 200
    assert b"Hi there! You have 1 bot, 1 of which is currently active." in response.data
