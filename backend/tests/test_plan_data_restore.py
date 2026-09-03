def test_restore_plan_data_round_trips_a_snapshot(client, auth_headers, project, floor_plan):
    """Simulates what the frontend's undo does: capture plan_data before an
    edit, apply an edit that clears furniture (a room resize), then restore
    the captured snapshot and confirm the furniture comes back."""
    floor = floor_plan["plan_data"]["floors"][0]
    room = floor["rooms"][0]
    assert room["furniture"] != []  # sanity check: generation actually placed furniture here

    snapshot_before = floor_plan["plan_data"]

    resize_payload = {
        "floor_number": floor["floor_number"],
        "rooms": {room["id"]: {"x": room["x"], "y": room["y"], "width": room["width"] - 0.5, "length": room["length"]}},
    }
    resize_resp = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms",
        json=resize_payload, headers=auth_headers,
    )
    assert resize_resp.status_code == 200, resize_resp.text
    resized_floor = next(f for f in resize_resp.json()["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])
    resized_room = next(r for r in resized_floor["rooms"] if r["id"] == room["id"])
    assert resized_room["furniture"] == []  # confirms the resize did clear furniture, as documented

    restore_resp = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/plan-data",
        json={"plan_data": snapshot_before},
        headers=auth_headers,
    )
    assert restore_resp.status_code == 200, restore_resp.text
    restored = restore_resp.json()
    restored_floor = next(f for f in restored["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])
    restored_room = next(r for r in restored_floor["rooms"] if r["id"] == room["id"])

    assert restored_room["width"] == room["width"]
    assert restored_room["furniture"] == room["furniture"]

    # estimates were recalculated from the restored geometry, not left stale
    assert abs(restored["total_built_up_area"] - floor_plan["total_built_up_area"]) < 0.01
    assert restored["plan_data"]["meta"]["cost_estimate"]["total_built_up_area"] == restored["total_built_up_area"]


def test_restore_plan_data_rejects_malformed_payload(client, auth_headers, project, floor_plan):
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/plan-data",
        json={"plan_data": {"nonsense": True}},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_restore_plan_data_rejects_unowned_floor_plan(client, auth_headers, project, floor_plan):
    from tests.conftest import register_and_login

    other_headers = register_and_login(client, email="someone-else@example.com")

    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/plan-data",
        json={"plan_data": floor_plan["plan_data"]},
        headers=other_headers,
    )
    assert r.status_code in (403, 404)
