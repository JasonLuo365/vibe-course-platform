from fastapi import FastAPI

from .config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="vibe-server")
    app.state.settings = settings

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
