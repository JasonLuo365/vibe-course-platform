import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from .api import assignments, auth, courses, submissions
from .config import Settings, get_settings
from .errors import ApiError, api_error_handler


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
    app.include_router(auth.router)
    app.include_router(courses.router)
    app.include_router(assignments.router)
    app.include_router(submissions.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
