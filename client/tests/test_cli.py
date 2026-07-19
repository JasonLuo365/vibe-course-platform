"""Tests for vibe_submit.cli submit/retry/doctor commands."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from vibe_submit.api import ApiError
from vibe_submit.collect import FileEntry
from vibe_submit.config import Config
from vibe_submit.sessions import SessionInfo


def _make_config():
    return Config(
        server_url="https://example.com",
        student_no="2026001",
        submit_token="secret-token",
        source="global",
    )


def _make_session(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    session_path = tmp_path / "session.jsonl"
    session_path.write_text("{}", encoding="utf-8")
    return SessionInfo(
        path=session_path,
        session_id="s1",
        cwd=str(project),
        started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
    )


def _run(args, monkeypatch):
    """Run CLI main with argv and return captured SystemExit code and output."""
    import io

    from vibe_submit import cli

    captured = {"code": None, "stdout": "", "stderr": ""}

    def fake_exit(code=0):
        captured["code"] = code
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)
    monkeypatch.setattr(cli, "_confirm_server_change", lambda url: True)

    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    try:
        cli.main([str(a) for a in args])
    except SystemExit as exc:
        captured["code"] = exc.code

    captured["stdout"] = stdout.getvalue()
    captured["stderr"] = stderr.getvalue()
    return captured


def test_submit_success_with_yes(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(
        cli,
        "get_meta",
        lambda cfg, code: {"assignment_code": code, "accepts": True, "opens_at": "2026-07-19T00:00:00Z"},
    )
    session = _make_session(tmp_path)
    monkeypatch.setattr(cli, "find_sessions", lambda *a, **kw: [session])
    file_entry = FileEntry("main.py", tmp_path / "main.py", 4)
    (tmp_path / "main.py").write_text("print(1)", encoding="utf-8")
    monkeypatch.setattr(cli, "collect_project", lambda root: ([file_entry], [".env"]))

    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"z")
    manifest = {"assignment_code": "HW01", "student_no": "2026001", "stats": {"files": 1, "bytes": 4}}
    monkeypatch.setattr(
        cli,
        "build_package",
        lambda *a, **kw: (zip_path, manifest, {"sessions": 1, "files": 1, "bytes": 4}),
    )
    monkeypatch.setattr(
        cli,
        "upload",
        lambda cfg, zip_path, manifest, force=False, transport=None: {
            "submission_id": "sub-1",
            "attempt_no": 1,
        },
    )

    captured = _run(["submit", "--code", "HW01", "--yes"], monkeypatch)
    assert captured["code"] == 0
    assert "sub-1" in captured["stdout"]
    assert "Code files: 1" in captured["stdout"]
    assert ".env" in captured["stdout"]


def test_submit_rejects_exits_two(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(
        cli,
        "get_meta",
        lambda cfg, code: {"assignment_code": code, "accepts": False},
    )

    captured = _run(["submit", "--code", "HW01", "--yes"], monkeypatch)
    assert captured["code"] == 2
    assert "not accepting" in captured["stderr"].lower()


def test_submit_409_without_force_exits_three(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(
        cli,
        "get_meta",
        lambda cfg, code: {"assignment_code": code, "accepts": True, "opens_at": "2026-07-19T00:00:00Z"},
    )
    session = _make_session(tmp_path)
    monkeypatch.setattr(cli, "find_sessions", lambda *a, **kw: [session])
    monkeypatch.setattr(cli, "collect_project", lambda root: ([], []))
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"z")
    monkeypatch.setattr(
        cli,
        "build_package",
        lambda *a, **kw: (zip_path, {"assignment_code": "HW01"}, {"sessions": 0, "files": 0, "bytes": 0}),
    )
    monkeypatch.setattr(
        cli,
        "upload",
        lambda *a, **kw: (_ for _ in ()).throw(
            ApiError(409, "DUPLICATE_SUBMISSION", "already submitted", {})
        ),
    )

    captured = _run(["submit", "--code", "HW01", "--yes"], monkeypatch)
    assert captured["code"] == 3
    assert "--force" in captured["stderr"]


def test_submit_force_passes_force_true(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(
        cli,
        "get_meta",
        lambda cfg, code: {"assignment_code": code, "accepts": True, "opens_at": "2026-07-19T00:00:00Z"},
    )
    session = _make_session(tmp_path)
    monkeypatch.setattr(cli, "find_sessions", lambda *a, **kw: [session])
    monkeypatch.setattr(cli, "collect_project", lambda root: ([], []))
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"z")
    manifest = {"assignment_code": "HW01"}
    monkeypatch.setattr(
        cli,
        "build_package",
        lambda *a, **kw: (zip_path, manifest, {"sessions": 0, "files": 0, "bytes": 0}),
    )

    calls = []

    def fake_upload(cfg, zip_path, manifest, force=False, transport=None):
        calls.append(force)
        return {"submission_id": "sub-2", "attempt_no": 1}

    monkeypatch.setattr(cli, "upload", fake_upload)

    captured = _run(["submit", "--code", "HW01", "--yes", "--force"], monkeypatch)
    assert captured["code"] == 0
    assert calls == [True]


def test_submit_network_error_saves_outbox(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(
        cli,
        "get_meta",
        lambda cfg, code: {"assignment_code": code, "accepts": True, "opens_at": "2026-07-19T00:00:00Z"},
    )
    session = _make_session(tmp_path)
    monkeypatch.setattr(cli, "find_sessions", lambda *a, **kw: [session])
    monkeypatch.setattr(cli, "collect_project", lambda root: ([], []))
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"z")
    manifest = {"assignment_code": "HW01"}
    monkeypatch.setattr(
        cli,
        "build_package",
        lambda *a, **kw: (zip_path, manifest, {"sessions": 0, "files": 0, "bytes": 0}),
    )
    monkeypatch.setattr(
        cli,
        "upload",
        lambda *a, **kw: (_ for _ in ()).throw(ApiError(0, "NETWORK", "offline", None)),
    )

    saved = []

    def fake_save_outbox(zip_path, manifest, cfg):
        saved.append((zip_path, manifest))
        return "OB-123"

    monkeypatch.setattr(cli, "save_outbox", fake_save_outbox)

    captured = _run(["submit", "--code", "HW01", "--yes"], monkeypatch)
    assert captured["code"] == 1
    assert saved
    assert "OB-123" in captured["stderr"]
    assert "retry" in captured["stderr"].lower()


def test_submit_interactive_confirm(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(
        cli,
        "get_meta",
        lambda cfg, code: {"assignment_code": code, "accepts": True, "opens_at": "2026-07-19T00:00:00Z"},
    )
    session = _make_session(tmp_path)
    monkeypatch.setattr(cli, "find_sessions", lambda *a, **kw: [session])
    monkeypatch.setattr(cli, "collect_project", lambda root: ([], []))
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"z")
    monkeypatch.setattr(
        cli,
        "build_package",
        lambda *a, **kw: (zip_path, {"assignment_code": "HW01"}, {"sessions": 0, "files": 0, "bytes": 0}),
    )
    monkeypatch.setattr(
        cli,
        "upload",
        lambda *a, **kw: {"submission_id": "sub-3", "attempt_no": 1},
    )

    inputs = iter(["y"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    captured = _run(["submit", "--code", "HW01"], monkeypatch)
    assert captured["code"] == 0
    assert "sub-3" in captured["stdout"]


def test_retry_lists_outbox(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(
        cli,
        "list_outbox",
        lambda: [
            {"id": "OB-1", "assignment_code": "HW01", "size": 1024, "saved_at": "2026-07-19T10:00:00Z"}
        ],
    )

    captured = _run(["retry"], monkeypatch)
    assert captured["code"] == 0
    assert "OB-1" in captured["stdout"]
    assert "HW01" in captured["stdout"]


def test_retry_uploads_outbox(monkeypatch, tmp_path):
    from vibe_submit import cli

    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"z")
    manifest = {"assignment_code": "HW01"}

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(cli, "get_outbox", lambda oid: (zip_path, manifest))
    monkeypatch.setattr(
        cli,
        "upload",
        lambda cfg, zip_path, manifest, force=False, transport=None: {
            "submission_id": "sub-r",
            "attempt_no": 2,
        },
    )

    captured = _run(["retry", "OB-1"], monkeypatch)
    assert captured["code"] == 0
    assert "sub-r" in captured["stdout"]


def test_doctor_reports_config_status(monkeypatch, tmp_path):
    from vibe_submit import cli

    monkeypatch.setattr(cli, "load_config", lambda project_root=None, confirm=None: _make_config())
    monkeypatch.setattr(cli, "_codex_home", lambda: tmp_path / ".codex")
    (tmp_path / ".codex" / "sessions").mkdir(parents=True)

    def handler(request: httpx.Request):
        assert str(request.url).endswith("/health")
        return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(cli, "_health_transport", httpx.MockTransport(handler))

    captured = _run(["doctor"], monkeypatch)
    assert captured["code"] == 0
    assert "config" in captured["stdout"].lower()
    assert "codex" in captured["stdout"].lower()
    assert "server" in captured["stdout"].lower()
