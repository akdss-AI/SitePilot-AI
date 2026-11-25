"""Aggregates all /api/v1 routers in one place.

Each new resource adds exactly one include_router line here in its phase.
"""
from fastapi import APIRouter

from app.api.v1.routes import auth, health, inventory, projects, site_updates, summary, tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(inventory.router)
api_router.include_router(tasks.router)
api_router.include_router(site_updates.router)
api_router.include_router(summary.router)
