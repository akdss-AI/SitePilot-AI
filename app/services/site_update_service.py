"""Site-update workflow service — Phase 5. No HTTP code here.

Flow (the contract in ARCHITECTURE.md section 1):
    raw text -> Groq (structured JSON) -> Pydantic validation
    -> validate every proposed action against the caller's records
    -> apply ALL valid actions in ONE transaction -> audit rows

Boundaries, enforced here:
  * The LLM only proposes. It never touches the database; this service
    never lets LLM output near SQL — every id is looked up through the
    ownership-checked getters from project/inventory/tasks services
    (get_owned_site/material/supplier/task), and every quantity/status/
    category was already validated by the LLM Pydantic schemas.
  * Atomicity is validate-all-then-apply-all in ONE db.commit().
    The other services' create/receive functions commit per call, so
    calling them in sequence would break atomicity (an early commit
    could not be rolled back if a later action failed). This executor
    therefore does NOT call those committing functions during apply:
    it reuses their ownership getters and the same rules (e.g. a
    recorded delivery is created already received and stock is
    increased in the same transaction — the receive_delivery state
    machine, applied once), and commits exactly once at the end. Any
    exception before that commit rolls everything back.
  * If ANY action is invalid, or Groq is unreachable, or the LLM
    output is unparseable: NO business change is written. The
    SiteUpdate row itself IS saved (status=failed, with a human-
    readable failure_reason) as the audit of the attempt — see
    models/site_updates.py for the exact recording rule.
  * A missing GROQ_API_KEY is different: it is a pre-flight
    configuration error, raised as AppError 503 before anything is
    recorded or sent to Groq, so POST returns 503 and no update row
    is created for it.
  * A failed Groq/parse/validation outcome is NOT an HTTP error:
    POST returns 201 with the SiteUpdate (status=failed) in the body,
    so the client can always read the audit trail from the response
    and from GET /site-updates/{id}. Nothing is ever presented as
    success when it failed.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.llm.client import GroqClient, GroqError, LLMParseError
from app.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm.schemas import LLMParsedUpdate
from app.models.inventory import Delivery, DeliveryStatus, Material
from app.models.project import Project, Site
from app.models.site_updates import (
    SiteUpdate,
    SiteUpdateAction,
    SiteUpdateActionType,
    SiteUpdateStatus,
)
from app.models.tasks import SiteIssue, Task
from app.models.user import User
from app.services.inventory_service import get_owned_material, get_owned_supplier
from app.services.project_service import get_owned_site
from app.services.tasks_service import get_owned_task

# Re-exported for tests: the allow-list lives on the model enum.
__all__ = ["submit_site_update", "list_site_updates", "get_owned_site_update"]


# ---- Recording helpers ---------------------------------------------------

def _record_failed_update(
    db: Session,
    owner: User,
    site: Site,
    raw_text: str,
    failure_reason: str,
    summary: str | None = None,
    rejected: list[tuple[dict, str]] | None = None,
) -> SiteUpdate:
    """Save the failed attempt as audit only. One commit, no business writes.

    `rejected` is a list of (payload, reason) — one row per proposed
    action, all applied=False. Pass None when no actions were parsed
    (Groq down / unparseable output): then there are no action rows.
    """
    update = SiteUpdate(
        site_id=site.id,
        submitted_by=owner.id,
        raw_text=raw_text,
        status=SiteUpdateStatus.FAILED,
        summary=summary,
        failure_reason=failure_reason,
    )
    db.add(update)
    db.flush()  # assign update.id so action rows can reference it
    for payload, reason in rejected or []:
        db.add(
            SiteUpdateAction(
                site_update_id=update.id,
                action_type=payload["action_type"],
                payload=payload,
                applied=False,
                rejection_reason=reason,
            )
        )
    db.commit()
    db.refresh(update)
    return update


# ---- Validation (no writes) ------------------------------------------------

def _validate_actions(
    db: Session, owner: User, site: Site, parsed: LLMParsedUpdate
) -> list[tuple[dict, str | None, object | None]]:
    """Check every proposed action against the caller's records.

    Returns one entry per action: (payload, rejection_reason, resolved
    object or None). rejection_reason is None when the action is valid.
    Nothing here writes to the database.
    """
    results = []
    payloads = parsed.payloads()
    for action, payload in zip(parsed.actions, payloads):
        reason: str | None = None
        resolved = None
        if action.action_type == SiteUpdateActionType.RECORD_DELIVERY:
            try:
                material = get_owned_material(db, owner, action.material_id)
            except AppError:
                material = None
                reason = (
                    f"Material {action.material_id} was not found. "
                    "It may not exist, or may belong to another user."
                )
            if material is not None and material.site_id != site.id:
                reason = (
                    f"Material {action.material_id} does not belong to this site."
                )
                material = None
            if material is not None:
                try:
                    get_owned_supplier(db, owner, action.supplier_id)
                except AppError:
                    reason = (
                        f"Supplier {action.supplier_id} was not found. "
                        "It may not exist, or may belong to another user."
                    )
                    material = None
            if reason is None and action.quantity <= 0:
                reason = "Delivery quantity must be greater than zero."
            resolved = material
        elif action.action_type in (
            SiteUpdateActionType.UPDATE_TASK_STATUS,
            SiteUpdateActionType.UPDATE_TASK_DUE_DATE,
        ):
            try:
                task = get_owned_task(db, owner, action.task_id)
            except AppError:
                task = None
                reason = (
                    f"Task {action.task_id} was not found. "
                    "It may not exist, or may belong to another user."
                )
            if task is not None:
                if task.project_id != site.project_id:
                    reason = (
                        f"Task {action.task_id} does not belong to this "
                        "site's project."
                    )
                    task = None
                elif task.site_id is not None and task.site_id != site.id:
                    reason = (
                        f"Task {action.task_id} belongs to a different site."
                    )
                    task = None
            resolved = task
        # create_issue / create_task reference no ids: Pydantic already
        # validated title/category/priority/due_date, so they are valid.
        results.append((payload, reason, resolved))
    return results


# ---- Submission ------------------------------------------------------------

def submit_site_update(
    db: Session,
    owner: User,
    site_id: int,
    raw_text: str,
    llm_client: GroqClient | None = None,
) -> SiteUpdate:
    """Submit raw text for a site; returns the recorded SiteUpdate.

    `llm_client` is injectable for tests (a fake that returns a canned
    LLMParsedUpdate or raises GroqError/LLMParseError). Production
    callers pass nothing and get a real GroqClient.
    """
    site = get_owned_site(db, owner, site_id)  # 404: missing / foreign site
    settings = get_settings()
    if llm_client is None:
        if not settings.groq_configured:
            raise AppError(
                "The LLM is not configured: set GROQ_API_KEY in the "
                "environment to use site updates.",
                503,
            )
        llm_client = GroqClient(settings)

    # Context for the prompt: only records the caller owns, so the LLM
    # has real ids to reference instead of inventing them.
    from app.services.inventory_service import list_materials, list_suppliers
    from app.services.tasks_service import list_tasks

    user_prompt = build_user_prompt(
        raw_text=raw_text,
        site_name=site.name,
        project_name=site.project.name,
        materials=list_materials(db, owner, site_id=site.id),
        suppliers=list_suppliers(db, owner),
        tasks=list_tasks(db, owner, project_id=site.project_id),
    )

    try:
        parsed = llm_client.parse_site_update(SYSTEM_PROMPT, user_prompt)
    except GroqError as exc:
        return _record_failed_update(
            db, owner, site, raw_text,
            failure_reason=f"The LLM service could not be reached: {exc}",
        )
    except LLMParseError as exc:
        return _record_failed_update(
            db, owner, site, raw_text,
            failure_reason=f"The LLM output could not be understood: {exc}",
        )

    validated = _validate_actions(db, owner, site, parsed)
    rejected = [
        (payload, reason) for payload, reason, _ in validated if reason is not None
    ]
    if rejected:
        # All-or-nothing: even the valid-looking actions are NOT applied.
        # Their audit rows say so explicitly.
        all_rejected = [
            (payload, reason if reason is not None
             else "Not applied: another action in this update was invalid, "
                  "so nothing was applied.")
            for payload, reason, _ in validated
        ]
        return _record_failed_update(
            db, owner, site, raw_text,
            failure_reason=(
                f"{len(rejected)} of {len(validated)} proposed action(s) "
                "were invalid, so nothing was applied."
            ),
            summary=parsed.summary or None,
            rejected=all_rejected,
        )

    # All valid: apply everything in ONE transaction.
    update = SiteUpdate(
        site_id=site.id,
        submitted_by=owner.id,
        raw_text=raw_text,
        status=SiteUpdateStatus.PROCESSED,
        summary=parsed.summary or None,
    )
    db.add(update)
    try:
        db.flush()
        for action, payload, (_, _, resolved) in zip(
            parsed.actions, parsed.payloads(), validated
        ):
            _apply_action(db, owner, site, action, resolved)
            db.add(
                SiteUpdateAction(
                    site_update_id=update.id,
                    action_type=action.action_type,
                    payload=payload,
                    applied=True,
                    rejection_reason=None,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        # The apply itself failed after validation passed (a database
        # error, not a validation error): record the failed attempt so
        # the audit trail shows it, and report honestly.
        return _record_failed_update(
            db, owner, site, raw_text,
            failure_reason=(
                "Applying the actions failed unexpectedly; nothing was changed."
            ),
            summary=parsed.summary or None,
        )
    db.refresh(update)
    return update


def _apply_action(db: Session, owner: User, site: Site, action, resolved) -> None:
    """Apply ONE already-validated action. No commit here — the caller
    commits once for the whole update. `resolved` is the owned record
    _validate_actions looked up (material / task), or None."""
    if action.action_type == SiteUpdateActionType.RECORD_DELIVERY:
        material: Material = resolved
        delivery = Delivery(
            material_id=material.id,
            supplier_id=action.supplier_id,
            quantity=action.quantity,
            unit_price=action.unit_price,
            notes=action.notes,
            # Created already received: the manager reported an arrival,
            # so this is create + receive in one transaction — the same
            # state change receive_delivery() performs, with the stock
            # increase in the same commit.
            status=DeliveryStatus.RECEIVED,
            received_date=date.today(),
        )
        db.add(delivery)
        material.quantity_on_hand = material.quantity_on_hand + action.quantity
    elif action.action_type == SiteUpdateActionType.CREATE_ISSUE:
        db.add(
            SiteIssue(
                site_id=site.id,
                reported_by=owner.id,
                title=action.title,
                description=action.description,
                category=action.category,
                priority=action.priority,
            )
        )
    elif action.action_type == SiteUpdateActionType.CREATE_TASK:
        db.add(
            Task(
                project_id=site.project_id,
                site_id=site.id,
                title=action.title,
                description=action.description,
                due_date=action.due_date,
            )
        )
    elif action.action_type == SiteUpdateActionType.UPDATE_TASK_STATUS:
        task: Task = resolved
        task.status = action.status
    elif action.action_type == SiteUpdateActionType.UPDATE_TASK_DUE_DATE:
        task: Task = resolved
        task.due_date = action.due_date
    else:  # pragma: no cover — the union + validation make this unreachable
        raise AppError(f"Unsupported action type: {action.action_type}.", 422)


# ---- Reads -----------------------------------------------------------------

def list_site_updates(
    db: Session, owner: User, site_id: int | None = None
) -> list[SiteUpdate]:
    query = (
        select(SiteUpdate)
        .join(Site, SiteUpdate.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(Project.owner_id == owner.id)
        .order_by(SiteUpdate.id)
    )
    if site_id is not None:
        get_owned_site(db, owner, site_id)  # filtering by a foreign site is 404
        query = query.where(SiteUpdate.site_id == site_id)
    return list(db.scalars(query))


def get_owned_site_update(db: Session, owner: User, update_id: int) -> SiteUpdate:
    update = db.scalar(
        select(SiteUpdate)
        .join(Site, SiteUpdate.site_id == Site.id)
        .join(Project, Site.project_id == Project.id)
        .where(SiteUpdate.id == update_id, Project.owner_id == owner.id)
    )
    if update is None:
        raise AppError("Site update not found.", 404)
    return update
