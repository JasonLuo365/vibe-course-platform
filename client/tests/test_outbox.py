"""Tests for vibe_submit.outbox persistence."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from vibe_submit.config import Config
from vibe_submit.outbox import OutboxError, get_outbox, list_outbox, remove_outbox, retry_config, save_outbox


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    return Config(
        server_url="https://example.com",
        student_no="2026001",
        password="secret-password",
        source="global",
    )


@pytest.fixture
def manifest():
    return {
        "format_version": "1",
        "assignment_code": "HW01",
        "student_no": "2026001",
        "client_version": "0.1.0",
        "submitted_at": "2026-07-19T10:00:00Z",
        "files": [],
        "stats": {"sessions": 0, "files": 0, "bytes": 0},
    }


def _make_zip(path: Path, content: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("dummy.txt", content)
    return path


def test_save_outbox_creates_zip_and_meta(cfg, manifest, tmp_path):
    zip_path = _make_zip(tmp_path / "orig.zip")
    outbox_id = save_outbox(zip_path, manifest, cfg)
    assert outbox_id

    outbox_dir = tmp_path / ".vibe-submit" / "outbox" / outbox_id
    assert outbox_dir.exists()
    assert (outbox_dir / "orig.zip").exists()
    meta = json.loads((outbox_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["assignment_code"] == "HW01"
    assert meta["student_no"] == "2026001"
    assert meta["server_url"] == "https://example.com"
    assert meta["manifest"] == manifest


def test_list_outbox_returns_entries(cfg, manifest, tmp_path):
    zip_path = _make_zip(tmp_path / "orig.zip")
    outbox_id = save_outbox(zip_path, manifest, cfg)

    entries = list_outbox()
    assert len(entries) == 1
    assert entries[0]["id"] == outbox_id
    assert entries[0]["assignment_code"] == "HW01"
    assert entries[0]["size"] == zip_path.stat().st_size
    assert "saved_at" in entries[0]


def test_get_outbox_returns_zip_and_manifest(cfg, manifest, tmp_path):
    zip_path = _make_zip(tmp_path / "orig.zip")
    outbox_id = save_outbox(zip_path, manifest, cfg)

    returned_zip, returned_manifest = get_outbox(outbox_id)
    assert returned_zip.exists()
    assert returned_manifest == manifest


def test_get_outbox_missing_raises(cfg):
    with pytest.raises(OutboxError):
        get_outbox("does-not-exist")


def test_retry_config_uses_current_password_and_saved_server(cfg, manifest, tmp_path):
    outbox_id = save_outbox(_make_zip(tmp_path / "orig.zip"), manifest, cfg)
    active = Config("https://other.example", "2026001", "fresh-password", "global")
    merged = retry_config(outbox_id, active)
    assert merged.server_url == "https://example.com"
    assert merged.password == "fresh-password"


def test_remove_outbox_after_success(cfg, manifest, tmp_path):
    outbox_id = save_outbox(_make_zip(tmp_path / "orig.zip"), manifest, cfg)
    remove_outbox(outbox_id)
    assert outbox_id not in {item["id"] for item in list_outbox()}


def test_outbox_rejects_path_traversal(cfg):
    with pytest.raises(OutboxError, match="invalid outbox id"):
        get_outbox("../outside")


def test_list_outbox_empty_when_none(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    assert list_outbox() == []

