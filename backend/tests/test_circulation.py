"""Circulation: a private room must not be the only way through to another
room. Doors form a spanning tree, so the path between any two rooms is
unique -- the route through the house IS the tree path, no search needed."""
from collections import deque

import pytest

from app.schemas.requirement import RequirementCreate
from app.services.floorplan_generator import generate_floor_plan

PRIVATE = {"bedroom", "master_bedroom", "guest_room", "servant_room", "bathroom", "accessible_bathroom"}
BEDROOMS = {"bedroom", "master_bedroom", "guest_room"}
BATHROOMS = {"bathroom", "accessible_bathroom"}


def _routes_through_private(floor):
    """[(room_label, [private rooms walked through])] for this floor. An
    ensuite -- a bathroom whose single intermediate is its own bedroom -- is
    correct architecture and excluded."""
    rooms = {r["id"]: r for r in floor["rooms"]}
    adj = {rid: [] for rid in rooms}
    entrance = None
    for d in floor["doors"]:
        if d["type"] == "main_entrance":
            entrance = d["room_id"]
        elif d["room_id"] in adj and d["connects_to"] in adj:
            adj[d["room_id"]].append(d["connects_to"])
            adj[d["connects_to"]].append(d["room_id"])
    if entrance is None:
        # Upper floor of a duplex: arrival is via the staircase.
        entrance = next((rid for rid, r in rooms.items() if r["type"] == "staircase"), None)
    if entrance is None:
        return []

    parent = {entrance: None}
    queue = deque([entrance])
    while queue:
        cur = queue.popleft()
        for nxt in adj[cur]:
            if nxt not in parent:
                parent[nxt] = cur
                queue.append(nxt)

    bad = []
    for rid, room in rooms.items():
        if rid == entrance or rid not in parent:
            continue
        through, hop = [], parent[rid]
        while hop is not None:
            if rooms[hop]["type"] in PRIVATE:
                through.append(rooms[hop]["label"])
            hop = parent[hop]
        if not through:
            continue
        if room["type"] in BATHROOMS and len(through) == 1 and rooms[parent[rid]]["type"] in BEDROOMS:
            continue  # ensuite
        bad.append((room["label"], through))
    return bad


# These six once split into pass/fail: the 30x40 and 35x50 plans put the
# kitchen behind the master bedroom and no door ordering could rescue them,
# because a band of nothing but private rooms spans the floor's full width
# and walls the house in two. `_repair_wall_bands` now trades a private room
# out of such a band, and all six pass.
SCENARIOS = [
    pytest.param(dict(plot_length=40, plot_width=30, facing="north", bedrooms=2, bathrooms=2, floors=1)),
    pytest.param(dict(plot_length=55, plot_width=40, facing="north", bedrooms=3, bathrooms=3, floors=2)),
    pytest.param(dict(plot_length=45, plot_width=25, facing="west", bedrooms=2, bathrooms=2, floors=2)),
    pytest.param(dict(plot_length=45, plot_width=22, facing="north", bedrooms=3, bathrooms=3, floors=3)),
    pytest.param(dict(plot_length=60, plot_width=50, facing="south", bedrooms=4, bathrooms=4, floors=2)),
    pytest.param(dict(plot_length=50, plot_width=35, facing="north", bedrooms=3, bathrooms=3, floors=1,
                      vastu_compliant=True)),
]


@pytest.mark.parametrize("overrides", SCENARIOS)
def test_kitchen_and_living_are_never_reached_through_a_private_room(overrides):
    """The rooms the whole household shares must never sit behind someone's
    bedroom or a bathroom. This is the regression that motivated weighting
    the door tree by `CIRCULATION_RANK` -- before that, 37% of all rooms were
    only reachable this way, including kitchens behind master bedrooms."""
    plan, _ = generate_floor_plan(RequirementCreate(**overrides))
    shared = {"kitchen", "living_room", "dining_room", "pooja_room", "staircase"}
    offenders = [
        (label, through)
        for floor in plan["floors"]
        for label, through in _routes_through_private(floor)
        if any(r["label"] == label and r["type"] in shared for r in floor["rooms"])
    ]
    assert not offenders, f"shared rooms reached only through a private room: {offenders}"

# The matching guarantee for attached bathrooms -- that an ensuite keeps its
# door to the parent room it was carved out of -- is covered end-to-end by
# test_attached_bathroom.py::test_add_attached_bathroom_shrinks_room_and_adds_bathroom.
# That test is what caught `_doorway_cost` initially ranking the ensuite pair
# worst of all (private + bathroom) and sending its only door elsewhere.


@pytest.mark.parametrize("overrides", SCENARIOS)
def test_shared_rooms_are_never_split_into_islands(overrides):
    """The invariant `_repair_wall_bands` exists to hold: with every private
    room taken out of the picture, the shared rooms left on a floor still
    reach each other. More than one island means a band of bedrooms and
    bathrooms has cut the floor in two, which is what puts a kitchen behind
    someone's bedroom."""
    from app.services.floorplan_generator import _public_islands, RoomInstance

    plan, _ = generate_floor_plan(RequirementCreate(**overrides))
    for floor in plan["floors"]:
        rooms = [
            RoomInstance(
                room_id=r["id"], room_type=r["type"], label=r["label"], weight=0, priority=0,
                zones=[], habitable=True, min_w=0, min_l=0, furniture=[], floor_index=0,
                rect={"x": r["x"], "y": r["y"], "w": r["width"], "l": r["length"]},
            )
            for r in floor["rooms"]
        ]
        assert _public_islands(rooms) <= 1, (
            f"floor {floor['floor_number']} shared rooms split into islands: "
            f"{[r['label'] for r in floor['rooms']]}"
        )
