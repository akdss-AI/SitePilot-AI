"""Vercel serverless entrypoint for SitePilot AI.

Vercel's Python runtime serves every file under api/ as a serverless
function. Mangum adapts the FastAPI ASGI app to that environment, so
the same app that runs locally under uvicorn runs here unchanged —
same routes, same Jinja2 pages, same JSON API.

Nothing in app/ knows about Vercel: this file is the only
deployment-specific adapter. Local development still uses
`uvicorn app.main:app`.

Deploy notes (see README "Deploy to Vercel + Neon"):
- `vercel.json` rewrites every path to this function.
- Environment variables (DATABASE_URL, SECRET_KEY, GROQ_API_KEY, ...)
  are set in the Vercel dashboard, never in this repo.
"""
from mangum import Mangum

from app.main import app

handler = Mangum(app)
