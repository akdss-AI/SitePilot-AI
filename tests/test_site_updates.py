"""Phase 5 — LLM site-update workflow: mocked Groq throughout.

No test here ever calls the real Groq API. The Groq client is
replaced (monkeypatched at app.services.site_update_service.GroqClient)
with a fake that returns a canned LLMParsedUpdate, or raises
GroqError / LLMParseError — plus direct unit tests of
parse_llm_response for malformed JSON, unknown action types and
invalid quantities. A fake Groq key is injected the same way, via
get_settings, so the missing-key test can use the real (empty) key.

Zero-partial-writes is asserted on every failure test by reading the
business state back through the API (stock, deliveries, issues,
tasks) and comparing it with the state before the update.
"""
import json
from datetime import date, timedelta

import pytest

from app.core.config import Settings
from app.llm.client import GroqError, LLMParseError, parse_llm_response
from app.llm.schemas import LLMParsedUpdate
from tests.conftest import make_material, make_site, make_supplier
from tests.test_materials import stock
from tests.test_tasks import make_task


# ---- Fakes ---------------------------------------------------------------

class FakeGroq:
    """Returns a canned parsed update, or raises a canned error."""

    def __init__(self, parsed=None, error=None):
        self.parsed = parsed
        self.error = error
        self.last_system_prompt = None
        self.last_user_prompt = None

    def parse_site_update(self, system_prompt, user_prompt):
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        if self.error is not None:
            raise self.error
        return self.parsed


class FakeGroqFromRaw:
    """Parses a raw LLM content string — exercises the real parser."""

    def __init__(self, raw_content):
        self.raw_content = raw_content

    def parse_site_update(self, system_prompt, user_prompt):
        return parse_llm_response(self.raw_content)


def mock_groq(monkeypatch, fake):
    """Inject a fake Groq client + a configured (fake) API key."""
    monkeypatch.setattr(
        "app.services.site_update_service.get_settings",
        lambda: Settings(groq_api_key="test-only-fake-key", groq_model="test-model"),
    )
    monkeypatch.setattr(
        "app.services.site_update_service.GroqClient",
        lambda settings: fake,
    )


def parsed_update(summary, actions):
    return LLMParsedUpdate.model_validate({"summary": summary, "actions": actions})


# ---- Setup helpers ---------------------------------------------------------

def setup_site(client, headers, opening=10, **site_kwargs):
    """Project + site + supplier + material; returns ids dict."""
    project_id, site_id = make_site(client, headers, **site_kwargs)
    supplier_id = make_supplier(client, headers)
    material = make_material(
        client, headers, site_id, quantity_on_hand=opening, reorder_level=5
    )
    return {
        "project_id": project_id,
        "site_id": site_id,
        "supplier_id": supplier_id,
        "material_id": material["id"],
    }


def setup_task(client, headers, project_id, site_id, **overrides):
    response = make_task(
        client, headers, project_id, site_id=site_id, **overrides
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, headers, site_id, text):
    return client.post(
        "/api/v1/site-updates",
        json={"site_id": site_id, "raw_text": text},
        headers=headers,
    )


def business_state(client, headers, material_id):
    """Snapshot of every business record a site update could change."""
    return {
        "stock": stock(client, headers, material_id),
        "deliveries": client.get("/api/v1/deliveries", headers=headers).json(),
        "issues": client.get("/api/v1/issues", headers=headers).json(),
        "tasks": client.get("/api/v1/tasks", headers=headers).json(),
    }


# ---- Happy path ------------------------------------------------------------

def test_valid_update_applies_delivery_issue_and_due_date_move(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    due = (date.today() + timedelta(days=5)).isoformat()
    task = setup_task(
        client, owner_headers, ids["project_id"], ids["site_id"], due_date=due
    )
    new_due = (date.today() + timedelta(days=7)).isoformat()
    fake = FakeGroq(
        parsed_update(
            "Cement arrived; scaffolding issue noted; plastering delayed.",
            [
                {
                    "action_type": "record_delivery",
                    "material_id": ids["material_id"],
                    "supplier_id": ids["supplier_id"],
                    "quantity": 200,
                },
                {
                    "action_type": "create_issue",
                    "title": "Scaffolding unsafe on Block C",
                    "category": "safety",
                    "priority": "high",
                },
                {
                    "action_type": "update_task_due_date",
                    "task_id": task["id"],
                    "due_date": new_due,
                },
            ],
        )
    )
    mock_groq(monkeypatch, fake)

    response = submit(
        client, owner_headers, ids["site_id"],
        "Cement delivery of 200 bags arrived. Scaffolding safety issue "
        "on Block C. Plastering delayed 2 days.",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "processed"
    assert body["failure_reason"] is None
    assert body["summary"].startswith("Cement arrived")
    assert len(body["actions"]) == 3
    assert all(a["applied"] for a in body["actions"])
    assert all(a["rejection_reason"] is None for a in body["actions"])
    # Delivery recorded already received + stock updated: 10 + 200.
    assert stock(client, owner_headers, ids["material_id"]) == 210
    deliveries = client.get("/api/v1/deliveries", headers=owner_headers).json()
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "received"
    assert deliveries[0]["quantity"] == "200.00"
    # Issue created, reported by the caller.
    issues = client.get("/api/v1/issues", headers=owner_headers).json()
    assert len(issues) == 1
    assert issues[0]["title"] == "Scaffolding unsafe on Block C"
    assert issues[0]["category"] == "safety"
    assert issues[0]["priority"] == "high"
    # Task deadline moved.
    updated = client.get(f"/api/v1/tasks/{task['id']}", headers=owner_headers).json()
    assert updated["due_date"] == new_due
    # The prompt gave the LLM the real ids to reference.
    assert f"id={ids['material_id']}" in fake.last_user_prompt
    assert f"id={ids['supplier_id']}" in fake.last_user_prompt
    assert f"id={task['id']}" in fake.last_user_prompt


def test_valid_update_creates_task_and_marks_task_done(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    task = setup_task(client, owner_headers, ids["project_id"], ids["site_id"])
    fake = FakeGroq(
        parsed_update(
            "Slab poured; new curing task created.",
            [
                {
                    "action_type": "update_task_status",
                    "task_id": task["id"],
                    "status": "done",
                },
                {
                    "action_type": "create_task",
                    "title": "Cure the slab",
                    "due_date": (date.today() + timedelta(days=3)).isoformat(),
                },
            ],
        )
    )
    mock_groq(monkeypatch, fake)
    response = submit(client, owner_headers, ids["site_id"], "Slab done, cure it.")
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "processed"
    tasks = client.get("/api/v1/tasks", headers=owner_headers).json()
    assert {t["title"]: t["status"] for t in tasks} == {
        "Pour concrete slab": "done",
        "Cure the slab": "todo",
    }


def test_update_with_no_actions_is_processed_and_changes_nothing(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    before = business_state(client, owner_headers, ids["material_id"])
    mock_groq(monkeypatch, FakeGroq(parsed_update("Nothing actionable.", [])))
    response = submit(client, owner_headers, ids["site_id"], "All good today.")
    assert response.status_code == 201
    assert response.json()["status"] == "processed"
    assert response.json()["actions"] == []
    assert business_state(client, owner_headers, ids["material_id"]) == before


# ---- Rejection: zero partial writes ----------------------------------------

def test_hallucinated_material_id_rejects_whole_update(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    task = setup_task(client, owner_headers, ids["project_id"], ids["site_id"])
    before = business_state(client, owner_headers, ids["material_id"])
    fake = FakeGroq(
        parsed_update(
            "Delivery arrived and a task finished.",
            [
                {
                    "action_type": "record_delivery",
                    "material_id": 99999,  # hallucinated
                    "supplier_id": ids["supplier_id"],
                    "quantity": 50,
                },
                {
                    "action_type": "update_task_status",
                    "task_id": task["id"],
                    "status": "done",
                },
            ],
        )
    )
    mock_groq(monkeypatch, fake)
    response = submit(client, owner_headers, ids["site_id"], "Delivery arrived.")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["failure_reason"] is not None
    assert len(body["actions"]) == 2
    assert all(not a["applied"] for a in body["actions"])
    assert "99999" in body["actions"][0]["rejection_reason"]
    # The valid-looking second action was NOT applied either.
    assert "another action" in body["actions"][1]["rejection_reason"]
    assert business_state(client, owner_headers, ids["material_id"]) == before


def test_hallucinated_supplier_and_task_ids_are_rejected(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    before = business_state(client, owner_headers, ids["material_id"])
    fake = FakeGroq(
        parsed_update(
            "Delivery and task update.",
            [
                {
                    "action_type": "record_delivery",
                    "material_id": ids["material_id"],
                    "supplier_id": 99999,
                    "quantity": 50,
                },
                {
                    "action_type": "update_task_status",
                    "task_id": 99999,
                    "status": "done",
                },
            ],
        )
    )
    mock_groq(monkeypatch, fake)
    response = submit(client, owner_headers, ids["site_id"], "Update.")
    assert response.json()["status"] == "failed"
    assert all(not a["applied"] for a in response.json()["actions"])
    assert business_state(client, owner_headers, ids["material_id"]) == before


def test_other_users_records_are_rejected_not_leaked(
    client, owner_headers, other_headers, monkeypatch
):
    # The other user owns a material + task; the owner must not be able
    # to reference them from their own site update.
    foreign = setup_site(client, other_headers, project_name="Other Project")
    foreign_task = setup_task(
        client, other_headers, foreign["project_id"], foreign["site_id"]
    )
    ids = setup_site(client, owner_headers)
    before = business_state(client, owner_headers, ids["material_id"])
    fake = FakeGroq(
        parsed_update(
            "Delivery and task update.",
            [
                {
                    "action_type": "record_delivery",
                    "material_id": foreign["material_id"],
                    "supplier_id": ids["supplier_id"],
                    "quantity": 50,
                },
                {
                    "action_type": "update_task_status",
                    "task_id": foreign_task["id"],
                    "status": "done",
                },
            ],
        )
    )
    mock_groq(monkeypatch, fake)
    response = submit(client, owner_headers, ids["site_id"], "Update.")
    assert response.json()["status"] == "failed"
    assert business_state(client, owner_headers, ids["material_id"]) == before
    # The foreign records themselves are untouched.
    assert stock(client, other_headers, foreign["material_id"]) == 10
    assert client.get(
        f"/api/v1/tasks/{foreign_task['id']}", headers=other_headers
    ).json()["status"] == "todo"


def test_material_from_another_site_of_same_owner_is_rejected(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    _, other_site = make_site(client, owner_headers, "Second Project", "Second Site")
    other_material = make_material(client, owner_headers, other_site)
    before = business_state(client, owner_headers, ids["material_id"])
    mock_groq(
        monkeypatch,
        FakeGroq(
            parsed_update(
                "Delivery arrived.",
                [
                    {
                        "action_type": "record_delivery",
                        "material_id": other_material["id"],
                        "supplier_id": ids["supplier_id"],
                        "quantity": 10,
                    }
                ],
            )
        ),
    )
    response = submit(client, owner_headers, ids["site_id"], "Delivery arrived.")
    assert response.json()["status"] == "failed"
    assert "does not belong to this site" in response.json()["actions"][0]["rejection_reason"]
    assert business_state(client, owner_headers, ids["material_id"]) == before


@pytest.mark.parametrize("quantity", [0, -5, "not-a-number"])
def test_invalid_quantities_are_rejected_with_zero_writes(
    client, owner_headers, monkeypatch, quantity
):
    ids = setup_site(client, owner_headers)
    before = business_state(client, owner_headers, ids["material_id"])
    raw = json.dumps(
        {
            "summary": "Delivery.",
            "actions": [
                {
                    "action_type": "record_delivery",
                    "material_id": ids["material_id"],
                    "supplier_id": ids["supplier_id"],
                    "quantity": quantity,
                }
            ],
        }
    )
    mock_groq(monkeypatch, FakeGroqFromRaw(raw))
    response = submit(client, owner_headers, ids["site_id"], "Delivery arrived.")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["actions"] == []  # unparseable output: no actions were parsed
    assert body["failure_reason"] is not None
    assert business_state(client, owner_headers, ids["material_id"]) == before


def test_unknown_action_type_is_rejected_with_zero_writes(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    before = business_state(client, owner_headers, ids["material_id"])
    raw = (
        '{"summary": "Do something.", "actions": ['
        '{"action_type": "delete_project", "project_id": 1}]}'
    )
    mock_groq(monkeypatch, FakeGroqFromRaw(raw))
    response = submit(client, owner_headers, ids["site_id"], "Delete the project.")
    assert response.json()["status"] == "failed"
    assert response.json()["actions"] == []
    assert business_state(client, owner_headers, ids["material_id"]) == before


def test_malformed_llm_json_is_rejected_with_zero_writes(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    before = business_state(client, owner_headers, ids["material_id"])
    mock_groq(monkeypatch, FakeGroqFromRaw("{this is not json"))
    response = submit(client, owner_headers, ids["site_id"], "Delivery arrived.")
    assert response.json()["status"] == "failed"
    assert response.json()["actions"] == []
    assert "not valid JSON" in response.json()["failure_reason"]
    assert business_state(client, owner_headers, ids["material_id"]) == before


def test_groq_down_is_a_clean_failure_with_zero_writes(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    before = business_state(client, owner_headers, ids["material_id"])
    mock_groq(monkeypatch, FakeGroq(error=GroqError("Connection timed out.")))
    response = submit(client, owner_headers, ids["site_id"], "Delivery arrived.")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["actions"] == []
    assert "could not be reached" in body["failure_reason"]
    assert business_state(client, owner_headers, ids["material_id"]) == before


# ---- Parser unit tests -------------------------------------------------------

def test_parse_llm_response_rejects_unknown_action_and_bad_status():
    with pytest.raises(LLMParseError):
        parse_llm_response('{"summary": "x", "actions": [{"action_type": "explode"}]}')
    with pytest.raises(LLMParseError):
        parse_llm_response(
            '{"summary": "x", "actions": [{"action_type": "update_task_status", '
            '"task_id": 1, "status": "finished"}]}'
        )
    with pytest.raises(LLMParseError):
        parse_llm_response('{"summary": "x", "actions": "not-a-list"}')
    with pytest.raises(LLMParseError):
        parse_llm_response("")


def test_parse_llm_response_ignores_extra_fields():
    parsed = parse_llm_response(
        '{"summary": "ok", "extra_top": 1, "actions": ['
        '{"action_type": "create_issue", "title": "Leak", '
        '"category": "quality", "made_up_field": true}]}'
    )
    assert parsed.summary == "ok"
    assert len(parsed.actions) == 1
    assert parsed.actions[0].title == "Leak"


# ---- Missing key, ownership, reads -------------------------------------------

def test_missing_api_key_returns_503_and_records_nothing(client, owner_headers):
    ids = setup_site(client, owner_headers)
    # No monkeypatch: conftest leaves GROQ_API_KEY empty.
    response = submit(client, owner_headers, ids["site_id"], "Delivery arrived.")
    assert response.status_code == 503, response.text
    assert "GROQ_API_KEY" in response.json()["detail"]
    assert "not configured" in response.json()["detail"]
    assert client.get("/api/v1/site-updates", headers=owner_headers).json() == []


def test_other_users_site_is_404(client, owner_headers, other_headers, monkeypatch):
    _, foreign_site = make_site(client, other_headers, "Other Project", "Other Site")
    mock_groq(monkeypatch, FakeGroq(parsed_update("x", [])))
    assert submit(
        client, owner_headers, foreign_site, "Hello."
    ).status_code == 404
    assert submit(client, owner_headers, 99999, "Hello.").status_code == 404


def test_get_endpoints_return_the_audit_trail(
    client, owner_headers, other_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    mock_groq(
        monkeypatch,
        FakeGroq(
            parsed_update(
                "Issue noted.",
                [
                    {
                        "action_type": "create_issue",
                        "title": "Crack in wall",
                        "category": "quality",
                        "priority": "medium",
                    }
                ],
            )
        ),
    )
    created = submit(client, owner_headers, ids["site_id"], "Crack in wall.")
    assert created.status_code == 201
    update_id = created.json()["id"]

    listed = client.get("/api/v1/site-updates", headers=owner_headers)
    assert listed.status_code == 200
    assert [u["id"] for u in listed.json()] == [update_id]
    filtered = client.get(
        f"/api/v1/site-updates?site_id={ids['site_id']}", headers=owner_headers
    )
    assert [u["id"] for u in filtered.json()] == [update_id]
    assert client.get(
        "/api/v1/site-updates?site_id=99999", headers=owner_headers
    ).status_code == 404

    detail = client.get(f"/api/v1/site-updates/{update_id}", headers=owner_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "processed"
    assert body["raw_text"] == "Crack in wall."
    assert len(body["actions"]) == 1
    assert body["actions"][0]["action_type"] == "create_issue"
    assert body["actions"][0]["applied"] is True
    assert body["actions"][0]["payload"]["title"] == "Crack in wall"
    # Another user sees nothing: empty list, 404 on the detail.
    assert client.get("/api/v1/site-updates", headers=other_headers).json() == []
    assert client.get(
        f"/api/v1/site-updates/{update_id}", headers=other_headers
    ).status_code == 404
    assert client.get("/api/v1/site-updates/99999", headers=owner_headers).status_code == 404


def test_failed_update_is_visible_in_the_audit_trail(
    client, owner_headers, monkeypatch
):
    ids = setup_site(client, owner_headers)
    mock_groq(monkeypatch, FakeGroq(error=GroqError("Service unavailable.")))
    created = submit(client, owner_headers, ids["site_id"], "Delivery arrived.")
    detail = client.get(
        f"/api/v1/site-updates/{created.json()['id']}", headers=owner_headers
    )
    assert detail.json()["status"] == "failed"
    assert detail.json()["failure_reason"] is not None
    assert detail.json()["actions"] == []


def test_site_updates_require_auth_and_blank_text_is_422(client, owner_headers, monkeypatch):
    ids = setup_site(client, owner_headers)
    assert client.post(
        "/api/v1/site-updates",
        json={"site_id": ids["site_id"], "raw_text": "hi"},
    ).status_code == 401
    assert client.get("/api/v1/site-updates").status_code == 401
    mock_groq(monkeypatch, FakeGroq(parsed_update("x", [])))
    assert submit(client, owner_headers, ids["site_id"], "   ").status_code == 422
