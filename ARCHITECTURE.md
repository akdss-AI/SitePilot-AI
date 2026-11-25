# SitePilot AI — Architecture

**SitePilot AI — Construction Operations Follow-up Assistant**
A portfolio-quality operations system for small construction contractors and
property developers. Fictional demo data only.

This document is the contract for the build. Architecture changes must be
recorded here first — they are never made silently in code.

---

## 1. Architecture overview

SitePilot is a **modular monolith**: one FastAPI application, one PostgreSQL
database, one deployable unit. This is deliberate — it is the simplest
architecture that demonstrates real backend + AI engineering, and the easiest
for a single developer to explain, debug, and maintain.

```
Browser (Jinja2 pages)
        │  HTTP (HTML for pages, JSON for API)
        ▼
FastAPI app
  ├─ api/v1/routes/     HTTP layer only: parse request, call service, return response
  ├─ services/          Business rules: stock alerts, overdue tasks, daily summary
  ├─ llm/               Groq client + structured-output parsing + validation
  │                     of site updates. The LLM *proposes*; it never writes.
  ├─ db/session.py      SQLAlchemy engine + session dependency
  └─ models/            SQLAlchemy models (database shape)
        │
        ▼
PostgreSQL  (SQLite only as a throwaway test database — models stay
             PostgreSQL-compatible; no SQLite-specific types are used)
```

**The most important rule in the system:** the LLM never executes SQL and
never touches the database directly. Flow for a site update:

```
raw text → Groq (structured JSON) → Pydantic validation → bounded service
functions (allow-listed actions only, IDs/quantities/statuses checked,
caller's projects only) → DB transaction → human-readable result
```

If any step fails validation, **nothing is written** and the user is told why.

### Frontend choice (decided before implementation)

**Server-rendered Jinja2 templates + plain CSS, served by FastAPI itself.**

Why, for this project:
- One language (Python), one repo, one deployment — no Node build step,
  no second server, no CORS configuration.
- Aqdas already knows Python; every part of the stack is code he can read.
- Semantic server-rendered HTML is good enough for a portfolio demo and
  for basic SEO (meta tags, Open Graph, sitemap) on the public landing page.

Trade-off accepted honestly: less interactive than a React/Next.js SPA.
If a richer UI is ever needed, the `/api/v1` JSON API already separates the
backend, so a separate frontend could be added later *without* rewriting it.
That is a future decision, not a v1 feature.

---

## 2. Folder structure

```
sitepilot-ai/
├── ARCHITECTURE.md          This document
├── README.md                How to run, test, and deploy
├── requirements.txt         Pinned-by-name dependencies (added per phase, on purpose)
├── .env.example             Every config variable, no real secrets
├── .gitignore
├── app/
│   ├── main.py              App factory, router + error-handler registration, root page
│   ├── core/
│   │   └── config.py        Settings from environment variables (pydantic-settings)
│   ├── db/
│   │   ├── base.py          SQLAlchemy Declarative Base (all models inherit it)
│   │   └── session.py       Engine, SessionLocal, get_db() dependency
│   ├── models/              SQLAlchemy models — Phase 2 onwards
│   ├── schemas/             Pydantic request/response schemas — Phase 2 onwards
│   ├── services/            Business logic (no HTTP, no LLM calls here)
│   ├── llm/                 Groq client, prompts, structured parsing — Phase 5
│   ├── api/v1/
│   │   ├── router.py        Aggregates all v1 routers under /api/v1
│   │   └── routes/          One file per resource (health, auth, projects, …)
│   ├── templates/           Jinja2 pages (base.html, index.html, dashboard…)
│   └── static/              Plain CSS / JS, no build step
├── scripts/                 Seed / demo-data scripts — Phase 7
└── tests/                   pytest suite; every phase adds tests for its work
```

---

## 3. Database relationships

```
users ──< projects ──< sites ──< materials ──< deliveries
              │            │          ▲              ▲
              │            │          └── suppliers ─┘
              │            ├──< tasks        (assigned_to ──> users, nullable)
              │            ├──< site_issues  (reported_by ──> users)
              │            └──< site_updates ──< site_update_actions
              └──< (tasks / issues can also attach at project level)
```

| Table | Key relationships | Notes |
|---|---|---|
| `users` | — | `email` unique, `hashed_password` only, never plain text |
| `projects` | `owner_id → users.id` | Every other record is scoped through a project |
| `sites` | `project_id → projects.id` | A project can have several physical sites |
| `suppliers` | `owner_id → users.id` | Owner-scoped (decided Phase 3): a supplier is a user's own address-book entry, which is what makes cross-user supplier references rejectable. Referenced by materials (preferred, SET NULL on delete) & deliveries (RESTRICT on delete) |
| `materials` | `site_id → sites.id`, `preferred_supplier_id → suppliers.id` (nullable) | `quantity_on_hand`, `reorder_level`, `unit`. **Stock alert = computed**: `quantity_on_hand <= reorder_level`. No separate alert table needed. |
| `deliveries` | `material_id`, `supplier_id` | No separate `site_id` column (decided Phase 3): site/project are reached through the material, so the stored data can never disagree about where a delivery went. Status: pending/received/cancelled; created always pending; receiving increases stock in the same transaction, exactly once |
| `tasks` | `project_id`, `site_id` (nullable), `assigned_to → users.id` (nullable), `due_date` (nullable) | Status enum: `todo` / `in_progress` / `done`. `assigned_to` is a display/follow-up reference only — not permissions or notifications. **Overdue = computed**: `due_date` is set AND `due_date < today` AND `status != done` (a task with no due date can never be overdue; a task due today is NOT overdue). Decided 2026-11-24 (proposed defaults accepted under full-completion authorization). |
| `site_issues` | `site_id`, `reported_by → users.id` | `category` enum: `safety, quality, material, labour, weather, equipment, other`; `priority` (low/medium/high/critical), `status` (open/in_progress/resolved/closed) — validated against fixed enums, never free text. Issues attach to a site only (no project link). Decided 2026-11-24. |
| `site_updates` | `site_id`, `submitted_by → users.id` | The manager's raw natural-language text + processing status |
| `site_update_actions` | `site_update_id` | One row per action the LLM proposed: action type (allow-list only), validated payload, whether it was applied. This is the audit trail that proves the LLM stayed bounded. |

Daily summaries are **generated on read** from tasks/materials/issues —
not stored — so they can never drift out of sync with the real data.

Enforced in code (Phase 2+): a user can only read/write records belonging
to projects they own. IDs from the LLM or the client are always checked
against that scope before use.

---

## 4. API endpoints (planned, `/api/v1` prefix)

| Area | Endpoints |
|---|---|
| Health | `GET /health` (page/API root check), `GET /api/v1/health` |
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Projects | `POST /projects`, `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}`, `DELETE /projects/{id}` |
| Sites | `POST /projects/{project_id}/sites`, `GET /projects/{project_id}/sites`, `GET /sites/{id}`, `PATCH /sites/{id}` |
| Suppliers | `POST /suppliers`, `GET /suppliers`, `GET /suppliers/{id}`, `PATCH /suppliers/{id}` |
| Materials | `POST /materials`, `GET /materials`, `GET /materials/{id}`, `PATCH /materials/{id}`, `GET /materials/alerts/stock` |
| Deliveries | `POST /deliveries`, `GET /deliveries`, `PATCH /deliveries/{id}` (receiving a delivery updates stock transactionally) |
| Tasks | `POST /tasks`, `GET /tasks`, `GET /tasks/overdue`, `GET /tasks/{id}`, `PATCH /tasks/{id}` |
| Site issues | `POST /issues`, `GET /issues`, `GET /issues/{id}`, `PATCH /issues/{id}` |
| Site updates (LLM) | `POST /site-updates` (submit raw text → structured, validated, bounded actions), `GET /site-updates`, `GET /site-updates/{id}` (includes per-action audit) |
| Daily summary | `GET /projects/{project_id}/summary/today` |

Pages (Jinja2, no `/api` prefix): `/` landing, `/dashboard`,
`/login`, `/projects/{id}` — built in Phase 6.

**Explicitly out of scope for v1:** RAG, embeddings, vector databases,
WhatsApp, payments, quotations/PDF generation, complex autonomous agents.

### Revenue readiness (added 2026-11-24)

SitePilot v1 stays a portfolio/learning build, but it must be
*demonstrably sellable*: polished landing page with the positioning
statement, a pricing section (Starter / Professional / Business as
content only — no payment gateway, no subscription enforcement; manual
activation, consistent with the v1 no-payments rule), realistic fictional
demo data, deployment + SEO, and a clean handover story (what it does,
who pays for it, what it costs to run). Real billing, multi-tenant
businesses, roles, expenses/labour/quotations, and a client portal are
the scope of the separate **BuildLedger** SaaS product (different folder,
different chat) — not bolted onto SitePilot.

---

## 5. Main user workflows

1. **Set up:** Register → create a project → add a site → add suppliers and
   starting materials.
2. **Daily follow-up (the core loop):** Manager opens the dashboard, sees
   overdue tasks, low stock, and open critical issues at a glance.
3. **Natural-language site update:** Manager types e.g. *"Cement delivery of
   200 bags arrived from Ali Traders. Tower B plastering is delayed 2 days
   because of rain. Urgent: scaffolding safety issue on Block C."*
   → System returns what it understood, what it changed (delivery recorded,
   stock updated, task deadline moved, issue created), and anything it
   rejected and why. Nothing unvalidated is ever applied.
4. **Material delivery:** Record a delivery → mark received → stock
   increases and the low-stock alert clears.
5. **Task follow-up:** Create/assign a task with a deadline → it appears in
   the overdue list and the daily summary until done.
6. **Daily summary:** One view per project: delays, shortages, open issues,
   upcoming tasks — the page a contractor owner checks each morning.

---

## 6. Phased implementation plan

Each phase: explanation → complete files → tests run → what works →
limitations. **Stop for Aqdas's review after every phase — superseded
2026-11-24:** on 2026-11-24 Aqdas authorized full completion of Phases
4–7 in sequence, lifting the Phase 3 review gate, and asked for the
product to be made revenue-ready (see "Revenue readiness" below). The
five Phase 4 design decisions above were settled to the proposed
defaults under that authorization. Demo videos, social-media posting,
and user testing are deferred to the end, when Aqdas will be asked.

### Phase 1 — Foundation — DONE
Scaffold, env-based config (no secrets in code), DB base/session,
health endpoint, simple landing page, test setup.
**Acceptance:** `pytest` passes; app starts; `GET /api/v1/health` returns
`{"status": "ok", ...}`; `GET /` renders the landing page; no API key or
password exists anywhere in code.

### Phase 2 — Auth + Projects & Sites — DONE
User model, password hashing, JWT login, project/site CRUD with ownership.
**Acceptance:** register/login/me tested; user A cannot access user B's
project (tested, 404/403); project + site CRUD tested.

### Phase 3 — Materials, Suppliers, Deliveries, Stock Alerts — DONE
**Acceptance:** receiving a delivery increases stock in one transaction
(tested, including failure rollback); low-stock alert list correct (tested).

### Phase 4 — Tasks & Site Issues — DONE (2026-11-24)
**Acceptance:** overdue detection correct across due-date/status cases
(tested); issue category/priority/status reject invalid values (tested).

### Phase 5 — LLM Site-Update Workflow (Groq) — DONE (2026-11-24)
Groq client (env-configured), structured output, Pydantic validation,
bounded action executor (allow-list only), audit rows, clear failure mode
when the LLM output is invalid or the API is down.
**Acceptance:** tests run against a *mocked* Groq response (no real API
cost in tests): valid update applies only permitted actions; hallucinated
IDs / invalid quantities / unknown actions are rejected and reported,
with zero partial writes.

**Live verification 2026-11-25 (Aqdas's key, env only):** the original
default model `llama-3.3-70b-versatile` no longer exists on Groq — the
API returned `model_not_found` — so the default was changed to
`openai/gpt-oss-20b` (verified against the live models list) in
`config.py`, `.env.example`, and the README. Request timeout raised
30s → 60s: live calls measured ~30s+ through this dev machine's egress
proxy; normal hosting has no proxy. A failed Groq call is recorded as a
`failed` update with a reason and zero business writes (verified live).

**Action allow-list (final, in exactly these five):** `record_delivery`,
`create_issue`, `create_task`, `update_task_status`,
`update_task_due_date`. Nothing else can be applied. A `record_delivery`
creates the delivery already received and increases stock in the same
transaction (the receive_delivery state machine, applied once). A task
update only applies to a task on the update site's project (and, if the
task has a site, that site). No action creates materials/suppliers,
deletes anything, or changes a task's project.

**Failed-attempt recording (decided Phase 5):** the `site_updates` row
itself is always saved on a processing failure — it is the audit of the
attempt, not a business change — with `status=failed` and a human-
readable `failure_reason`, and NO business change is written (no
delivery, stock, task or issue change; no action row marked applied).
Groq unreachable / unparseable output: failed row, zero action rows
(no actions were parsed). One or more invalid actions: failed row plus
one action row per proposed action, ALL `applied=false` with a
`rejection_reason` — including valid-looking ones, which are explicitly
not applied because the update is all-or-nothing. A failed outcome is
returned as HTTP 201 with `status=failed` in the body (the submission
was recorded), never presented as success. The one exception is a
missing `GROQ_API_KEY`: a pre-flight configuration error, HTTP 503,
no update row created.

**How atomicity is achieved:** validate ALL actions first (ownership
via the existing `get_owned_*` getters, site/project scope, positive
Decimal quantities, valid enums), then apply ALL in ONE `db.commit()`.
The executor deliberately does NOT call the other services'
create/receive functions during apply, because those commit per call
and a later failure could not roll back an earlier commit. Prompt
context lists only the caller's real material/supplier/task ids, so
the LLM has ids to reference instead of inventing them; hallucinated
ids are still rejected by the executor. LLM schemas: known fields
validated strictly; unknown extra fields ignored (never applied);
an unknown `action_type` matches no discriminated-union variant, so
the whole output fails validation. No new dependency: httpx (already
present) calls Groq's OpenAI-compatible endpoint with
`response_format: {"type": "json_object"}`.

### Phase 6 — Daily Summary + Dashboard — DONE (2026-11-24)
Summary service + endpoint, Jinja2 dashboard, landing page polish,
basic SEO meta/sitemap for the public page.
**Acceptance:** summary numbers match seeded demo data (tested);
dashboard renders for a logged-in user.

**Page auth decision (Phase 6):** the JSON API keeps Bearer JWTs
(`Authorization: Bearer <token>`, 401 when absent). Browsers do not
send that header on plain navigation, so the HTML pages accept the
*same* JWT from an HttpOnly cookie as well: `POST /login` (form)
authenticates and sets a `sitepilot_token` cookie (`HttpOnly`,
`SameSite=Lax`, lifetime = the JWT expiry); page routes accept the
token from the Authorization header first, then the cookie
(`app/api/deps.py:get_page_user`, which returns `None` instead of
raising). Unauthenticated visits to `/dashboard` and `/projects/{id}`
redirect to `/login` with 302. No new dependency, no session table,
no change to Bearer auth — the cookie only carries the same JWT.
**Summary:** generated on read from live data (never stored, no
summary table); overdue = `due_date < today` and not done; due today
and upcoming (next 7 days) are separate buckets; open issues are
`open`/`in_progress`, listed critical first; low stock is
`quantity_on_hand <= reorder_level`; pending deliveries and the 5
most recent site updates are included. Landing page carries the
positioning statement, a features section, and Starter ($29) /
Professional ($79) / Business ($199) pricing as content only —
billing is manual in v1, no payment gateway, no subscription
enforcement. SEO: meta description + Open Graph tags on `/`,
`/sitemap.xml` (lists `/` and `/login`), `/robots.txt` (allows all,
points at the sitemap).

### Phase 7 — Demo Data, Docs, Deployment — DONE (2026-11-24)
Fictional seed data script (`scripts/seed_demo.py`: 1 demo user, 2
projects / 3 sites, suppliers, materials incl. low stock, deliveries
incl. one received, tasks covering every status incl. one overdue
and one due today, issues across 5 categories incl. one critical open
safety issue; re-run refuses without `--reset`, `--reset` wipes only
the demo user's data), README rewritten as the single run/deploy
guide (Render free tier + Render/Supabase Postgres checked 2026-11-24;
`create_all` honestly documented as not a migration strategy),
WINDOWS_SETUP.md updated for the final codebase, `.env.example`
completed against every Settings field, and 3 seed tests added.
**Acceptance:** fresh clone → following only the README → app runs with
demo data; full `pytest` passes; deployment steps written for the
platforms checked at that time.

**Deployment update (2026-11-25):** Aqdas chose **Neon + Vercel**
(free, no card). Vercel adapter added: `api/index.py` (Mangum) +
`vercel.json` (rewrite all paths to the function) + `mangum`
dependency + `.vercelignore`; README deployment section rewritten
for Neon + Vercel (Render kept as alternative). Verified locally:
the Mangum handler returns 200 for `/api/v1/health`, `/`, and
`/sitemap.xml`. No live deployment has been done yet — that needs
Aqdas's GitHub, Vercel, and Neon accounts.

---

## Security notes (apply from Phase 1)

- All secrets (`GROQ_API_KEY`, `SECRET_KEY`, `DATABASE_URL`) come from
  environment variables / `.env` (git-ignored). `.env.example` shows names only.
- Passwords are stored hashed only (Phase 2). JWTs expire.
- Every query is scoped to the caller's projects (Phase 2+).
- The LLM is untrusted input: its output is parsed, validated, allow-listed,
  and applied through normal service functions — never raw SQL, never eval.
- Honest limit: v1 has no rate limiting, no email verification, and no
  multi-user-per-project roles. Those are documented gaps, not hidden ones.
