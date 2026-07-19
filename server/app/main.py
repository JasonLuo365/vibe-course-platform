import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from .api import assignments, auth, courses, submissions
from .config import Settings, get_settings
from .errors import ApiError, api_error_handler
from .web import PageAuthRequired
from .web import pages as web_pages


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
    )
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
    app.include_router(web_pages.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
