"""SitePilot AI — application entry point.

Phase 1 scope: app factory, /api/v1 router, error handling for API errors,
static files, and a simple Jinja2 landing page at /.
Business features arrive in later phases, one at a time.

Phase 6 adds the Jinja2 pages: /dashboard, /login (cookie-based page
auth — see app/api/deps.py), /projects/{id}, plus /sitemap.xml and
/robots.txt for basic SEO.
"""
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import COOKIE_NAME, get_page_user
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError  # noqa: F401  (re-exported for compatibility)
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import engine, get_db
from app.models.user import User
from app.services import auth_service, summary_service

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)

    # Dev convenience (Phase 2): create any missing tables. This is NOT a
    # migration strategy — create_all never alters existing tables.
    # Alembic migrations are the Phase 7 / production answer.
    # NOTE: "import app.models as ..." — a plain "import app.models" inside
    # this function would rebind the local name `app` (the FastAPI instance)
    # to the package. Learned by an actual crash in Phase 2 testing.
    import app.models as _models  # noqa: F401  (registers models on Base.metadata)

    Base.metadata.create_all(bind=engine)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.message}
        )

    app.include_router(api_router)
    app.mount(
        "/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static"
    )

    @app.get("/", include_in_schema=False)
    def home(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"app_name": settings.app_name},
        )

    # ---- SEO: sitemap + robots (Phase 6) --------------------------------

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap(request: Request):
        base = str(request.base_url).rstrip("/")
        urls = "".join(
            f"<url><loc>{base}{path}</loc></url>" for path in ("/", "/login")
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{urls}</urlset>"
        )
        return Response(content=xml, media_type="application/xml")

    @app.get("/robots.txt", include_in_schema=False)
    def robots(request: Request):
        base = str(request.base_url).rstrip("/")
        return PlainTextResponse(
            f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
        )

    # ---- HTML pages: login + dashboard + project detail (Phase 6) --------

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"app_name": settings.app_name, "error": None},
        )

    @app.post("/login", include_in_schema=False)
    def login_submit(
        request: Request,
        username: str = Form(),
        password: str = Form(),
        db: Session = Depends(get_db),
    ):
        try:
            user = auth_service.authenticate_user(db, username, password)
        except AppError:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                status_code=401,
                context={
                    "app_name": settings.app_name,
                    "error": "Invalid email or password.",
                },
            )
        token = create_access_token(user.id)
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            path="/",
            max_age=settings.access_token_expire_minutes * 60,
        )
        return response

    @app.get("/dashboard", include_in_schema=False)
    def dashboard(
        request: Request,
        db: Session = Depends(get_db),
        current_user: User | None = Depends(get_page_user),
    ):
        if current_user is None:
            return RedirectResponse(url="/login", status_code=302)
        data = summary_service.build_dashboard(db, current_user)
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"app_name": settings.app_name, "user": current_user, **data},
        )

    @app.get("/projects/{project_id}", include_in_schema=False)
    def project_page(
        project_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User | None = Depends(get_page_user),
    ):
        if current_user is None:
            return RedirectResponse(url="/login", status_code=302)
        try:
            summary = summary_service.build_project_summary(
                db, current_user, project_id
            )
        except AppError:
            return templates.TemplateResponse(
                request=request,
                name="not_found.html",
                status_code=404,
                context={
                    "app_name": settings.app_name,
                    "message": "That project does not exist.",
                },
            )
        return templates.TemplateResponse(
            request=request,
            name="project_detail.html",
            context={
                "app_name": settings.app_name,
                "user": current_user,
                "summary": summary,
            },
        )

    return app


app = create_app()
