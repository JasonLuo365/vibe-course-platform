import pytest

from app.config import Settings
from app.main import create_app


def test_production_rejects_insecure_session_settings(tmp_path):
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        environment="production",
        session_secret="too-short",
        session_https_only=False,
        allowed_hosts=["*"],
        worker_enabled=False,
    )
    with pytest.raises(RuntimeError, match="VIBE_SESSION_SECRET"):
        create_app(settings)


def test_production_accepts_explicit_secure_settings(tmp_path):
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        environment="production",
        session_secret="a" * 48,
        session_https_only=True,
        allowed_hosts=["vibe.example.com", "localhost"],
        trust_proxy_headers=True,
        worker_enabled=False,
    )
    app = create_app(settings)
    assert app.state.settings.environment == "production"
