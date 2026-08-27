from tests.conftest import register_and_login


def test_create_and_get_project(client, auth_headers):
    r = client.post("/api/v1/projects", json={"name": "Home A", "description": "desc"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    project = r.json()

    r = client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Home A"


def test_list_projects(client, auth_headers):
    client.post("/api/v1/projects", json={"name": "P1"}, headers=auth_headers)
    client.post("/api/v1/projects", json={"name": "P2"}, headers=auth_headers)
    r = client.get("/api/v1/projects", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_update_project(client, auth_headers, project):
    r = client.put(f"/api/v1/projects/{project['id']}", json={"name": "Renamed"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


def test_delete_project_soft_deletes(client, auth_headers, project):
    r = client.delete(f"/api/v1/projects/{project['id']}", headers=auth_headers)
    assert r.status_code == 204
    r = client.get(f"/api/v1/projects/{project['id']}", headers=auth_headers)
    assert r.status_code == 404


def test_project_not_found(client, auth_headers):
    r = client.get("/api/v1/projects/9999", headers=auth_headers)
    assert r.status_code == 404


def test_cross_user_access_forbidden(client, auth_headers, project):
    other_headers = register_and_login(client, email="other@example.com")
    r = client.get(f"/api/v1/projects/{project['id']}", headers=other_headers)
    assert r.status_code == 403
