"""Rule-based "AI" design-suggestion engine.

Produces structured, human-readable suggestions from the requirement, the
validation results and the generated plan's statistics. This is a
deterministic heuristic engine (no external model call) so it works fully
offline; it is isolated behind this module so a real LLM/ML call could be
swapped in later without touching the API layer.
"""
import math

from app.schemas.requirement import RequirementCreate
from app.services.cost_estimator import estimate_cost


def build_suggestions(
    req: RequirementCreate,
    warnings: list[str],
    plan: dict,
    total_built_up_area: float,
) -> list[dict]:
    suggestions: list[dict] = []

    for warning in warnings:
        suggestions.append({"category": "validation", "priority": "high", "message": warning})

    cost = estimate_cost(total_built_up_area, req.budget)
    if req.budget:
        if cost["within_budget"]:
            suggestions.append({
                "category": "budget", "priority": "medium",
                "message": f"Your budget comfortably supports the '{cost['recommended_tier']}' finish tier "
                           f"(~{cost['recommended_cost']:,.0f}) for the ~{total_built_up_area:,.0f} sqft built-up area.",
            })
        else:
            cheapest = min(cost["tier_estimates"].values())
            suggestions.append({
                "category": "budget", "priority": "high",
                "message": f"Even the economy tier (~{cheapest:,.0f}) exceeds your budget of {req.budget:,.0f}. "
                           "Consider reducing built-up area, floors, or room count.",
            })
    else:
        suggestions.append({
            "category": "budget", "priority": "low",
            "message": f"No budget specified. Estimated construction cost ranges from "
                       f"{min(cost['tier_estimates'].values()):,.0f} (economy) to "
                       f"{max(cost['tier_estimates'].values()):,.0f} (luxury) for {total_built_up_area:,.0f} sqft.",
        })

    recommended_bedrooms = max(1, math.ceil(req.family_members / 2))
    if req.bedrooms > recommended_bedrooms + 1:
        suggestions.append({
            "category": "layout", "priority": "low",
            "message": f"{req.bedrooms} bedrooms is generous for {req.family_members} family members — "
                       "consider a home office, guest room or larger living area instead.",
        })

    if req.vastu_compliant:
        suggestions.append({
            "category": "vastu", "priority": "medium",
            "message": "Kitchen placed toward South-East and pooja room toward North-East per Vastu; "
                       "master bedroom oriented South-West for stability.",
        })
    else:
        suggestions.append({
            "category": "vastu", "priority": "low",
            "message": "Vastu preference not enabled — rooms are placed purely for functional adjacency "
                       "(kitchen near dining, bedrooms clustered for privacy).",
        })

    for floor in plan["floors"]:
        undersized = [r["label"] for r in floor["rooms"] if r.get("below_min_size")]
        if undersized:
            suggestions.append({
                "category": "layout", "priority": "medium",
                "message": f"On {floor['label']}, these rooms are tighter than the recommended minimum size: "
                           f"{', '.join(undersized)}. Consider a larger plot, fewer rooms, or an additional floor.",
            })

    if req.cars >= 2 and req.plot_width < 22:
        suggestions.append({
            "category": "parking", "priority": "medium",
            "message": "For 2+ cars on a narrow plot, a stack/tandem parking layout or basement parking "
                       "would use space more efficiently than side-by-side open parking.",
        })

    if req.floors == 1 and req.bedrooms >= 4:
        suggestions.append({
            "category": "layout", "priority": "low",
            "message": "4+ bedrooms on a single floor requires a large footprint — adding a second floor "
                       "would reduce ground coverage and leave more open/garden space.",
        })

    if not req.has_utility_room and req.family_members >= 4:
        suggestions.append({
            "category": "layout", "priority": "low",
            "message": "A dedicated utility/wash area is recommended for households of 4+ to keep laundry "
                       "out of the kitchen.",
        })

    return suggestions
