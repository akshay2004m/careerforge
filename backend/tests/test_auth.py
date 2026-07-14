def test_signup_and_me(client):
    r = client.post(
        "/api/auth/signup",
        json={"name": "Ada", "email": "ada@example.com", "password": "password1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"
    assert me.json()["name"] == "Ada"


def test_signup_weak_password(client):
    r = client.post(
        "/api/auth/signup",
        json={"name": "Bad", "email": "bad@example.com", "password": "short"},
    )
    assert r.status_code in (400, 422)


def test_login_wrong_password(client):
    client.post(
        "/api/auth/signup",
        json={"name": "Bob", "email": "bob@example.com", "password": "password1"},
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "wrongpass9"},
    )
    assert r.status_code == 401


def test_login_success(client):
    client.post(
        "/api/auth/signup",
        json={"name": "Bob", "email": "bob2@example.com", "password": "password1"},
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "bob2@example.com", "password": "password1"},
    )
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_duplicate_signup(client):
    payload = {"name": "Dup", "email": "dup@example.com", "password": "password1"}
    assert client.post("/api/auth/signup", json=payload).status_code == 200
    r = client.post("/api/auth/signup", json=payload)
    assert r.status_code == 400
