from app.utils.constants import (
    BOQ_RATES_PER_SQFT,
    CONSTRUCTION_TIMELINE_FIXED_WEEKS,
    CONSTRUCTION_TIMELINE_WEEKS_PER_1000_SQFT,
    COST_TIERS,
    MAX_FAR,
)


def estimate_cost(total_built_up_area: float, budget: float = 0) -> dict:
    """Estimate construction cost across quality tiers and recommend the best-fit tier for the given budget."""
    tier_costs = {tier: round(total_built_up_area * rate) for tier, rate in COST_TIERS.items()}

    recommended_tier = "economy"
    if budget:
        affordable = [t for t, cost in tier_costs.items() if cost <= budget]
        if affordable:
            # pick the highest-quality tier that still fits the budget
            recommended_tier = max(affordable, key=lambda t: COST_TIERS[t])
        else:
            recommended_tier = "economy"

    return {
        "total_built_up_area": round(total_built_up_area, 1),
        "tier_estimates": tier_costs,
        "recommended_tier": recommended_tier,
        "recommended_cost": tier_costs[recommended_tier],
        "within_budget": bool(budget and tier_costs[recommended_tier] <= budget),
    }


def estimate_boq(total_built_up_area: float) -> dict:
    """Rough bill-of-quantities from built-up area using standard Indian
    residential RCC-frame rule-of-thumb ratios -- indicative only, not a
    substitute for a structural engineer's BOQ."""
    return {item: round(total_built_up_area * rate, 1) for item, rate in BOQ_RATES_PER_SQFT.items()}


def estimate_construction_timeline(total_built_up_area: float, floors: int) -> dict:
    """Rough phase-by-phase construction schedule from built-up area and floor
    count. Structure/brickwork scales with floor count since floors are built
    up sequentially; the other phases scale with total area only."""
    area_units = total_built_up_area / 1000.0
    phases = {}
    for phase, rate in CONSTRUCTION_TIMELINE_WEEKS_PER_1000_SQFT.items():
        weeks = CONSTRUCTION_TIMELINE_FIXED_WEEKS.get(phase, 0) + rate * area_units
        if phase == "structure_and_brickwork":
            weeks *= max(floors, 1)
        phases[phase] = round(weeks, 1)
    total_weeks = round(sum(phases.values()), 1)
    return {
        "phases_weeks": phases,
        "total_weeks": total_weeks,
        "total_months": round(total_weeks / 4.345, 1),
    }


def estimate_far(total_built_up_area: float, plot_area: float) -> dict:
    """Floor-area-ratio (total built-up area across all floors / plot area)
    against a typical residential municipal limit."""
    far = round(total_built_up_area / plot_area, 2) if plot_area else 0.0
    return {"far": far, "max_far": MAX_FAR, "exceeds_typical_limit": far > MAX_FAR}
