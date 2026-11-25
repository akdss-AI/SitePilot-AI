# SitePilot AI — Windows Setup Guide

Setup for the complete (Phases 1–7) codebase on Windows, using
PowerShell. Everything below uses fictional/demo settings only. Never
share your real `.env` file with anyone.

## 0. What you need first

- **Python 3.11 or newer (3.12 recommended).** Install from
  https://www.python.org/downloads/ and tick **"Add python.exe to PATH"**
  during installation.
- Verify in a **new** PowerShell window:

```powershell
py --version
```

You should see something like `Python 3.12.x`.

## 1. Put the code in your folder

This ZIP contains one top-level folder: `sitepilot-ai`.

1. Open the ZIP, open the `sitepilot-ai` folder inside it.
2. Copy **its contents** (the `app` folder, `tests` folder, `scripts`
   folder, `requirements.txt`, etc.) into your existing empty folder,
   e.g. `...\SitePilot AI`.
3. Your folder should now contain `app`, `tests`, `scripts`,
   `requirements.txt`, `.env.example`, `README.md`,
   `ARCHITECTURE.md`, `WINDOWS_SETUP.md` directly inside it —
   not nested inside another `sitepilot-ai` folder.

## 2. Create a virtual environment and install dependencies

Open PowerShell **inside** your `SitePilot AI` folder
(Shift + Right-click in the folder → "Open in Terminal", or `cd` to it):

```powershell
cd "C:\path\to\SitePilot AI"
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `Activate.ps1` is blocked by the execution policy, run this once for
the current window only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

You know the environment is active when the prompt starts with `(.venv)`.

## 3. Create your local .env file

```powershell
Copy-Item .env.example .env
notepad .env
```

In Notepad:

- Leave `DATABASE_URL=sqlite:///./sitepilot_dev.db` as it is for now
  (SQLite needs no installation; PostgreSQL is the production target
  — see step 7).
- Replace `SECRET_KEY=change-me-in-your-real-env` with a long random
  value (32+ characters). Generate one with this PowerShell command
  and paste the result after `SECRET_KEY=`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

- `GROQ_API_KEY=` is **optional**. Leave it empty and the app runs
  fine — only the LLM site-update endpoint (`POST /site-updates`)
  returns a 503 "LLM is not configured" until you add a real Groq key.
  To use it, paste your Groq API key after `GROQ_API_KEY=`.
  Never share that key with anyone.

Save and close Notepad. **Never commit, upload, or share this `.env`.**

## 4. Run the app

```powershell
uvicorn app.main:app --reload
```

Then open in your browser:

- Landing page: http://127.0.0.1:8000/
- Log in / dashboard: http://127.0.0.1:8000/login and /dashboard
- Interactive API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/v1/health

Stop the server with `Ctrl + C`.

## 5. Seed the fictional demo data (optional, recommended)

With the virtual environment active, from the project folder:

```powershell
python scripts\seed_demo.py
```

This creates a demo account and a realistic fictional dataset
(2 projects, 3 sites, suppliers, materials with low stock, deliveries,
tasks including an overdue one, and site issues including a critical
safety issue). No Groq key is needed for seeding.

Log in with the throwaway demo credentials (demo only, never a real
account):

- email: `demo@sitepilot.example`
- password: `demo-sitepilot-2026`

Then open http://127.0.0.1:8000/dashboard — you will see the overdue
task, the low-stock alerts, and the critical issue at a glance.

Running the script a second time without `--reset` refuses cleanly
and changes nothing. To wipe the demo data and re-seed:

```powershell
python scripts\seed_demo.py --reset
```

## 6. Run the tests

With the virtual environment active:

```powershell
python -m pytest -q
```

Expected result for this final export: **157 passed, 1 skipped**.
The skipped test is the live-PostgreSQL test (it only runs when
`SITEPILOT_PG_TEST_URL` is set — see step 7). The suite takes a few
minutes — most of that is real bcrypt password hashing in the auth
tests. Tests use an in-memory database and never call the real Groq
API, so they are safe to run any time.

## 7. Optional: use PostgreSQL instead of SQLite

PostgreSQL is the production target, and the project includes a test
that runs the end-to-end flow against a real PostgreSQL server:

1. Install PostgreSQL for Windows and create a database, e.g. `sitepilot`.
2. In `.env`, replace the `DATABASE_URL` line with:

```
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/sitepilot
```

If your password contains special characters like `@`, `#` or `:`, they
must be URL-encoded in this string.
3. Restart the app. Tables are created automatically on startup.
4. To run the live-PostgreSQL test, create an empty test database
   (e.g. `sitepilot_test`) and run:

```powershell
$env:SITEPILOT_PG_TEST_URL = "postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/sitepilot_test"
python -m pytest tests\test_postgres_compat.py -q
```

## 8. What you can try next

- **Dashboard flow:** log in as the demo user, open a project page —
  it shows that project's daily summary (overdue, due today, low
  stock, open issues, pending deliveries).
- **API flow in `/docs`:** `POST /api/v1/auth/register` →
  `POST /api/v1/auth/login` (copy the `access_token`) → click
  **Authorize** and paste the token → `POST /api/v1/projects`,
  then add sites, suppliers, materials and tasks.
- **LLM site update (needs `GROQ_API_KEY`):** `POST /api/v1/site-updates`
  with a `site_id` and plain-language `raw_text`, e.g.
  *"Cement delivery of 200 bags arrived from Ravi Building Supplies.
  Tower B plastering is delayed 2 days because of rain. Urgent:
  scaffolding safety issue on Block C."* — the response shows what
  was understood, what changed, and what was rejected and why.
- **Deployment:** see the "Deployment" section in `README.md`
  (Render free tier + hosted Postgres, checked Nov 2026). Nothing
  is deployed yet — those are instructions to follow when ready.

## Troubleshooting

| Problem | Fix |
|---|---|
| `py` is not recognised | Python was installed without PATH. Reinstall from python.org and tick "Add python.exe to PATH", then open a new PowerShell. |
| `Activate.ps1 cannot be loaded` | Use the `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` command in step 2. |
| Port 8000 already in use | Run on another port: `uvicorn app.main:app --reload --port 8001` |
| `pip install` fails on a package | Make sure the prompt shows `(.venv)` and your Python is 3.11+. All dependencies in `requirements.txt` ship prebuilt Windows wheels. |
| Health endpoint says `"database": "unavailable"` | Check the `DATABASE_URL` line in `.env` for typos, and that the database exists if you switched to PostgreSQL. |
| `POST /site-updates` returns 503 | `GROQ_API_KEY` is empty in `.env`. Add a real Groq key (step 3) or skip the LLM feature — the rest of the app works without it. |
| Seed script says "already exists" | The demo user is already seeded. Use `python scripts\seed_demo.py --reset` to wipe and re-seed, or just log in with the demo credentials. |
