def test_update_furniture_layout(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    room_id = floor["rooms"][0]["id"]

    payload = {
        "floor_number": floor["floor_number"],
        "furniture_by_room": {
            room_id: [{"type": "bed", "x": 1, "y": 1, "w": 4, "l": 6, "rotation": 90}]
        },
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/furniture",
        json=payload,
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    updated_floor = next(f for f in r.json()["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])
    updated_room = next(r for r in updated_floor["rooms"] if r["id"] == room_id)
    assert updated_room["furniture"] == [{"type": "bed", "x": 1, "y": 1, "w": 4, "l": 6, "rotation": 90}]


def test_update_furniture_unknown_room_rejected(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    payload = {"floor_number": floor["floor_number"], "furniture_by_room": {"not_a_real_room": []}}
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/furniture",
        json=payload,
        headers=auth_headers,
    )
    assert r.status_code == 400
