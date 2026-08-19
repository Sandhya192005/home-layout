from app.utils.constants import COST_TIERS


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
