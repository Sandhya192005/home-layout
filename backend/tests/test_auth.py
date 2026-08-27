def test_register_and_login(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "full_name": "A User", "password": "supersecret123"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "a@example.com"

    r = client.post("/api/v1/auth/login", data={"username": "a@example.com", "password": "supersecret123"})
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


def test_register_duplicate_email_rejected(client):
    payload = {"email": "dupe@example.com", "full_name": "Dupe", "password": "supersecret123"}
    r1 = client.post("/api/v1/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/auth/register", json=payload)
    assert r2.status_code == 400


def test_login_wrong_password_rejected(client):
    client.post(
        "/api/v1/auth/register",
        json={"email": "b@example.com", "full_name": "B User", "password": "supersecret123"},
    )
    r = client.post("/api/v1/auth/login", data={"username": "b@example.com", "password": "wrongpass"})
    assert r.status_code == 401


def test_me_requires_auth(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_returns_current_user(client, auth_headers):
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "test@example.com"
