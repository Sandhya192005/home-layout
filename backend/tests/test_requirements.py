from tests.conftest import requirement_payload


def test_submit_requirement(client, auth_headers, project):
    r = client.post(
        f"/api/v1/projects/{project['id']}/requirements", json=requirement_payload(), headers=auth_headers
    )
    assert r.status_code == 201, r.text
    assert r.json()["bedrooms"] == 3


def test_submit_requirement_too_small_plot_rejected(client, auth_headers, project):
    r = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json=requirement_payload(plot_length=10, plot_width=10),
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert "errors" in r.json()["detail"]


def test_latest_requirement_404_when_none_submitted(client, auth_headers, project):
    r = client.get(f"/api/v1/projects/{project['id']}/requirements/latest", headers=auth_headers)
    assert r.status_code == 404


def test_latest_requirement_returns_most_recent(client, auth_headers, project):
    client.post(
        f"/api/v1/projects/{project['id']}/requirements", json=requirement_payload(bedrooms=2), headers=auth_headers
    )
    client.post(
        f"/api/v1/projects/{project['id']}/requirements", json=requirement_payload(bedrooms=4), headers=auth_headers
    )
    r = client.get(f"/api/v1/projects/{project['id']}/requirements/latest", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["bedrooms"] == 4


def test_list_requirements(client, auth_headers, project, requirement):
    r = client.get(f"/api/v1/projects/{project['id']}/requirements", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
