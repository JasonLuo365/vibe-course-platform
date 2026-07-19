"""End-to-end tests using a MockTransport-backed mini server."""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from vibe_submit import cli
from vibe_submit import api as api_module
from vibe_submit.config import write_config
from vibe_submit.mcp_server import (
    get_assignment_meta,
    get_submission_status,
    preview_submission,
    submit_homework,
)
from vibe_submit.preview import get_meta as preview_get_meta


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Create an isolated codex home, global config, project and sessions."""
    vibe_home = tmp_path / "vibe_home"
    codex_home = tmp_path / "codex"
    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "main.py").write_text("print('hello vibe-submit')\n", encoding="utf-8")
    (project / "screenshots").mkdir(parents=True, exist_ok=True)
    (project / "screenshots" / "one.png").write_bytes(b"\x89PNG\r\n\x1a\nfake png data")

    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    project_cwd = str(project.resolve())
    for idx, name in enumerate(("session_a.jsonl", "session_b.jsonl"), start=1):
        path = sessions_dir / name
        meta = {
            "type": "session_meta",
            "payload": {
                "id": f"s{idx}",
                "timestamp": f"2026-07-19T1{idx}:00:00Z",
                "cwd": project_cwd,
            },
        }
        message = {
            "type": "response_item",
            "payload": {
                "role": "user",
                "timestamp": f"2026-07-19T1{idx}:01:00Z",
            },
        }
        path.write_text(
            json.dumps(meta) + "\n" + json.dumps(message) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(vibe_home))
    monkeypatch.setenv("VIBE_CODEX_HOME", str(codex_home))

    write_config(
        vibe_home / ".vibe-submit" / "config.toml",
        {
            "server_url": "https://submit.example.com",
            "student_no": "2026001",
            "submit_token": "e2e-secret-token",
        },
    )

    return project


def _make_mock_transport():
    """Return a MockTransport, request log and mutable server state."""
    state = {"submission_count": 0}
    log: list[dict] = []

    def handler(request: httpx.Request):
        log.append(
            {
                "method": request.method,
                "path": str(request.url.path),
                "headers": dict(request.headers),
                "body": request.content,
            }
        )

        if request.method == "GET" and request.url.path.endswith("/meta"):
            return httpx.Response(
                200,
                json={
                    "assignment_code": "HW01",
                    "accepts": True,
                    "opens_at": "2026-07-18T00:00:00Z",
                    "deadline": "2026-08-01T00:00:00Z",
                    "min_client_version": "0.1.0",
                    "supported": ["1"],
                },
            )

        if request.method == "POST" and request.url.path.endswith("/submissions"):
            body = request.content
            force = (
                b'name="force"' in body
                and b"\r\n\r\ntrue" in body
            )
            if force or state["submission_count"] == 0:
                state["submission_count"] += 1
                return httpx.Response(
                    201,
                    json={
                        "submission_id": 1,
                        "attempt_no": state["submission_count"],
                    },
                )
            return httpx.Response(
                409,
                json={
                    "error": {
                        "code": "ALREADY_SUBMITTED",
                        "message": "already submitted",
                    }
                },
            )

        if request.method == "GET" and request.url.path.endswith("/submissions/status"):
            return httpx.Response(200, json={"status": "queued", "position": 1})

        return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})

    return httpx.MockTransport(handler), log, state


def _run_cli(args):
    """Run CLI main and return captured exit code and output streams."""
    captured = {"code": None, "stdout": "", "stderr": ""}

    def fake_exit(code=0):
        captured["code"] = code
        raise SystemExit(code)

    original_exit = sys.exit
    sys.exit = fake_exit

    stdout = io.StringIO()
    stderr = io.StringIO()
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    sys.stdout = stdout
    sys.stderr = stderr

    try:
        cli.main([str(a) for a in args])
    except SystemExit as exc:
        captured["code"] = exc.code
    finally:
        sys.exit = original_exit
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    captured["stdout"] = stdout.getvalue()
    captured["stderr"] = stderr.getvalue()
    return captured


def _assert_post_body(body: bytes) -> None:
    assert b'name="manifest"' in body
    assert b'name="file"' in body
    assert b'name="force"' in body


def test_cli_submit_e2e_success_then_conflict_then_force_then_status(
    monkeypatch, setup_env
):
    project = setup_env
    transport, log, state = _make_mock_transport()

    monkeypatch.setattr(
        cli, "get_meta", lambda cfg, code: api_module.get_meta(cfg, code, transport=transport)
    )
    def patched_upload(cfg, zip_path, manifest, force=False):
        return api_module.upload(cfg, zip_path, manifest, force, transport=transport)

    monkeypatch.setattr(cli, "upload", patched_upload)

    # 1) First submission succeeds.
    result = _run_cli(["submit", "--code", "HW01", "--project", str(project), "--yes"])
    assert result["code"] == 0
    assert "Submitted successfully" in result["stdout"]
    assert "attempt_no=1" in result["stdout"]

    # 2) Second submission without --force hits 409.
    result = _run_cli(["submit", "--code", "HW01", "--project", str(project), "--yes"])
    assert result["code"] == 3
    assert "--force" in result["stderr"]

    # 3) Third submission with --force succeeds on attempt 2.
    result = _run_cli(
        ["submit", "--code", "HW01", "--project", str(project), "--yes", "--force"]
    )
    assert result["code"] == 0
    assert "attempt_no=2" in result["stdout"]

    # 4) Status endpoint returns queued.
    status = api_module.get_status(
        api_module.Config(
            server_url="https://submit.example.com",
            student_no="2026001",
            submit_token="e2e-secret-token",
            source="global",
        ),
        "HW01",
        transport=transport,
    )
    assert status["status"] == "queued"

    posts = [r for r in log if r["method"] == "POST"]
    assert len(posts) == 3
    for post in posts:
        assert post["headers"].get("authorization", "").startswith("Bearer ")
        _assert_post_body(post["body"])

    assert state["submission_count"] == 2


def test_mcp_submit_e2e_preview_confirm_and_reject(
    monkeypatch, setup_env
):
    project = setup_env
    transport, log, state = _make_mock_transport()

    monkeypatch.setattr(
        "vibe_submit.preview.get_meta",
        lambda cfg, code: api_module.get_meta(cfg, code, transport=transport),
    )
    monkeypatch.setattr(
        "vibe_submit.mcp_server.get_meta",
        lambda cfg, code: api_module.get_meta(cfg, code, transport=transport),
    )
    monkeypatch.setattr(
        "vibe_submit.mcp_server.upload",
        lambda cfg, zip_path, manifest, force=False: api_module.upload(
            cfg, zip_path, manifest, force, transport=transport
        ),
    )
    monkeypatch.setattr(
        "vibe_submit.mcp_server.get_status",
        lambda cfg, code: api_module.get_status(cfg, code, transport=transport),
    )

    # 1) Fetch assignment metadata.
    meta_result = get_assignment_meta("HW01")
    assert meta_result["ok"] is True
    assert meta_result["meta"]["accepts"] is True

    # 2) Create a preview.
    preview_result = preview_submission("HW01", str(project))
    assert preview_result["ok"] is True
    preview = preview_result["preview"]
    preview_id = preview["preview_id"]
    assert preview["files"] == 1
    assert preview["screenshots"] == 1
    assert len(preview["sessions"]) == 2
    assert preview["fingerprint"]

    # 3) Rejection when not confirmed.
    reject = submit_homework(preview_id, confirmed=False)
    assert reject["ok"] is False
    assert reject["error"]["code"] == "CONFIRMATION_REQUIRED"

    # 4) Confirmed submission succeeds.
    submit = submit_homework(preview_id, confirmed=True)
    assert submit["ok"] is True
    assert submit["submission"]["attempt_no"] == 1

    # 5) Status query.
    status = get_submission_status("HW01")
    assert status["ok"] is True
    assert status["status"]["status"] == "queued"

    posts = [r for r in log if r["method"] == "POST"]
    assert len(posts) == 1
    post = posts[0]
    assert post["headers"].get("authorization", "").startswith("Bearer ")
    _assert_post_body(post["body"])
    assert state["submission_count"] == 1

