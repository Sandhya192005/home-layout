from app.services import geometry as geo


def _find_east_west_neighbors(rooms: list[dict]):
    """Find two ordinary (non-staircase) rooms in a real generated layout
    that share a north-south (west/east) boundary wide enough for a doorway,
    so a test can drag that boundary and know exactly which other edges must
    stay fixed. The staircase is excluded since it can't be resized."""
    rooms = [r for r in rooms if r["type"] != "staircase"]
    for i, a in enumerate(rooms):
        a_rect = {"x": a["x"], "y": a["y"], "w": a["width"], "l": a["length"]}
        for b in rooms[i + 1 :]:
            b_rect = {"x": b["x"], "y": b["y"], "w": b["width"], "l": b["length"]}
            shared = geo.shared_segment(a_rect, b_rect)
            if not shared:
                continue
            side_a, _side_b, seg = shared
            if side_a in ("west", "east") and geo.segment_length(seg) >= 3:
                west, east = (a, b) if side_a == "east" else (b, a)
                return west, east
    return None


def test_drag_shared_boundary_between_two_rooms(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    pair = _find_east_west_neighbors(floor["rooms"])
    assert pair is not None, "fixture layout has no west/east adjacent room pair to test with"
    west_room, east_room = pair

    shift = 1.0
    payload = {
        "floor_number": floor["floor_number"],
        "rooms": {
            west_room["id"]: {
                "x": west_room["x"], "y": west_room["y"],
                "width": west_room["width"] + shift, "length": west_room["length"],
            },
            east_room["id"]: {
                "x": east_room["x"] + shift, "y": east_room["y"],
                "width": east_room["width"] - shift, "length": east_room["length"],
            },
        },
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms", json=payload, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    updated_floor = next(f for f in updated["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])
    new_west = next(rm for rm in updated_floor["rooms"] if rm["id"] == west_room["id"])
    new_east = next(rm for rm in updated_floor["rooms"] if rm["id"] == east_room["id"])

    assert new_west["width"] == west_room["width"] + shift
    assert new_east["x"] == east_room["x"] + shift
    assert new_west["furniture"] == []
    assert new_east["furniture"] == []
    # area only moved from one room to the other, so the floor's total area is unchanged
    assert updated["total_built_up_area"] == floor_plan["total_built_up_area"]
    # doors/walls were rebuilt, not left stale
    assert any(d["room_id"] in (west_room["id"], east_room["id"]) or d.get("connects_to") in (
        west_room["id"], east_room["id"]
    ) for d in updated_floor["doors"])


def test_room_edit_rejects_unknown_room(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    payload = {"floor_number": floor["floor_number"], "rooms": {"not_a_real_room": {"x": 0, "y": 0, "width": 5, "length": 5}}}
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms", json=payload, headers=auth_headers
    )
    assert r.status_code == 400


def test_room_edit_rejects_staircase_resize(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    stair = next((r for r in floor["rooms"] if r["type"] == "staircase"), None)
    assert stair is not None, "fixture is multi-floor, expected a staircase room"
    payload = {
        "floor_number": floor["floor_number"],
        "rooms": {stair["id"]: {"x": stair["x"], "y": stair["y"], "width": stair["width"] + 1, "length": stair["length"]}},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms", json=payload, headers=auth_headers
    )
    assert r.status_code == 400


def test_room_edit_rejects_overlap(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    ordinary = [r for r in floor["rooms"] if r["type"] != "staircase"]
    a, b = ordinary[0], ordinary[1]
    payload = {
        "floor_number": floor["floor_number"],
        # move room a directly on top of room b -- guaranteed overlap
        "rooms": {a["id"]: {"x": b["x"], "y": b["y"], "width": a["width"], "length": a["length"]}},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms", json=payload, headers=auth_headers
    )
    assert r.status_code == 400


def test_room_edit_rejects_out_of_bounds(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    room = next(r for r in floor["rooms"] if r["type"] != "staircase")
    outline = floor["outline"]
    payload = {
        "floor_number": floor["floor_number"],
        "rooms": {room["id"]: {"x": outline["width"] + 50, "y": room["y"], "width": room["width"], "length": room["length"]}},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms", json=payload, headers=auth_headers
    )
    assert r.status_code == 400


def test_room_edit_no_op_preserves_layout(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    room = next(r for r in floor["rooms"] if r["type"] != "staircase")
    payload = {
        "floor_number": floor["floor_number"],
        "rooms": {room["id"]: {"x": room["x"], "y": room["y"], "width": room["width"], "length": room["length"]}},
    }
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms", json=payload, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_built_up_area"] == floor_plan["total_built_up_area"]
