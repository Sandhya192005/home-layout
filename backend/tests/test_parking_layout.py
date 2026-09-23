import pytest

from app.schemas.requirement import RequirementCreate
from app.services import geometry as geo
from app.services.floorplan_generator import generate_floor_plan, rooms_are_connected


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


NARROW_DEEP_PLOTS = [
    # A deep plot entered from its long side: the front setback comes off the
    # short dimension, so the buildable strip is narrow and a nose-in car's
    # 17ft length does not fit into it.
    dict(plot_length=45, plot_width=22, facing="east", bedrooms=2, bathrooms=2, floors=1),
    dict(plot_length=45, plot_width=22, facing="west", bedrooms=3, bathrooms=3, floors=2),
    dict(plot_length=50, plot_width=24, facing="east", bedrooms=3, bathrooms=2, floors=1),
    dict(plot_length=40, plot_width=20, facing="west", bedrooms=2, bathrooms=2, floors=1),
]


@pytest.mark.parametrize("overrides", NARROW_DEEP_PLOTS)
def test_parking_never_consumes_the_buildable_footprint(overrides):
    """Carving parking out of the footprint must leave a house behind it.

    Nose-in parking needs a car's full 17ft length as depth. On a 45x22
    east-facing plot the buildable strip is only 14ft wide, so that carve
    once left a 2ft sliver for every room: the layout then placed rooms
    outside the floor outline and the floor came out disconnected.
    `compute_parking` now parks parallel to the street when nose-in would
    take more than half the footprint."""
    plan, _ = generate_floor_plan(RequirementCreate(**overrides))
    for floor in plan["floors"]:
        outline = floor["outline"]
        for room in floor["rooms"]:
            assert room["x"] >= outline["x"] - 0.05, f"{room['label']} starts west of the outline"
            assert room["y"] >= outline["y"] - 0.05, f"{room['label']} starts north of the outline"
            assert room["x"] + room["width"] <= outline["x"] + outline["width"] + 0.05, \
                f"{room['label']} runs past the outline's east edge"
            assert room["y"] + room["length"] <= outline["y"] + outline["length"] + 0.05, \
                f"{room['label']} runs past the outline's south edge"

        assert rooms_are_connected([r["id"] for r in floor["rooms"]], floor["doors"]), \
            f"floor {floor['floor_number']} has rooms with no route to the rest of the house"

        parking = floor.get("parking")
        if parking:
            park_rect = {"x": parking["x"], "y": parking["y"], "w": parking["width"], "l": parking["length"]}
            for room in floor["rooms"]:
                overlap = geo.rect_intersect(
                    park_rect, {"x": room["x"], "y": room["y"], "w": room["width"], "l": room["length"]}
                )
                assert not (overlap and overlap["w"] > 0.05 and overlap["l"] > 0.05), \
                    f"parking overlaps {room['label']}"
