from app.services import floorplan_generator as fpg
from app.services import geometry as geo

from tests.conftest import requirement_payload


def _floor_with_bedroom(plan_data: dict) -> tuple[dict, dict]:
    """Duplex-mode plans (the default fixture) put bedrooms on an upper
    floor, not the ground floor -- search every floor for one."""
    for floor in plan_data["floors"]:
        bedroom = next((r for r in floor["rooms"] if r["type"] in ("bedroom", "master_bedroom")), None)
        if bedroom:
            return floor, bedroom
    raise AssertionError("no bedroom found on any floor of this plan")


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


def test_add_attached_bathroom_shrinks_room_and_adds_bathroom(client, auth_headers, project, floor_plan):
    floor, bedroom = _floor_with_bedroom(floor_plan["plan_data"])
    original_area = bedroom["width"] * bedroom["length"]

    r = client.post(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{bedroom['id']}/attached-bathroom",
        json={"floor_number": floor["floor_number"]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    plan = body["floor_plan"]
    new_floor = next(f for f in plan["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])

    new_bedroom = next(rm for rm in new_floor["rooms"] if rm["id"] == bedroom["id"])
    bath = next(rm for rm in new_floor["rooms"] if rm.get("attached_to") == bedroom["id"])

    assert bath["type"] == "bathroom"
    assert new_bedroom["attached_bathroom_id"] == bath["id"]
    assert new_bedroom["width"] * new_bedroom["length"] < original_area
    assert new_bedroom["furniture"] == []

    # bathroom carved out is a strict rectangular sub-piece: combined area
    # equals the original room's area (nothing lost/gained by the split)
    combined = new_bedroom["width"] * new_bedroom["length"] + bath["width"] * bath["length"]
    assert abs(combined - original_area) < 0.5

    # total built-up area is conserved (splitting one room into two doesn't
    # create or destroy floor area), but cost/BOQ/FAR were still recomputed
    assert abs(plan["total_built_up_area"] - floor_plan["total_built_up_area"]) < 0.5
    assert plan["plan_data"]["meta"]["cost_estimate"]["total_built_up_area"] == plan["total_built_up_area"]
    assert "boq" in plan["plan_data"]["meta"]
    assert "far" in plan["plan_data"]["meta"]

    # a real door connects the new bathroom to its parent room, and every
    # room on the floor is still reachable
    assert any(
        {d.get("room_id"), d.get("connects_to")} == {bedroom["id"], bath["id"]}
        for d in new_floor["doors"] if d["type"] == "internal"
    )
    assert fpg.rooms_are_connected([rm["id"] for rm in new_floor["rooms"]], new_floor["doors"])

    # walls were rebuilt to include the new partition
    assert any(bath["id"] in w.get("between", []) for w in new_floor["walls"])


def test_add_attached_bathroom_rejects_already_present(client, auth_headers, project, floor_plan):
    floor, bedroom = _floor_with_bedroom(floor_plan["plan_data"])
    url = f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{bedroom['id']}/attached-bathroom"
    payload = {"floor_number": floor["floor_number"]}

    r1 = client.post(url, json=payload, headers=auth_headers)
    assert r1.status_code == 200, r1.text

    r2 = client.post(url, json=payload, headers=auth_headers)
    assert r2.status_code == 400
    assert "already has" in r2.json()["detail"]


def test_add_attached_bathroom_rejects_ineligible_room_type(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    kitchen = next(r for r in floor["rooms"] if r["type"] == "kitchen")
    r = client.post(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{kitchen['id']}/attached-bathroom",
        json={"floor_number": floor["floor_number"]},
        headers=auth_headers,
    )
    assert r.status_code == 400
    assert "suitable" in r.json()["detail"]


def test_add_attached_bathroom_rejects_unknown_room(client, auth_headers, project, floor_plan):
    floor = floor_plan["plan_data"]["floors"][0]
    r = client.post(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/not_a_real_room/attached-bathroom",
        json={"floor_number": floor["floor_number"]},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_remove_attached_bathroom_restores_space(client, auth_headers, project, floor_plan):
    floor, bedroom = _floor_with_bedroom(floor_plan["plan_data"])
    original = {"x": bedroom["x"], "y": bedroom["y"], "width": bedroom["width"], "length": bedroom["length"]}
    url = f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{bedroom['id']}/attached-bathroom"

    add_resp = client.post(url, json={"floor_number": floor["floor_number"]}, headers=auth_headers)
    assert add_resp.status_code == 200, add_resp.text

    del_resp = client.delete(url, params={"floor_number": floor["floor_number"]}, headers=auth_headers)
    assert del_resp.status_code == 200, del_resp.text
    body = del_resp.json()
    plan = body["floor_plan"]
    new_floor = next(f for f in plan["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])

    restored = next(rm for rm in new_floor["rooms"] if rm["id"] == bedroom["id"])
    assert restored["x"] == original["x"]
    assert restored["y"] == original["y"]
    assert restored["width"] == original["width"]
    assert restored["length"] == original["length"]
    assert not restored.get("attached_bathroom_id")
    assert not any(rm.get("attached_to") == bedroom["id"] for rm in new_floor["rooms"])
    assert body["warnings"] == []

    # total area returns to exactly what it was before the bathroom was ever added
    assert abs(plan["total_built_up_area"] - floor_plan["total_built_up_area"]) < 0.5


def test_remove_attached_bathroom_rejects_when_none_present(client, auth_headers, project, floor_plan):
    floor, bedroom = _floor_with_bedroom(floor_plan["plan_data"])
    r = client.delete(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{bedroom['id']}/attached-bathroom",
        params={"floor_number": floor["floor_number"]},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_remove_attached_bathroom_warns_when_manually_resized(client, auth_headers, project, floor_plan):
    """After adding an attached bathroom, if the user then manually resizes
    either room via the normal room-layout editor, the clean strip no longer
    tiles exactly -- removal should still succeed (never block a removal) but
    warn that the space couldn't be automatically reclaimed."""
    floor, bedroom = _floor_with_bedroom(floor_plan["plan_data"])
    url = f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms/{bedroom['id']}/attached-bathroom"

    add_resp = client.post(url, json={"floor_number": floor["floor_number"]}, headers=auth_headers)
    assert add_resp.status_code == 200, add_resp.text
    plan = add_resp.json()["floor_plan"]
    new_floor = next(f for f in plan["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"])
    new_bedroom = next(rm for rm in new_floor["rooms"] if rm["id"] == bedroom["id"])
    bath = next(rm for rm in new_floor["rooms"] if rm.get("attached_to") == bedroom["id"])

    # Shrink the bedroom slightly from its far edge (away from the bathroom)
    # so the bedroom/bathroom pair no longer forms one exact rectangle.
    shrink = min(1.0, new_bedroom["width"] * 0.1)
    resize_payload = {
        "floor_number": floor["floor_number"],
        "rooms": {new_bedroom["id"]: {
            "x": new_bedroom["x"], "y": new_bedroom["y"],
            "width": new_bedroom["width"] - shrink, "length": new_bedroom["length"],
        }},
    }
    resize_resp = client.put(
        f"/api/v1/projects/{project['id']}/floorplans/{floor_plan['id']}/rooms",
        json=resize_payload, headers=auth_headers,
    )
    assert resize_resp.status_code == 200, resize_resp.text

    del_resp = client.delete(url, params={"floor_number": floor["floor_number"]}, headers=auth_headers)
    assert del_resp.status_code == 200, del_resp.text
    del_body = del_resp.json()
    assert del_body["warnings"] != []
    del_floor = next(
        f for f in del_body["floor_plan"]["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"]
    )
    assert not any(rm["id"] == bath["id"] for rm in del_floor["rooms"])


def test_add_attached_bathroom_no_valid_edge_raises_clear_error():
    """Unit-level test of the geometry function directly (bypassing the
    generator's layout heuristics for a deterministic setup): a bedroom sized
    exactly at its own minimum, with no room to give up any depth without
    dropping below that minimum on every side, must be rejected with a clear
    reason rather than silently producing an invalid layout."""
    outline = {"x": 0, "y": 0, "width": 40, "length": 40}
    bedroom = {
        "id": "bedroom_1", "type": "bedroom", "label": "Bedroom", "zone": "N",
        "x": 0, "y": 0, "width": 10, "length": 11, "area": 110, "below_min_size": False, "furniture": [],
    }
    floor = {
        "outline": outline,
        "rooms": [bedroom],
        "doors": [],
        "windows": [],
        "walls": [],
    }
    try:
        fpg.add_attached_bathroom(floor, "bedroom_1", "north", False)
        assert False, "expected a ValueError for a room too small to host an attached bathroom"
    except ValueError as exc:
        assert "too small" in str(exc)
    # the floor must be untouched -- a rejected attempt should never partially mutate it
    assert floor["rooms"] == [bedroom]


def test_add_attached_bathroom_across_room_sizes(client, auth_headers, project):
    """Smoke-test add+remove across a spread of plot/room sizes to catch
    regressions specific to particular room dimensions."""
    sweeps = (
        {"plot_length": 55, "plot_width": 40, "bedrooms": 2, "floors": 1, "bathrooms": 2, "balconies": 0,
         "has_pooja_room": False, "has_utility_room": False},
        {"plot_length": 65, "plot_width": 48, "bedrooms": 4, "floors": 1, "bathrooms": 3, "balconies": 1},
        {"plot_length": 80, "plot_width": 55, "bedrooms": 3, "floors": 1, "bathrooms": 3, "balconies": 2},
    )
    for overrides in sweeps:
        plan = _generate(client, auth_headers, project["id"], **overrides)
        floor, bedroom = _floor_with_bedroom(plan["plan_data"])
        url = f"/api/v1/projects/{project['id']}/floorplans/{plan['id']}/rooms/{bedroom['id']}/attached-bathroom"

        r = client.post(url, json={"floor_number": floor["floor_number"]}, headers=auth_headers)
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            new_floor = next(
                f for f in r.json()["floor_plan"]["plan_data"]["floors"] if f["floor_number"] == floor["floor_number"]
            )
            assert fpg.rooms_are_connected([rm["id"] for rm in new_floor["rooms"]], new_floor["doors"])
            for a_idx, a in enumerate(new_floor["rooms"]):
                a_rect = {"x": a["x"], "y": a["y"], "w": a["width"], "l": a["length"]}
                for b in new_floor["rooms"][a_idx + 1:]:
                    b_rect = {"x": b["x"], "y": b["y"], "w": b["width"], "l": b["length"]}
                    assert not geo.rects_overlap(a_rect, b_rect, tolerance=0.05), (a["id"], b["id"])

            del_resp = client.delete(url, params={"floor_number": floor["floor_number"]}, headers=auth_headers)
            assert del_resp.status_code == 200, del_resp.text
