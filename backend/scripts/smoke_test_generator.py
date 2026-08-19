"""Ad-hoc smoke test for the floor-plan generator — no DB required.

Run: python scripts/smoke_test_generator.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.requirement import RequirementCreate
from app.services.floorplan_generator import generate_floor_plan
from app.services.validation import validate_requirement

SCENARIOS = [
    dict(
        name="Small single-floor vastu home",
        plot_length=40, plot_width=30, facing="north", family_members=4,
        bedrooms=2, bathrooms=2, cars=1, two_wheelers=1, floors=1,
        budget=2_500_000, vastu_compliant=True,
    ),
    dict(
        name="Large 2-floor non-vastu home",
        plot_length=60, plot_width=45, facing="east", family_members=6,
        bedrooms=4, bathrooms=4, cars=2, two_wheelers=2, floors=2,
        budget=8_000_000, vastu_compliant=False, has_pooja_room=True,
        has_study_room=True, additional_rooms=["guest_room"],
    ),
    dict(
        name="Narrow plot, south facing, 3 floors",
        plot_length=70, plot_width=22, facing="south", family_members=8,
        bedrooms=5, bathrooms=5, cars=2, two_wheelers=3, floors=3,
        budget=12_000_000, vastu_compliant=True, balconies=3,
    ),
    dict(
        name="Tiny plot stress test",
        plot_length=20, plot_width=16, facing="west", family_members=2,
        bedrooms=1, bathrooms=1, cars=0, two_wheelers=1, floors=1,
        budget=500_000, vastu_compliant=False,
    ),
]

for scenario in SCENARIOS:
    name = scenario.pop("name")
    print(f"\n=== {name} ===")
    req = RequirementCreate(**scenario)
    errors, warnings = validate_requirement(req)
    print("errors:", errors)
    print("warnings:", warnings)
    if errors:
        continue
    plan, total_area = generate_floor_plan(req)
    print("total_built_up_area:", total_area)
    for floor in plan["floors"]:
        room_summary = [(r["type"], r["zone"], r["width"], r["length"], r["below_min_size"]) for r in floor["rooms"]]
        print(f"  {floor['label']}: {len(floor['rooms'])} rooms, {len(floor['walls'])} walls, "
              f"{len(floor['doors'])} doors, {len(floor['windows'])} windows, "
              f"parking={'yes' if floor['parking'] else 'no'}")
        for rs in room_summary:
            flag = " <<< BELOW MIN" if rs[4] else ""
            print(f"    {rs[0]:15s} zone={rs[1]:3s} {rs[2]:5.1f} x {rs[3]:5.1f} ft{flag}")

print("\nOK - full JSON sample for scenario 1 below:\n")
req = RequirementCreate(plot_length=40, plot_width=30, facing="north", family_members=4,
                         bedrooms=2, bathrooms=2, cars=1, two_wheelers=1, floors=1,
                         budget=2_500_000, vastu_compliant=True)
plan, total_area = generate_floor_plan(req)
print(json.dumps(plan, indent=2)[:2000])
