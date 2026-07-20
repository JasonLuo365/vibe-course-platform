import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from .api import assignments, auth, courses, reports, submissions
from .config import Settings, get_settings
from .errors import ApiError, api_error_handler
from .web import PageAuthRequired
from .web import pages as web_pages
from .web import detail as web_detail
from .web import present as web_present


templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    if getattr(settings, "worker_enabled", True) and getattr(settings, "llm_api_key", ""):
        import asyncio

        from .eval.worker import worker_loop

        asyncio.create_task(worker_loop(app))
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment == "production":
        if settings.session_secret == "dev-secret-change-me" or len(settings.session_secret) < 32:
            raise RuntimeError("Production requires a random VIBE_SESSION_SECRET of at least 32 characters.")
        if not settings.session_https_only:
            raise RuntimeError("Production requires VIBE_SESSION_HTTPS_ONLY=true.")
        if "*" in settings.allowed_hosts:
            raise RuntimeError("Production requires explicit VIBE_ALLOWED_HOSTS.")
    app = FastAPI(title="vibe-server", lifespan=lifespan)
    app.state.settings = settings

    os.makedirs(settings.data_dir, exist_ok=True)
    from .db import create_all, init_engine

    init_engine(settings.database_url)
    create_all()

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=settings.session_cookie,
        https_only=settings.session_https_only,
        max_age=settings.session_max_age_seconds,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        return response
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(
        PageAuthRequired,
        lambda req, exc: RedirectResponse(f"/login?next={exc.next_url}", status_code=302),
    )

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(auth.router)
    app.include_router(courses.router)
    app.include_router(assignments.router)
    app.include_router(submissions.router)
    app.include_router(reports.router)
    app.include_router(web_pages.router)
    app.include_router(web_detail.router)
    app.include_router(web_present.router)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "environment": settings.environment,
            "worker_enabled": settings.worker_enabled,
        }

    return app


app = create_app()

