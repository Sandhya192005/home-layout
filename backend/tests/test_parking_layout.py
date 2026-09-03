def _get_parking(floor_plan: dict) -> dict:
    floor = floor_plan["plan_data"]["floors"][0]
    parking = floor["parking"]
    assert parking is not None, "fixture layout has no parking -- adjust requirement_payload cars/two_wheelers"
    return parking


def test_resize_parking_succeeds(client, auth_headers, project, floor_plan):
    parking = _get_parking(floor_plan)
    payload = {
        "floor_number": 0,
        "parking": {"x": parking["x"], "y": parking["y"], "width": parking["width"] - 1, "length": parking["length"]},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/parking", json=payload, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    updated_parking = updated["plan_data"]["floors"][0]["parking"]
    assert updated_parking["width"] == parking["width"] - 1
    assert updated_parking["capacity_cars"] == parking["capacity_cars"]


def test_shrink_parking_below_vehicle_footprint_rejected(client, auth_headers, project, floor_plan):
    parking = _get_parking(floor_plan)
    payload = {
        "floor_number": 0,
        "parking": {"x": parking["x"], "y": parking["y"], "width": 1, "length": 1},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/parking", json=payload, headers=auth_headers
    )
    assert r.status_code == 400
    assert "at least" in r.json()["detail"]


def test_move_parking_outside_plot_rejected(client, auth_headers, project, floor_plan):
    parking = _get_parking(floor_plan)
    payload = {
        "floor_number": 0,
        "parking": {"x": -5, "y": parking["y"], "width": parking["width"], "length": parking["length"]},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/parking", json=payload, headers=auth_headers
    )
    assert r.status_code == 422  # x has ge=0 at the schema level


def test_move_parking_onto_a_room_rejected(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    parking = _get_parking(floor_plan)
    room = floor["rooms"][0]
    payload = {
        "floor_number": 0,
        "parking": {"x": room["x"], "y": room["y"], "width": parking["width"], "length": parking["length"]},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/parking", json=payload, headers=auth_headers
    )
    assert r.status_code == 400
    assert "overlap" in r.json()["detail"]
