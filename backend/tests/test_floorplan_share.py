def test_create_and_fetch_share(client, auth_headers, project, floor_plan):
    r = client.post(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/share", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]

    r = client.get(f"/api/v1/public/floorplans/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["total_built_up_area"] == floor_plan["total_built_up_area"]


def test_get_share_before_creation_returns_null(client, auth_headers, project, floor_plan):
    r = client.get(f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/share", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() is None


def test_revoke_share_makes_public_link_404(client, auth_headers, project, floor_plan):
    r = client.post(f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/share", headers=auth_headers)
    token = r.json()["token"]

    r = client.delete(f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/share", headers=auth_headers)
    assert r.status_code == 204

    r = client.get(f"/api/v1/public/floorplans/{token}")
    assert r.status_code == 404


def test_unknown_share_token_404(client):
    r = client.get("/api/v1/public/floorplans/does-not-exist")
    assert r.status_code == 404


def test_public_share_endpoint_rate_limited(client):
    from app.core.config import settings

    for _ in range(settings.PUBLIC_SHARE_RATE_LIMIT_MAX):
        r = client.get("/api/v1/public/floorplans/does-not-exist")
        assert r.status_code == 404

    r = client.get("/api/v1/public/floorplans/does-not-exist")
    assert r.status_code == 429
