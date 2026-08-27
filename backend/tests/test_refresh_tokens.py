def _register_and_login_full(client, email="refresh@example.com", password="supersecret123") -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "full_name": "Refresh User", "password": password})
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def test_login_returns_access_and_refresh_token(client):
    tokens = _register_and_login_full(client)
    assert tokens["access_token"]
    assert tokens["refresh_token"]


def test_refresh_issues_new_token_pair(client):
    tokens = _register_and_login_full(client)
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200, r.text
    new_tokens = r.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"})
    assert r.status_code == 200


def test_refresh_token_is_single_use(client):
    tokens = _register_and_login_full(client)
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200

    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401


def test_refresh_with_unknown_token_rejected(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert r.status_code == 401


def test_logout_revokes_refresh_token(client):
    tokens = _register_and_login_full(client)
    r = client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 204

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
