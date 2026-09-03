from app.services import floorplan_generator as fpg
from app.services import geometry as geo

from tests.conftest import requirement_payload


def _generate(client, auth_headers, project_id: int, **overrides) -> dict:
    r = client.post(
        f"/api/v1/projects/{project_id}/requirements", json=requirement_payload(**overrides), headers=auth_headers
    )
    assert r.status_code == 201, r.text
    requirement = r.json()
    r = client.post(
        f"/api/v1/projects/{project_id}/requirements/{requirement['id']}/generate", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    return r.json()["floor_plan"]


def _floor_with_room_type(plan_data: dict, room_type: str) -> tuple[dict, dict]:
    for floor in plan_data["floors"]:
        room = next((r for r in floor["rooms"] if r["type"] == room_type), None)
        if room:
            return floor, room
    raise AssertionError(f"no {room_type} found on any floor of this plan")


def test_replace_room_updates_type_label_furniture_and_keeps_geometry(client, auth_headers, project, floor_plan):
    """Converting into pooja_room -- the smallest minimums in ROOM_LIBRARY
    (4x5 ft) -- fits inside virtually any generated room regardless of how
    thin the grid-slicer made it, giving a deterministic happy path without
    depending on the generator's exact sizing for this plan."""
    floor, living_room = _floor_with_room_type(floor_plan["plan_data"], "living_room")
    original = {k: living_room[k] for k in ("x", "y", "width", "length")}

    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{living_room['id']}/replace",
        json={"floor_number": floor["floor_number"], "new_type": "pooja_room"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    plan = body["floor_plan"]
    new_floor = next(f for f in plan["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])
    new_room = next(rm for rm in new_floor["rooms"] if rm["id"] == living_room["id"])

    assert new_room["type"] == "pooja_room"
    assert new_room["label"] == "Pooja Room"
    assert {t["type"] for t in new_room["furniture"]} == {"mandir_unit"}

    # geometry (and therefore area/built-up area) is reused exactly as-is --
    # this is a relabel-plus-refurnish, not a resize
    assert original == {k: new_room[k] for k in ("x", "y", "width", "length")}
    assert abs(plan["total_built_up_area"] - floor_plan["total_built_up_area"]) < 0.01

    # cost/BOQ/FAR were still recomputed even though area didn't change
    assert plan["plan_data"]["meta"]["cost_estimate"]["total_built_up_area"] == plan["total_built_up_area"]
    assert "boq" in plan["plan_data"]["meta"]
    assert "far" in plan["plan_data"]["meta"]

    # every room is still reachable, and no other room's geometry moved
    assert fpg.rooms_are_connected([rm["id"] for rm in new_floor["rooms"]], new_floor["doors"])
    old_others = {rm["id"]: (rm["x"], rm["y"], rm["width"], rm["length"]) for rm in floor["rooms"] if rm["id"] != living_room["id"]}
    new_others = {rm["id"]: (rm["x"], rm["y"], rm["width"], rm["length"]) for rm in new_floor["rooms"] if rm["id"] != living_room["id"]}
    assert old_others == new_others


def test_replace_room_rejects_same_type(client, auth_headers, project, floor_plan):
    floor, living_room = _floor_with_room_type(floor_plan["plan_data"], "living_room")
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{living_room['id']}/replace",
        json={"floor_number": floor["floor_number"], "new_type": "living_room"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "already a" in r.json()["detail"]


def test_replace_room_rejects_unknown_type(client, auth_headers, project, floor_plan):
    floor, living_room = _floor_with_room_type(floor_plan["plan_data"], "living_room")
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{living_room['id']}/replace",
        json={"floor_number": floor["floor_number"], "new_type": "not_a_real_type"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "recognized" in r.json()["detail"]


def test_replace_room_rejects_unknown_room(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/not_a_real_room/replace",
        json={"floor_number": floor["floor_number"], "new_type": "kitchen"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_replace_room_rejects_structural_source_type(client, auth_headers, project, floor_plan):
    floor = next(f for f in floor_plan["plan_data"]["floors"] if f.get("has_staircase"))
    staircase = next(r for r in floor["rooms"] if r["type"] == "staircase")
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{staircase['id']}/replace",
        json={"floor_number": floor["floor_number"], "new_type": "kitchen"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "can't be replaced" in r.json()["detail"]


def test_replace_room_rejects_structural_target_type(client, auth_headers, project, floor_plan):
    floor, living_room = _floor_with_room_type(floor_plan["plan_data"], "living_room")
    r = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{living_room['id']}/replace",
        json={"floor_number": floor["floor_number"], "new_type": "veranda"},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "placed automatically" in r.json()["detail"]


def test_replace_room_bathroom_to_kitchen_when_large_enough():
    """Unit-level test of the geometry function directly, for the exact
    scenario named in the feature request: a bathroom roomy enough to meet
    a kitchen's minimum size converts cleanly, geometry untouched."""
    outline = {"x": 0, "y": 0, "width": 40, "length": 40}
    bathroom = {
        "id": "bathroom_1", "type": "bathroom", "label": "Bathroom", "zone": "SE",
        "x": 0, "y": 0, "width": 8, "length": 10, "area": 80, "below_min_size": False, "furniture": [],
    }
    other = {
        "id": "living_room_1", "type": "living_room", "label": "Living Room", "zone": "N",
        "x": 8, "y": 0, "width": 20, "length": 20, "area": 400, "below_min_size": False, "furniture": [],
    }
    floor = {"outline": outline, "rooms": [bathroom, other], "doors": [], "windows": [], "walls": []}

    new_room, warnings = fpg.replace_room(floor, "bathroom_1", "kitchen", "north", False)

    assert new_room["type"] == "kitchen"
    assert new_room["label"] == "Kitchen"
    assert new_room["x"] == 0 and new_room["y"] == 0
    assert new_room["width"] == 8 and new_room["length"] == 10
    assert {t["type"] for t in new_room["furniture"]} == {"l_shape_counter", "sink", "stove", "refrigerator"}
    assert isinstance(warnings, list)
    assert fpg.rooms_are_connected([r["id"] for r in floor["rooms"]], floor["doors"])


def test_replace_room_too_small_raises_clear_error_and_leaves_floor_untouched():
    """A bathroom sized at its own minimum can't become a kitchen (which
    needs a bigger footprint) -- must be rejected with a clear reason
    instead of silently applying an undersized room."""
    outline = {"x": 0, "y": 0, "width": 40, "length": 40}
    bathroom = {
        "id": "bathroom_1", "type": "bathroom", "label": "Bathroom", "zone": "SE",
        "x": 0, "y": 0, "width": 5, "length": 7, "area": 35, "below_min_size": False, "furniture": [],
    }
    floor = {"outline": outline, "rooms": [bathroom], "doors": [], "windows": [], "walls": []}

    try:
        fpg.replace_room(floor, "bathroom_1", "kitchen", "north", False)
        assert False, "expected a ValueError for a room too small to become a kitchen"
    except ValueError as exc:
        assert "too small" in str(exc)
    # a rejected attempt should never partially mutate the floor
    assert floor["rooms"] == [bathroom]


def test_replace_room_warns_when_no_exterior_wall_for_wet_room():
    """A room with no exterior wall access converting into a wet room type
    should still succeed (never block on ventilation/plumbing alone) but
    surface a clear warning about it."""
    outline = {"x": 0, "y": 0, "width": 40, "length": 40}
    # fully interior room, surrounded on every side by other rooms
    interior = {
        "id": "study_1", "type": "study_room", "label": "Study Room", "zone": "C",
        "x": 10, "y": 10, "width": 8, "length": 10, "area": 80, "below_min_size": False, "furniture": [],
    }
    north = {"id": "n", "type": "bedroom", "label": "Bedroom", "zone": "N", "x": 10, "y": 0, "width": 8, "length": 10, "area": 80, "below_min_size": False, "furniture": []}
    south = {"id": "s", "type": "bedroom", "label": "Bedroom", "zone": "S", "x": 10, "y": 20, "width": 8, "length": 10, "area": 80, "below_min_size": False, "furniture": []}
    west = {"id": "w", "type": "bedroom", "label": "Bedroom", "zone": "W", "x": 0, "y": 10, "width": 10, "length": 10, "area": 100, "below_min_size": False, "furniture": []}
    east = {"id": "e", "type": "bedroom", "label": "Bedroom", "zone": "E", "x": 18, "y": 10, "width": 22, "length": 10, "area": 220, "below_min_size": False, "furniture": []}
    floor = {"outline": outline, "rooms": [interior, north, south, west, east], "doors": [], "windows": [], "walls": []}

    new_room, warnings = fpg.replace_room(floor, "study_1", "bathroom", "north", False)
    assert new_room["type"] == "bathroom"
    assert any("plumbing" in w for w in warnings)


def test_replace_room_across_room_sizes(client, auth_headers, project):
    """Smoke-test across a spread of plot/room sizes: converting the living
    room into a study room should either succeed cleanly or be rejected with
    a 400 (if the grid-slicer happened to make this particular living room
    too thin) -- but must never disconnect the house or leave an overlap."""
    sweeps = (
        {"plot_length": 55, "plot_width": 40, "bedrooms": 2, "floors": 1, "bathrooms": 2},
        {"plot_length": 65, "plot_width": 48, "bedrooms": 4, "floors": 1, "bathrooms": 3},
        {"plot_length": 80, "plot_width": 55, "bedrooms": 3, "floors": 2, "bathrooms": 3},
    )
    for overrides in sweeps:
        plan = _generate(client, auth_headers, project["id"], **overrides)
        floor, living_room = _floor_with_room_type(plan["plan_data"], "living_room")
        url = f"/api/v1/projects/{project['id']}/floorplans/{plan['id']}/rooms/{living_room['id']}/replace"

        r = client.put(url, json={"floor_number": floor["floor_number"], "new_type": "study_room"}, headers=auth_headers)
        assert r.status_code in (200, 400), r.text
        if r.status_code != 200:
            continue
        new_floor = next(
            f for f in r.json()["floor_plan"]["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"]
        )
        assert fpg.rooms_are_connected([rm["id"] for rm in new_floor["rooms"]], new_floor["doors"])
        for a_idx, a in enumerate(new_floor["rooms"]):
            a_rect = {"x": a["x"], "y": a["y"], "w": a["width"], "l": a["length"]}
            for b in new_floor["rooms"][a_idx + 1:]:
                b_rect = {"x": b["x"], "y": b["y"], "w": b["width"], "l": b["length"]}
                assert not geo.rects_overlap(a_rect, b_rect, tolerance=0.05), (a["id"], b["id"])
