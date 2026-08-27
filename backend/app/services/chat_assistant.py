"""A house-building Q&A chat assistant, backed by an NVIDIA NIM-hosted LLM
(OpenAI-compatible chat completions API). This is the one place in the app
that calls an external AI API -- everything else (floor-plan generation,
"AI suggestions", cost estimation) is deterministic rule-based geometry/logic,
by design (see CLAUDE.md). Isolated here so it can be swapped for a different
provider without touching the rest of the app.
"""
import httpx

from app.core.config import settings
from app.models.floorplan import FloorPlan
from app.models.requirement import Requirement
from app.schemas.chat import ChatMessage

SYSTEM_PROMPT = (
    "You are a helpful, knowledgeable assistant embedded in a home floor-plan design app. "
    "Answer questions about house-building and home-design topics: room sizing and layout, "
    "Vastu Shastra principles, construction materials and costs, plot setbacks and floor-area "
    "ratio, parking and staircase planning, budgeting, and general home-buying/building advice. "
    "If the user includes details about their specific project below, ground your answer in "
    "those specifics rather than generic advice. Keep answers concise and practical (a few "
    "sentences or a short list), not long essays. "
    "If a question has nothing to do with houses, home-building, or the app itself, politely "
    "say that's outside what you can help with here and steer back to house-related topics."
)


class ChatAssistantError(Exception):
    """Raised for any failure calling the NIM API; the caller maps this to an HTTP error."""


class ChatNotConfiguredError(ChatAssistantError):
    """Raised when NVIDIA_NIM_API_KEY isn't set -- distinct from a request failure so the
    API layer can return 503 (feature off) rather than 502 (upstream call failed)."""


def _project_context(requirement: Requirement | None, floor_plan: FloorPlan | None) -> str | None:
    if requirement is None:
        return None
    lines = [
        f"- Plot: {requirement.plot_length} x {requirement.plot_width} ft, facing {requirement.facing}",
        f"- Family size: {requirement.family_members}, {requirement.bedrooms} bedroom(s), "
        f"{requirement.bathrooms} bathroom(s), {requirement.floors} floor(s)",
        f"- Budget: {requirement.budget:,.0f}" if requirement.budget else "- Budget: not specified",
        f"- Vastu compliant: {'yes' if requirement.vastu_compliant else 'no'}",
    ]
    if floor_plan is not None:
        lines.append(
            f"- Latest generated plan: {floor_plan.total_built_up_area:,.0f} sqft built-up, "
            f"estimated cost {floor_plan.estimated_cost:,.0f} (version {floor_plan.version})"
        )
        room_labels = [
            room.get("label", room.get("type", "room"))
            for floor in floor_plan.plan_data.get("floors", [])
            for room in floor.get("rooms", [])
        ]
        if room_labels:
            lines.append(f"- Rooms in the plan: {', '.join(room_labels)}")
    return "The user's current project:\n" + "\n".join(lines)


def get_chat_reply(
    messages: list[ChatMessage],
    requirement: Requirement | None = None,
    floor_plan: FloorPlan | None = None,
) -> str:
    if not settings.NVIDIA_NIM_API_KEY:
        raise ChatNotConfiguredError("Chat assistant is not configured (missing NVIDIA_NIM_API_KEY).")

    system_content = SYSTEM_PROMPT
    context = _project_context(requirement, floor_plan)
    if context:
        system_content += "\n\n" + context

    payload = {
        "model": settings.NVIDIA_NIM_MODEL,
        "messages": [{"role": "system", "content": system_content}]
        + [{"role": m.role, "content": m.content} for m in messages],
        "temperature": 0.4,
        "max_tokens": 500,
    }

    try:
        resp = httpx.post(
            f"{settings.NVIDIA_NIM_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.NVIDIA_NIM_API_KEY}"},
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise ChatAssistantError("The chat assistant timed out -- try again.") from exc
    except httpx.HTTPStatusError as exc:
        raise ChatAssistantError(f"Chat assistant request failed ({exc.response.status_code}).") from exc
    except httpx.HTTPError as exc:
        raise ChatAssistantError("Could not reach the chat assistant.") from exc

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ChatAssistantError("Chat assistant returned an unexpected response.") from exc
