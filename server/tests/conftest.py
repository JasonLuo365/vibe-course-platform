import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path / "data"),
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        session_secret="test-secret",
    )


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
