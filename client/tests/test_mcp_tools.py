"""Tests for vibe_submit.mcp_server tool implementations."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from vibe_submit.api import ApiError
from vibe_submit.config import Config, ConfigError
from vibe_submit.mcp_server import (
    get_assignment_meta_impl,
    get_submission_status_impl,
    preview_submission_impl,
    retry_submission_impl,
    submit_homework_impl,
)
from vibe_submit.preview import PreviewError, load_preview


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    return Config(
        server_url="https://example.com",
        student_no="2026001",
        submit_token="secret-token",
        source="global",
    )


@pytest.fixture
def make_project(tmp_path):
    def _make(files=None, sessions=None):
        root = tmp_path / "project"
        root.mkdir(parents=True, exist_ok=True)
        if files:
            for relpath, content in files.items():
                p = root / relpath
                p.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    p.write_bytes(content)
                else:
                    p.write_text(content, encoding="utf-8")
        if sessions:
            codex = tmp_path / "codex" / "sessions"
            codex.mkdir(parents=True, exist_ok=True)
            for name, spec in sessions.items():
                path = codex / name
                cwd = spec.get("cwd", str(root))
                meta = {
                    "type": "session_meta",
                    "payload": {
                        "id": spec.get("id", "s1"),
                        "timestamp": spec.get("timestamp", "2026-07-19T10:00:00Z"),
                        "cwd": cwd,
                    },
                }
                lines = [json.dumps(meta)]
                for line in spec.get("lines", []):
                    lines.append(
                        json.dumps(line) if isinstance(line, dict) else str(line)
                    )
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return root

    return _make


def _assignment_meta(opens_at="2026-07-19T00:00:00Z", accepts=True):
    return {"assignment_code": "HW01", "accepts": accepts, "opens_at": opens_at}


def test_preview_submission_creates_preview_and_returns_summary(
    cfg, make_project, monkeypatch, tmp_path
):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(
        files={
            "main.py": "print('hello')",
            "screenshots/img.png": b"png",
            ".env": "secret",
        },
        sessions={
            "session.jsonl": {
                "id": "s1",
                "timestamp": "2026-07-19T10:00:00Z",
                "lines": [
                    {
                        "type": "response_item",
                        "payload": {"role": "user", "timestamp": "2026-07-19T10:01:00Z"},
                    }
                ],
            }
        },
    )

    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        result = preview_submission_impl(cfg, "HW01", str(root))

    assert result["ok"] is True
    data = result["preview"]
    preview_id = data["preview_id"]
    assert len(preview_id) > 0
    assert data["files"] == 1
    assert data["screenshots"] == 1
    assert data["bytes"] > 0
    assert data["skipped"] == [".env"]
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == "s1"
    assert data["fingerprint"]

    preview_dir = tmp_path / ".vibe-submit" / "previews" / preview_id
    assert preview_dir.exists()
    assert (preview_dir / "meta.json").exists()
    assert list(preview_dir.glob("*.zip"))

    meta = json.loads((preview_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["project_root"] == str(root.resolve())
    assert meta["fingerprint"] == data["fingerprint"]
    assert meta["expires_at"] > meta["created_at"]


def test_submit_homework_rejects_missing_preview(cfg):
    result = submit_homework_impl("no-such-id", confirmed=True, cfg=cfg)
    assert result["ok"] is False
    assert result["error"]["code"] == "PREVIEW_INVALID"


def test_submit_homework_rejects_without_confirmation(cfg, make_project, monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(files={"main.py": "x"})
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    result = submit_homework_impl(preview_id, confirmed=False, cfg=cfg)
    assert result["ok"] is False
    assert result["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_submit_homework_rejects_project_root_mismatch(
    cfg, make_project, monkeypatch, tmp_path
):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(files={"main.py": "x"})
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    result = submit_homework_impl(
        preview_id,
        confirmed=True,
        project_root=str(tmp_path / "other"),
        cfg=cfg,
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "PREVIEW_INVALID"


def test_submit_homework_success_path(cfg, make_project, monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(files={"main.py": "x"})
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    with patch(
        "vibe_submit.mcp_server.upload",
        return_value={"submission_id": "sub-1", "attempt_no": 1},
    ) as mock_upload:
        result = submit_homework_impl(preview_id, confirmed=True, cfg=cfg)

    assert result["ok"] is True
    assert result["submission"]["submission_id"] == "sub-1"
    mock_upload.assert_called_once()


def test_submit_homework_409_requires_force_confirmed(
    cfg, make_project, monkeypatch, tmp_path
):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(files={"main.py": "x"})
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    conflict = ApiError(409, "DUPLICATE_SUBMISSION", "already submitted", None)
    with patch("vibe_submit.mcp_server.upload", side_effect=conflict) as mock_upload:
        result = submit_homework_impl(preview_id, confirmed=True, cfg=cfg)

    assert result["ok"] is False
    assert result["error"]["code"] == "FORCE_REQUIRED"
    assert "already submitted" in result["error"]["message"]
    mock_upload.assert_called_once_with(cfg, ANY, ANY, force=False)


def test_submit_homework_force_confirmed_retries_with_force(
    cfg, make_project, monkeypatch, tmp_path
):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(files={"main.py": "x"})
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    conflict = ApiError(409, "DUPLICATE_SUBMISSION", "already submitted", None)
    with patch(
        "vibe_submit.mcp_server.upload",
        side_effect=[conflict, {"submission_id": "sub-2", "attempt_no": 2}],
    ) as mock_upload:
        result = submit_homework_impl(
            preview_id, confirmed=True, force_confirmed=True, cfg=cfg
        )

    assert result["ok"] is True
    assert result["submission"]["submission_id"] == "sub-2"
    assert mock_upload.call_count == 2
    calls = mock_upload.call_args_list
    assert calls[0].kwargs.get("force") is False
    assert calls[1].kwargs.get("force") is True


def test_submit_homework_maps_other_api_errors(cfg, make_project, monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(files={"main.py": "x"})
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    err = ApiError(401, "UNAUTHORIZED", "bad token", {"error": {"code": "UNAUTHORIZED"}})
    with patch("vibe_submit.mcp_server.upload", side_effect=err):
        result = submit_homework_impl(preview_id, confirmed=True, cfg=cfg)

    assert result["ok"] is False
    assert result["error"]["code"] == "UNAUTHORIZED"
    assert "bad token" in result["error"]["message"]


def test_retry_submission_no_args_returns_read_only_list(cfg, make_project, tmp_path):
    # Save an outbox entry first.
    zip_path = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("dummy.txt", b"data")
    manifest = {
        "format_version": "1",
        "assignment_code": "HW01",
        "student_no": "2026001",
        "client_version": "0.1.0",
        "submitted_at": "2026-07-19T10:00:00Z",
        "files": [],
        "stats": {"sessions": 0, "files": 0, "bytes": 0},
    }
    from vibe_submit.outbox import save_outbox

    outbox_id = save_outbox(zip_path, manifest, cfg)

    with patch("vibe_submit.mcp_server.upload") as mock_upload:
        result = retry_submission_impl(cfg)

    assert result["ok"] is True
    assert "outbox" in result
    assert len(result["outbox"]) == 1
    assert result["outbox"][0]["id"] == outbox_id
    mock_upload.assert_not_called()


def test_retry_submission_by_id_uses_stored_server_url_and_current_token(cfg, make_project, tmp_path):
    zip_path = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("dummy.txt", b"data")
    manifest = {
        "format_version": "1",
        "assignment_code": "HW01",
        "student_no": "2026001",
        "client_version": "0.1.0",
        "submitted_at": "2026-07-19T10:00:00Z",
        "files": [],
        "stats": {"sessions": 0, "files": 0, "bytes": 0},
    }
    from vibe_submit.outbox import save_outbox

    outbox_id = save_outbox(zip_path, manifest, cfg)

    # Preserve the original server but use the active credential.
    other_cfg = Config(
        server_url="https://wrong.example.com",
        student_no="2026001",
        submit_token="other-token",
        source="global",
    )

    with patch(
        "vibe_submit.mcp_server.upload",
        return_value={"submission_id": "sub-3", "attempt_no": 1},
    ) as mock_upload:
        result = retry_submission_impl(other_cfg, outbox_id=outbox_id)

    assert result["ok"] is True
    assert result["submission"]["submission_id"] == "sub-3"
    mock_upload.assert_called_once()
    used_cfg = mock_upload.call_args_list[0].args[0]
    assert used_cfg.server_url == "https://example.com"
    assert used_cfg.student_no == "2026001"
    assert used_cfg.submit_token == "other-token"
    assert not (tmp_path / ".vibe-submit" / "outbox" / outbox_id).exists()


def test_retry_submission_rejects_entry_for_a_different_student(cfg, make_project, tmp_path):
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"data")
    manifest = {"assignment_code": "HW01"}
    from vibe_submit.outbox import save_outbox

    outbox_id = save_outbox(zip_path, manifest, cfg)
    other_cfg = Config(
        server_url="https://example.com",
        student_no="2026999",
        submit_token="other-token",
        source="global",
    )
    result = retry_submission_impl(other_cfg, outbox_id=outbox_id)
    assert result["ok"] is False
    assert result["error"]["code"] == "OUTBOX_ERROR"


def test_retry_submission_by_assignment_code_uploads(cfg, make_project, tmp_path):
    zip_path = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("dummy.txt", b"data")
    manifest = {
        "format_version": "1",
        "assignment_code": "HW01",
        "student_no": "2026001",
        "client_version": "0.1.0",
        "submitted_at": "2026-07-19T10:00:00Z",
        "files": [],
        "stats": {"sessions": 0, "files": 0, "bytes": 0},
    }
    from vibe_submit.outbox import save_outbox

    save_outbox(zip_path, manifest, cfg)

    with patch(
        "vibe_submit.mcp_server.upload",
        return_value={"submission_id": "sub-4", "attempt_no": 1},
    ):
        result = retry_submission_impl(cfg, assignment_code="HW01")

    assert result["ok"] is True
    assert result["submission"]["submission_id"] == "sub-4"


def test_submit_homework_network_failure_saves_outbox(cfg, make_project, monkeypatch, tmp_path):
    root = make_project(files={"main.py": "print(1)"})
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    network_error = ApiError(0, "NETWORK", "offline", None)
    with patch("vibe_submit.mcp_server.upload", side_effect=network_error):
        result = submit_homework_impl(preview_id, confirmed=True, cfg=cfg)

    assert result["ok"] is False
    assert result["error"]["code"] == "NETWORK"
    assert result["outbox_id"]


def test_preview_uses_installed_client_version(cfg, make_project, monkeypatch, tmp_path):
    root = make_project(files={"main.py": "print(1)"})
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()), patch(
        "vibe_submit.preview.installed_version", return_value="0.2.3"
    ):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]
    assert load_preview(preview_id).manifest["client_version"] == "0.2.3"


def test_retry_submission_by_assignment_code_ambiguous(cfg, make_project, tmp_path):
    for code in ("HW01", "HW01"):
        zip_path = tmp_path / f"{code}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dummy.txt", b"data")
        manifest = {
            "format_version": "1",
            "assignment_code": code,
            "student_no": "2026001",
            "client_version": "0.1.0",
            "submitted_at": "2026-07-19T10:00:00Z",
            "files": [],
            "stats": {"sessions": 0, "files": 0, "bytes": 0},
        }
        from vibe_submit.outbox import save_outbox

        save_outbox(zip_path, manifest, cfg)

    result = retry_submission_impl(cfg, assignment_code="HW01")
    assert result["ok"] is False
    assert result["error"]["code"] == "AMBIGUOUS_OUTBOX"


def test_retry_submission_by_assignment_code_missing(cfg):
    result = retry_submission_impl(cfg, assignment_code="HW99")
    assert result["ok"] is False
    assert result["error"]["code"] == "OUTBOX_NOT_FOUND"


def test_get_assignment_meta_impl_passthrough(cfg):
    with patch("vibe_submit.mcp_server.get_meta", return_value={"accepts": True}) as mock:
        result = get_assignment_meta_impl(cfg, "HW01")
    assert result["ok"] is True
    assert result["meta"]["accepts"] is True
    mock.assert_called_once_with(cfg, "HW01")


def test_get_submission_status_impl_passthrough(cfg):
    with patch(
        "vibe_submit.mcp_server.get_status", return_value={"status": "graded"}
    ) as mock:
        result = get_submission_status_impl(cfg, "HW01")
    assert result["ok"] is True
    assert result["status"]["status"] == "graded"
    mock.assert_called_once_with(cfg, "HW01")


def test_mcp_tools_return_structured_config_error(monkeypatch):
    from vibe_submit import mcp_server as server

    def boom():
        raise ConfigError("global config not found")

    monkeypatch.setattr(server, "_load_cfg", boom)

    result = server.get_assignment_meta("HW01")
    assert result == {
        "ok": False,
        "error": {"code": "CONFIG_ERROR", "message": "global config not found"},
    }

    result = server.retry_submission(outbox_id="obx-1")
    assert result == {
        "ok": False,
        "error": {"code": "CONFIG_ERROR", "message": "global config not found"},
    }


def test_load_preview_rejects_expired_preview(cfg, make_project, monkeypatch, tmp_path):
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex"))
    root = make_project(files={"main.py": "x"})
    with patch("vibe_submit.preview.get_meta", return_value=_assignment_meta()):
        preview = preview_submission_impl(cfg, "HW01", str(root))
    preview_id = preview["preview"]["preview_id"]

    # Expire the preview by manipulating meta.json.
    preview_dir = tmp_path / ".vibe-submit" / "previews" / preview_id
    meta = json.loads((preview_dir / "meta.json").read_text(encoding="utf-8"))
    meta["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat().replace("+00:00", "Z")
    (preview_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    result = submit_homework_impl(preview_id, confirmed=True, cfg=cfg)
    assert result["ok"] is False
    assert result["error"]["code"] == "PREVIEW_INVALID"


def test_load_preview_raises_on_missing():
    with pytest.raises(PreviewError):
        load_preview("nonexistent-id")

