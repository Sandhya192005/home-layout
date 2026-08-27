from tests.conftest import requirement_payload


def test_generate_creates_floor_plan(client, auth_headers, project, requirement):
    r = client.post(
        f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/generate", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    body = r.json()
    plan = body["floor_plan"]
    assert plan["version"] == 1
    assert len(plan["plan_data"]["floors"]) == 2
    assert plan["total_built_up_area"] > 0
    assert "cost_estimate" in plan["plan_data"]["meta"]
    assert "boq" in plan["plan_data"]["meta"]
    assert "construction_timeline" in plan["plan_data"]["meta"]


def test_regenerate_bumps_version_and_changes_plan(client, auth_headers, project, requirement):
    r1 = client.post(
        f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/generate", headers=auth_headers
    )
    plan1 = r1.json()["floor_plan"]

    r = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json=requirement_payload(plot_width=30, cars=0),
        headers=auth_headers,
    )
    requirement2 = r.json()

    r2 = client.post(
        f"/api/v1/projects/{project['id']}/requirements/{requirement2['id']}/generate", headers=auth_headers
    )
    plan2 = r2.json()["floor_plan"]

    assert plan2["version"] == 2
    assert plan2["total_built_up_area"] != plan1["total_built_up_area"]


def test_get_latest_floor_plan(client, auth_headers, project, floor_plan):
    r = client.get(f"/api/v1/projects/{project['id']}/floorplans/latest", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == floor_plan["id"]


def test_latest_floor_plan_404_when_none_generated(client, auth_headers, project):
    r = client.get(f"/api/v1/projects/{project['id']}/floorplans/latest", headers=auth_headers)
    assert r.status_code == 404


def test_generate_for_unowned_requirement_forbidden(client, auth_headers, project, requirement):
    from tests.conftest import register_and_login

    other_headers = register_and_login(client, email="other@example.com")
    r = client.post(
        f"/api/v1/projects/{project['id']}/requirements/{requirement['id']}/generate", headers=other_headers
    )
    assert r.status_code == 403
