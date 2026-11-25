# SitePilot AI — Construction Operations Follow-up Assistant

Simple AI-powered operations follow-up for small construction contractors
and property developers: materials and stock alerts, tasks and deadlines,
site issues, plain-language site updates converted by an LLM into
structured, validated actions, and a daily project summary.

**Demo system — all data is fictional.**

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design, database
relationships, API list, user workflows, and the phased build plan.
See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for the same setup on Windows
(PowerShell).

## Status

All seven phases are complete:

1. **Foundation** — config from env, DB session, health endpoint, landing page.
2. **Auth + Projects & Sites** — JWT login, ownership-checked CRUD.
3. **Materials, Suppliers, Deliveries** — transactional stock updates, low-stock alerts.
4. **Tasks & Site Issues** — computed overdue detection, validated enums.
5. **LLM site updates (Groq)** — structured output, bounded action allow-list, audit trail.
6. **Daily summary + Dashboard** — summary generated on read, cookie page login, pricing page, basic SEO.
7. **Demo data, docs, deployment** — fictional seed script, this guide, deployment instructions for the platforms checked in Nov 2026.

## Run locally

```bash
cd sitepilot-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your own values
uvicorn app.main:app --reload
```

- Landing page: http://127.0.0.1:8000/
- Log in / dashboard: http://127.0.0.1:8000/login and /dashboard
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/v1/health

For real use set `DATABASE_URL` in `.env` to PostgreSQL, e.g.
`postgresql+psycopg2://user:password@localhost:5432/sitepilot`.
SQLite works for a quick local look and is what the tests use.
PostgreSQL is the production target: the models stay
PostgreSQL-compatible and the suite includes a live-PostgreSQL test
(see "Tests" below).

## Demo data (seed script)

`scripts/seed_demo.py` creates a realistic fictional dataset — no
Groq call, no `GROQ_API_KEY` needed — through the normal service
functions, so the same ownership and validation rules apply as
through the API:

```bash
python scripts/seed_demo.py            # seed once
python scripts/seed_demo.py --reset    # wipe the demo data and re-seed
python -m scripts.seed_demo            # same as the first form
```

What it creates: 1 demo user, 2 projects with 3 sites, 3 suppliers,
6 materials (Sand and Paint are low stock), 3 deliveries (1 received
— cement stock goes 120 → 320 bags — and 2 pending), 6 tasks covering
every status (1 overdue, 1 due today, 1 with no due date), and 5
issues across 5 categories including 1 critical open safety issue
(missing scaffolding guardrail on Tower B).

**Demo login — throwaway demo credentials only, never a real account:**

- email: `demo@sitepilot.example`
- password: `demo-sitepilot-2026`

**Re-run rule:** running the script a second time *without* `--reset`
refuses cleanly (message + exit code 2) and leaves existing data
untouched. With `--reset` it deletes **only the demo user's data**
and re-seeds. It never touches other users' data.

## Tests

```bash
pytest
# or, for the short summary:
python -m pytest -q
```

Tests use an in-memory SQLite database and never call the real Groq
API (LLM tests use a mocked response). Expected result:
**157 passed, 1 skipped** (the skipped test is the live-PostgreSQL
test — see below). The suite takes a few minutes, mostly real bcrypt
password hashing in the auth tests.

### Verify against your own PostgreSQL (optional)

The default test run uses SQLite and skips the live-PostgreSQL test.
To run the end-to-end flow against a real PostgreSQL server:

```bash
# create an empty database first, e.g. sitepilot_test
SITEPILOT_PG_TEST_URL=postgresql+psycopg2://user:password@localhost:5432/sitepilot_test python -m pytest tests/test_postgres_compat.py
```

(PowerShell: set `$env:SITEPILOT_PG_TEST_URL = "..."` on its own line first.)
Note: quantities/prices are Decimal and are returned in JSON as strings
like "210.00" — that preserves exact values; parse them as numbers client-side.

## Configuration & secrets

Everything is configured through environment variables — see
`.env.example` (it lists every `Settings` field from
`app/core/config.py`). Never commit a real `.env`, and never paste a
real API key into code, tests, or chat.

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL in real use; SQLite only for local experiments / tests |
| `SECRET_KEY` | Yes | Long random value (32+ bytes) for JWT signing. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `APP_ENV` | No | `development` / `production` / `test` |
| `DEBUG` | No | `true` locally, `false` when deployed |
| `GROQ_API_KEY` | No | Optional. Without it the app runs fine, but `POST /site-updates` returns 503 ("LLM is not configured") |
| `GROQ_MODEL` | No | Default `openai/gpt-oss-20b` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `60` |
| `JWT_ALGORITHM` | No | Default `HS256` |
| `APP_NAME`, `APP_VERSION` | No | Display only |

## Deployment

**Status: not deployed yet.** No hosting account has been created and
no live URL exists. The steps below were written from the platforms'
own documentation as checked on **2026-11-25**; re-check the pricing
pages before you deploy, because free tiers change.

### Recommended free path: Vercel (app) + Neon (Postgres)

Chosen 2026-11-25: both free tiers need **no credit card**, and
together they cost $0. (Render + Supabase/Render Postgres remain a
documented alternative below.)

**Vercel (Hobby, free)** — the FastAPI app runs as a Python
serverless function. `api/index.py` (Mangum adapter) + `vercel.json`
are the only Vercel-specific files; the app itself is unchanged and
still runs locally under uvicorn. From Vercel's own limits as
checked Nov 2026:

- Hobby costs $0, no credit card, 100 GB bandwidth, 1M function
  invocations, 4 hours active CPU per month.
- The filesystem is **ephemeral**: nothing written to disk survives
  between invocations. **Do not use SQLite on Vercel** — use Neon.
- Serverless function timeout applies (commonly cited as 60s on
  Hobby; Vercel's newer Fluid compute can allow more — check the
  current docs if a Groq call ever times out). Groq calls are
  normally a few seconds, so this fits, but a slow LLM response
  can hit the limit where a long-running server would not.
- Cold starts: the first request after idle takes a few seconds.
- **Honest terms note:** Vercel's Hobby plan is licensed for
  personal, non-commercial use. A site that generates revenue or
  serves paying clients belongs on Pro ($20/month) under Vercel's
  terms. Hobby is right for this demo/portfolio stage; budget Pro
  for the day the product starts charging.

**Neon (Free)** — serverless Postgres, from Neon's pricing as
checked Nov 2026:

- **$0, permanent, no credit card.** 1 GB storage per project,
  100 CU-hours of compute per project per month, up to 100
  projects. Compute scales to zero after 5 minutes idle and wakes
  on the first query.
- Limits never delete your data: at the CU-hour or egress limit,
  compute is suspended until the next billing period; over storage,
  writes fail until you free space.
- Better than Supabase's free tier for this app: Supabase pauses
  a project after 1 week idle and caps storage at 500 MB; Neon
  does not pause projects and gives 1 GB.
- **Use the pooled connection string** (host ends in `-pooler`) —
  serverless functions open many short-lived connections, and the
  pooler handles that. Neon requires SSL: the connection string
  includes `sslmode=require`.

### Steps (Vercel + Neon)

1. Push the code to a GitHub repository (do **not** commit `.env`).
2. Create the Neon database first (Neon dashboard → New Project,
   Free plan) and copy its **pooled** connection string
   (`postgresql://user:password@<host>-pooler.<region>.neon.tech/<db>?sslmode=require`).
3. Create the Vercel project (Dashboard → Add New → Project →
   import the GitHub repo):
   - Framework preset: **Other** (this is not a Next.js app).
   - No build command and no custom start command are needed:
     `vercel.json` routes every path to `api/index.py`.
   - Set `PYTHON_VERSION=3.12` as an environment variable so the
     runtime matches local development.
4. Set these environment variables in the Vercel dashboard (never
   in code):
   - `DATABASE_URL` — the Neon pooled connection string above.
   - `SECRET_KEY` — a long random value (generate one; see above).
   - `APP_ENV=production`, `DEBUG=false`
   - `GROQ_API_KEY` — optional; leave unset and the LLM endpoints
     return a clear 503, everything else works.
5. Deploy. On startup the app runs `Base.metadata.create_all`, so
   the tables are created automatically on first boot.
6. Check `https://<your-project>.vercel.app/api/v1/health`, then
   open the landing page at `/`.

### Alternative free path: Render web service + hosted Postgres

If Vercel's serverless limits ever get in the way, Render runs the
same code as a plain long-running uvicorn server with **no code
changes** (start command `uvicorn app.main:app --host 0.0.0.0
--port $PORT`). Render Free: $0, no card, 750 instance hours/month,
spins down after 15 minutes idle (~1 minute to wake). Pair it with
Neon (above) or Supabase Free (500 MB, 2 projects, pauses after 1
week idle) or Render's own free Postgres (1 GB, **expires 30 days
after creation**). The `api/index.py` and `vercel.json` files are
simply ignored on Render.

### Seeding demo data on the deployed instance

Free Vercel functions have **no shell access**, so you cannot run the
seed script on the server itself. Instead, run it from your own
machine pointed at the hosted database:

```bash
DATABASE_URL='postgresql+psycopg2://user:password@<host>:5432/<db>' \
  SECRET_KEY='a-long-random-value-for-this-run-only' \
  python scripts/seed_demo.py
```

The script creates any missing tables first, then seeds. Use
`--reset` only if you want to wipe and re-seed the demo user.
(Keep that connection string private — it is a real credential,
unlike the demo login.)

### Honest notes on production readiness

- **Tables are created by `create_all` on startup.** That is a dev
  convenience, not a migration strategy: `create_all` never alters
  existing tables, so a schema change to a live database would need
  manual work. Production should use **Alembic migrations, which are
  NOT set up in v1**. Do not treat a `create_all` deploy as a
  migration plan.
- The free tiers above are for demos and hobby use. A real
  production deploy needs a paid instance (no spin-down), a paid
  Postgres (no 30-day expiry / pausing, with backups), a real
  `SECRET_KEY`, and `DEBUG=false`.

## API overview

Base prefix `/api/v1`. JSON API uses Bearer JWTs
(`Authorization: Bearer <token>`, 401 when absent). HTML pages use
the same JWT in an HttpOnly `sitepilot_token` cookie (see below).
Another user's record is a 404, never a 403.

| Area | Endpoints |
|---|---|
| Health | `GET /health`, `GET /api/v1/health` |
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Projects | `POST /projects`, `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}`, `DELETE /projects/{id}` |
| Sites | `POST /projects/{project_id}/sites`, `GET /projects/{project_id}/sites`, `GET /sites/{id}`, `PATCH /sites/{id}` |
| Suppliers | `POST /suppliers`, `GET /suppliers`, `GET /suppliers/{id}`, `PATCH /suppliers/{id}` |
| Materials | `POST /materials`, `GET /materials`, `GET /materials/{id}`, `PATCH /materials/{id}`, `GET /materials/alerts/stock` |
| Deliveries | `POST /deliveries`, `GET /deliveries`, `PATCH /deliveries/{id}`, `POST /deliveries/{id}/receive` (receiving a delivery updates stock transactionally, exactly once) |
| Tasks | `POST /tasks`, `GET /tasks`, `GET /tasks/overdue`, `GET /tasks/{id}`, `PATCH /tasks/{id}` |
| Site issues | `POST /issues`, `GET /issues`, `GET /issues/{id}`, `PATCH /issues/{id}` |
| Site updates (LLM) | `POST /site-updates` (raw text → structured, validated, bounded actions), `GET /site-updates`, `GET /site-updates/{id}` (per-action audit) |
| Daily summary | `GET /projects/{project_id}/summary/today` |

### What each phase added (detail)

**Summary (Phase 6)** — `GET /api/v1/projects/{project_id}/summary/today`
returns one model with counts + item lists, all computed from live
data: overdue tasks, tasks due today, upcoming tasks (next 7 days),
low-stock materials, open issues (critical first), pending deliveries,
and the 5 most recent site updates. Nothing is stored — there is no
summary table.

**Pages (Phase 6, Jinja2, no `/api` prefix)** — `/` landing
(positioning statement, features, pricing: Starter $29 /
Professional $79 / Business $199 per month as content only — billing
is manual in v1, no payment gateway, no subscription enforcement),
`/login` (form), `/dashboard` (the user's projects, overdue tasks,
low-stock alerts, open critical/high issues), `/projects/{id}` (that
project's daily summary). SEO — `/sitemap.xml` (lists `/` and
`/login`), `/robots.txt` (allows all, points at the sitemap), meta
description + Open Graph tags on the landing page.

**Page login (cookie auth, Phase 6)** — the JSON API still uses
Bearer JWTs only. Browsers do not send an Authorization header on
plain navigation, so `POST /login` sets an HttpOnly
`sitepilot_token` cookie carrying the same JWT (`SameSite=Lax`,
expires with the token); page routes accept the token from the
Authorization header or that cookie. An unauthenticated visit to
`/dashboard` or `/projects/{id}` redirects to `/login` (302). See
ARCHITECTURE.md Phase 6 for the full decision.

**Site updates (Phase 5, LLM)** — `POST /site-updates` (body:
`site_id` + `raw_text`). The manager types plain language, e.g.
*"Cement delivery of 200 bags arrived from Ali Traders. Tower B
plastering is delayed 2 days because of rain. Urgent: scaffolding
safety issue on Block C."* Groq returns structured JSON, which is
Pydantic-validated and then applied only through a bounded allow-list
— `record_delivery`, `create_issue`, `create_task`,
`update_task_status`, `update_task_due_date` — with every referenced
id checked against the caller's own records. All actions in one update
are validated first, then applied in a single transaction: if any
action is invalid, the LLM output is unparseable, or Groq is
unreachable, nothing business-related is written (zero partial
writes), but the failed attempt itself is recorded as a `site_update`
with `status=failed` and a human-readable reason, so the audit trail
shows what happened. A successful update returns
`status=processed` with per-action results (what was understood, what
changed, what was rejected and why). If `GROQ_API_KEY` is not set,
`POST /site-updates` returns 503 with a clear "LLM is not
configured" error. Tests use a mocked Groq response only — they never
call the real Groq API and cost nothing.

**Tasks & issues (Phase 4)** — Tasks: `POST /tasks`,
`GET /tasks` (optional `project_id`, `site_id`, `status` filters),
`GET /tasks/overdue`, `GET /tasks/{id}`, `PATCH /tasks/{id}`. A task
belongs to a project (required) and optionally a site in that project;
`due_date` is optional and `is_overdue`/`overdue` are computed
(`due_date` past and status not `done`). `assigned_to` is a display
reference to an existing user id only — it grants no access. Site
issues: `POST /issues`, `GET /issues` (optional `site_id`, `category`,
`priority`, `status` filters), `GET /issues/{id}`,
`PATCH /issues/{id}`. An issue attaches to a site only;
`category`/`priority`/`status` are validated against fixed enums,
and `reported_by` is set server-side from the authenticated user.

## Project structure

```
sitepilot-ai/
├── ARCHITECTURE.md          Design contract + phased plan
├── README.md                This guide (run / test / deploy)
├── WINDOWS_SETUP.md         Windows (PowerShell) setup guide
├── requirements.txt         Dependencies (no version pins; added per phase)
├── .env.example             Every config variable, no real secrets
├── app/
│   ├── main.py              App factory, pages, SEO routes
│   ├── core/                config.py (env settings), security.py, errors.py
│   ├── db/                  base.py, session.py (engine + get_db)
│   ├── models/              SQLAlchemy models
│   ├── schemas/             Pydantic request/response schemas
│   ├── services/            Business logic (no HTTP, no LLM calls here)
│   ├── llm/                 Groq client + structured parsing + validation
│   ├── api/v1/              Router + one route file per resource
│   ├── templates/           Jinja2 pages
│   └── static/              Plain CSS / JS, no build step
├── scripts/
│   └── seed_demo.py         Fictional demo-data seed (Phase 7)
└── tests/                   pytest suite; every phase adds tests for its work
```

## Known limitations (v1, documented honestly)

- **No rate limiting** on any endpoint.
- **No email verification** — registration only checks the email format.
- **No multi-user roles** — one user owns their projects; there is no
  sharing, no per-project members, no admin role. `assigned_to` on a
  task is a display reference only.
- **`create_all`, not migrations** — tables are created on startup;
  there is no Alembic setup, so schema changes to a live database
  need manual handling (see "Deployment").
- **No payments** — pricing on the landing page is content only;
  billing is manual. No subscription enforcement.
- **LLM is advisory only by design** — it proposes actions through a
  fixed allow-list; it never executes SQL or touches the database
  directly. Site updates need `GROQ_API_KEY`; without it they 503.
- **Free-tier hosting limits apply** — see "Deployment": spin-down,
  expiry/pausing, no backups on the free database options.
- **Fictional demo data only** — the seed script and all examples use
  invented names; nothing here is a real company or person.
