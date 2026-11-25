"""Prompt for the site-update LLM call — Phase 5.

The prompt is the main defence against hallucinated ids: it gives the
model the exact records it may reference (materials, suppliers and
tasks of this site/project, with their real ids) and tells it to use
ONLY those ids — never to invent one, and to leave an action out
rather than guess an id. Anything the model still invents is caught
by the executor, which checks every id against the caller's records.
"""
from datetime import date

from app.models.inventory import Material, Supplier
from app.models.tasks import Task

SYSTEM_PROMPT = """You are SitePilot, a construction site follow-up assistant.
Convert a site manager's plain-language site update into structured actions.

RULES
- Reply with JSON ONLY, no other text, matching this shape:
  {"summary": "<one sentence saying what you understood>", "actions": [...]}
- Each action is an object with an "action_type" and its fields.
- Use ONLY these action types, and only the fields listed for each:
  * record_delivery: {"action_type": "record_delivery", "material_id": <int>, "supplier_id": <int>, "quantity": <number greater than 0>, "unit_price": <number, optional>, "notes": <string, optional>}
    Use ONLY when the update says a delivery arrived / was received.
  * create_issue: {"action_type": "create_issue", "title": "<short>", "description": "<optional>", "category": "safety|quality|material|labour|weather|equipment|other", "priority": "low|medium|high|critical"}
    Use for a problem, hazard, defect or delay cause worth tracking.
  * create_task: {"action_type": "create_task", "title": "<short>", "description": "<optional>", "due_date": "<YYYY-MM-DD, optional>"}
    Use for new work the update asks to be done.
  * update_task_status: {"action_type": "update_task_status", "task_id": <int>, "status": "todo|in_progress|done"}
    Use ONLY for a task listed in the context below, when the update says it started, finished, or changed state.
  * update_task_due_date: {"action_type": "update_task_due_date", "task_id": <int>, "due_date": "<YYYY-MM-DD>"}
    Use ONLY for a task listed in the context below, when the update moves its deadline.
- Use ONLY the ids listed in the context below. NEVER invent an id.
  If the update mentions a material, supplier or task that is NOT in
  the context, do NOT create an action for it — say so in the summary.
- Quantities must be positive numbers. Never use 0 or a negative number.
- Dates must be YYYY-MM-DD. "Today" is the date given in the context.
- If nothing in the update maps to an action, return an empty actions
  list and explain why in the summary.
- Do not add any other action types or fields.
"""


def build_user_prompt(
    raw_text: str,
    site_name: str,
    project_name: str,
    materials: list[Material],
    suppliers: list[Supplier],
    tasks: list[Task],
) -> str:
    """User message: the raw update plus the referenceable records."""
    lines = [
        f"Site: {site_name} (project: {project_name})",
        f"Today: {date.today().isoformat()}",
        "",
        "Materials at this site (use these ids only):",
    ]
    if materials:
        for m in materials:
            lines.append(
                f"- id={m.id} name={m.name!r} unit={m.unit} "
                f"on hand={m.quantity_on_hand}"
            )
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("Suppliers (use these ids only):")
    if suppliers:
        for s in suppliers:
            lines.append(f"- id={s.id} name={s.name!r}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("Tasks on this project (use these ids only):")
    if tasks:
        for t in tasks:
            due = t.due_date.isoformat() if t.due_date else "no due date"
            lines.append(
                f"- id={t.id} title={t.title!r} status={t.status.value} due={due}"
            )
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("Site update from the manager:")
    lines.append(raw_text)
    return "\n".join(lines)
