"""Tests for vibe_submit.config loading and project/global rules."""

from __future__ import annotations

import pytest

from vibe_submit.config import ConfigError, ServerChangeRequired, load_config, write_config


def _write_global(home: Path, **fields):
    config_dir = home / ".vibe-submit"
    config_dir.mkdir(parents=True, exist_ok=True)
    lines = [f'{k} = "{v}"\n' for k, v in fields.items()]
    (config_dir / "config.toml").write_text("".join(lines), encoding="utf-8")


def test_load_global_config(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    _write_global(tmp_path, server_url="https://global.example", student_no="2026001", password="pw")

    cfg = load_config()
    assert cfg.server_url == "https://global.example"
    assert cfg.student_no == "2026001"
    assert cfg.password == "pw"
    assert cfg.source == "global"


def test_missing_global_config_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    with pytest.raises(ConfigError):
        load_config()


def test_project_server_url_conflict_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    _write_global(tmp_path, server_url="https://global.example", student_no="2026001", password="pw")

    project = tmp_path / "project"
    project.mkdir()
    (project / ".vibe-submit.toml").write_text(
        'server_url = "https://project.example"\n', encoding="utf-8"
    )

    with pytest.raises(ServerChangeRequired) as exc_info:
        load_config(project)
    assert exc_info.value.url == "https://project.example"


def test_project_server_url_conflict_confirmed(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    _write_global(tmp_path, server_url="https://global.example", student_no="2026001", password="pw")

    project = tmp_path / "project"
    project.mkdir()
    (project / ".vibe-submit.toml").write_text(
        'server_url = "https://project.example"\n', encoding="utf-8"
    )

    cfg = load_config(project, confirm=lambda url: True)
    assert cfg.server_url == "https://project.example"
    assert cfg.source == "project"


def test_project_server_url_same_keeps_global(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    _write_global(tmp_path, server_url="https://same.example", student_no="2026001", password="pw")

    project = tmp_path / "project"
    project.mkdir()
    (project / ".vibe-submit.toml").write_text(
        'server_url = "https://same.example"\n', encoding="utf-8"
    )

    cfg = load_config(project)
    assert cfg.server_url == "https://same.example"
    assert cfg.source == "project"


def test_write_config_creates_file(tmp_path):
    path = tmp_path / "config.toml"
    write_config(
        path,
        {"server_url": "https://w.example", "student_no": "2026002", "password": "pw"},
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "https://w.example" in text
    assert "2026002" in text


@pytest.mark.parametrize("url", ["http://class.example", "https://class.example/path", "file:///tmp/x"])
def test_load_config_rejects_non_https_or_non_origin_server_url(tmp_path, monkeypatch, url):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    _write_global(tmp_path, server_url=url, student_no="2026001", password="pw")
    with pytest.raises(ConfigError, match="HTTPS origin"):
        load_config()

