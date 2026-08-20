"""Validates a customer requirement before floor-plan generation is attempted.

Returns (errors, warnings). Errors block generation; warnings are informational
and are surfaced to the client alongside the generated plan.
"""
import math

from app.schemas.requirement import RequirementCreate
from app.utils.constants import (
    CAR_PARKING_SIZE,
    COST_TIERS,
    MAX_GROUND_COVERAGE,
    SETBACK_RULES,
    TWO_WHEELER_PARKING_SIZE,
)


def _setback(dimension: float, kind: str) -> float:
    rule = SETBACK_RULES[kind]
    return min(max(dimension * rule["fraction"], rule["min"]), rule["max"])


def _estimate_parking_area_carved_from_footprint(req: RequirementCreate, buildable_width: float) -> float:
    """Mirrors the generator's parking-carve logic: parking only eats into the roofed
    footprint when the vehicle depth exceeds the front setback."""
    if req.cars <= 0 and req.two_wheelers <= 0:
        return 0.0
    front_dim = req.plot_length if req.facing in ("north", "south") else req.plot_width
    front_sb = _setback(front_dim, "front")
    depth_needed = CAR_PARKING_SIZE["l"] if req.cars > 0 else TWO_WHEELER_PARKING_SIZE["l"]
    extra_depth = max(0.0, depth_needed - front_sb)
    return extra_depth * buildable_width


def estimate_minimum_plot_area(req: RequirementCreate) -> float:
    """Rough minimum buildable-area requirement (sqft) for the requested program,
    used to sanity check the plot size before running the full layout engine."""
    from app.utils.constants import ROOM_LIBRARY

    room_counts = _room_program(req)
    total = 0.0
    for room_type, count in room_counts.items():
        meta = ROOM_LIBRARY[room_type]
        total += meta["min_w"] * meta["min_l"] * count
    return total


def _room_program(req: RequirementCreate) -> dict[str, int]:
    counts: dict[str, int] = {}
    counts["master_bedroom"] = 1
    if req.bedrooms > 1:
        counts["bedroom"] = req.bedrooms - 1
    counts["bathroom"] = req.bathrooms
    if req.wheelchair_accessible and counts["bathroom"] > 0:
        counts["bathroom"] -= 1
        counts["accessible_bathroom"] = 1
    counts["kitchen"] = 1
    if req.has_living_room:
        counts["living_room"] = 1
    if req.has_dining_room:
        counts["dining_room"] = 1
    if req.has_pooja_room:
        counts["pooja_room"] = 1
    if req.has_study_room:
        counts["study_room"] = 1
    if req.has_utility_room:
        counts["utility"] = 1
    if req.balconies:
        counts["balcony"] = req.balconies
    for extra in req.additional_rooms:
        counts[extra] = counts.get(extra, 0) + 1
    if req.floors > 1:
        counts["staircase"] = 1
    return counts


def validate_requirement(req: RequirementCreate) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if req.plot_length < 15 or req.plot_width < 12:
        errors.append(
            f"Plot dimensions {req.plot_length}x{req.plot_width} ft are too small to build a functional house. "
            "Minimum recommended is 15x12 ft."
        )

    plot_area = req.plot_length * req.plot_width
    if req.facing in ("north", "south"):
        buildable_length = max(req.plot_length - _setback(req.plot_length, "front") - _setback(req.plot_length, "rear"), 0)
        buildable_width = max(req.plot_width - 2 * _setback(req.plot_width, "side"), 0)
    else:
        buildable_width = max(req.plot_width - _setback(req.plot_width, "front") - _setback(req.plot_width, "rear"), 0)
        buildable_length = max(req.plot_length - 2 * _setback(req.plot_length, "side"), 0)
    buildable_area_per_floor = buildable_length * buildable_width

    if buildable_area_per_floor <= 0:
        errors.append("Mandatory setbacks consume the entire plot; no buildable area remains.")
        return errors, warnings

    min_required = estimate_minimum_plot_area(req)
    parking_carve = _estimate_parking_area_carved_from_footprint(req, buildable_width)
    ground_floor_area = max(buildable_area_per_floor - parking_carve, 0)
    max_footprint_across_floors = ground_floor_area + buildable_area_per_floor * max(req.floors - 1, 0)

    if parking_carve > 0 and parking_carve > buildable_area_per_floor * 0.4:
        warnings.append(
            "Parking for the requested vehicles needs more depth than the front setback provides, "
            "consuming a large share of the ground-floor footprint. Consider a wider plot frontage, "
            "fewer vehicles, or stacked/basement parking."
        )

    if min_required > max_footprint_across_floors:
        if req.floors < 3:
            errors.append(
                f"The requested rooms need at least ~{math.ceil(min_required)} sqft, but only "
                f"~{math.floor(max_footprint_across_floors)} sqft is buildable across {req.floors} floor(s) "
                "after setbacks. Increase the plot size, reduce the room count, or add another floor."
            )
        else:
            errors.append(
                f"The requested rooms need at least ~{math.ceil(min_required)} sqft, but only "
                f"~{math.floor(max_footprint_across_floors)} sqft is buildable across {req.floors} floor(s). "
                "Increase the plot size or reduce the room count."
            )

    if buildable_area_per_floor > plot_area * MAX_GROUND_COVERAGE:
        warnings.append(
            "Buildable ground-floor area exceeds typical local ground-coverage norms "
            f"({int(MAX_GROUND_COVERAGE * 100)}%); confirm against local municipal by-laws."
        )

    recommended_bedrooms = max(1, math.ceil(req.family_members / 2))
    if req.bedrooms < recommended_bedrooms:
        warnings.append(
            f"With {req.family_members} family members, {recommended_bedrooms}+ bedrooms is recommended; "
            f"only {req.bedrooms} requested."
        )

    if req.bathrooms < math.ceil(req.bedrooms / 2):
        warnings.append(
            f"{req.bathrooms} bathroom(s) may be insufficient for {req.bedrooms} bedrooms; "
            f"consider at least {math.ceil(req.bedrooms / 2)}."
        )

    if req.floors > 1 and req.bedrooms <= 1:
        warnings.append("Multiple floors requested but only one bedroom — a single floor may suffice.")

    # Budget sanity check against the cheapest construction tier.
    built_up_estimate = min(max_footprint_across_floors, min_required * 1.35 if min_required else buildable_area_per_floor)
    min_cost = built_up_estimate * COST_TIERS["economy"]
    if req.budget and req.budget < min_cost:
        warnings.append(
            f"Budget of {req.budget:,.0f} may be insufficient for an estimated {built_up_estimate:,.0f} sqft "
            f"build (economy tier minimum ~{min_cost:,.0f})."
        )

    if req.cars > 0 and req.plot_width < 18:
        warnings.append("Plot frontage under 18 ft may make car parking + driveway tight; consider tandem parking.")

    if req.vastu_compliant and req.plot_length <= 0:
        pass  # placeholder guard, real vastu geometry checks happen during generation

    return errors, warnings
