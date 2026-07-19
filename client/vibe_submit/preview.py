"""Preview creation and persistence for MCP submissions."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .api import get_meta
from .collect import collect_project
from .config import Config, _config_dir
from .package import build_package
from .sessions import find_sessions, session_index

PREVIEW_LIFETIME = timedelta(hours=1)


def _codex_home() -> Path:
    home = os.environ.get("VIBE_CODEX_HOME")
    if home:
        return Path(home)
    return Path.home() / ".codex"


class PreviewError(Exception):
    """Raised when a preview cannot be loaded or has expired."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class PreviewRecord:
    preview_id: str
    project_root: str
    fingerprint: str
    created_at: datetime
    expires_at: datetime
    zip_path: Path
    manifest: dict[str, Any]
    sessions: list[dict]
    files: int
    screenshots: int
    bytes: int
    skipped: list[str]


def resolve_project_root(path: str | Path | None) -> str:
    """Return the canonical absolute resolved project root path."""
    if path is None:
        path = "."
    return str(Path(path).resolve().absolute())


def _previews_dir() -> Path:
    return _config_dir() / "previews"


def _image_extensions() -> set[str]:
    return {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _is_screenshot(entry) -> bool:
    relpath = getattr(entry, "relpath", "")
    return (
        relpath.startswith("screenshots/")
        and Path(relpath).suffix.lower() in _image_extensions()
    )


def _partition_files(files: list) -> tuple[list, list]:
    code_files = []
    screenshots = []
    for entry in files:
        if _is_screenshot(entry):
            screenshots.append(entry)
        else:
            code_files.append(entry)
    return code_files, screenshots


def _compute_fingerprint(project_root: str, stats: dict[str, Any]) -> str:
    canonical = Path(project_root).resolve().as_posix()
    data = json.dumps(
        {"project_root": canonical, "stats": stats},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:12]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def create_preview(
    cfg: Config,
    assignment_code: str,
    project_root: str | Path,
) -> dict[str, Any]:
    """Build a submission preview, persist it, and return a summary dict.

    The preview is stored under ``~/.vibe-submit/previews/{preview_id}/`` with
    ``meta.json`` and the zip package.  The preview record binds the canonical
    project root, a content fingerprint, and a one-hour expiry.
    """
    root_str = resolve_project_root(project_root)
    root = Path(root_str)

    meta = get_meta(cfg, assignment_code)
    opens_at = meta.get("opens_at")
    since = _parse_iso(opens_at) if opens_at else None

    sessions = find_sessions(_codex_home(), root, since)
    files, skipped = collect_project(root)
    code_files, screenshots = _partition_files(files)

    package_meta = {
        "assignment_code": assignment_code,
        "student_no": cfg.student_no,
        "client_version": meta.get("client_version", "0.1.0"),
    }

    preview_id = secrets.token_urlsafe(12)
    preview_dir = _previews_dir() / preview_id
    preview_dir.mkdir(parents=True, exist_ok=True)

    zip_path, manifest, stats = build_package(
        root,
        sessions,
        code_files,
        screenshots,
        package_meta,
        preview_dir,
    )

    fingerprint = _compute_fingerprint(root_str, stats)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + PREVIEW_LIFETIME

    record_meta = {
        "preview_id": preview_id,
        "project_root": root_str,
        "fingerprint": fingerprint,
        "created_at": _iso_utc(created_at),
        "expires_at": _iso_utc(expires_at),
        "zip_path": str(zip_path),
    }
    (preview_dir / "meta.json").write_text(
        json.dumps(record_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "preview": {
            "preview_id": preview_id,
            "sessions": [session_index(s.path) for s in sessions],
            "files": len(code_files),
            "screenshots": len(screenshots),
            "bytes": stats["bytes"],
            "skipped": skipped,
            "fingerprint": fingerprint,
        },
    }


def load_preview(preview_id: str) -> PreviewRecord:
    """Load a preview record from disk, rejecting missing or expired previews."""
    preview_dir = _previews_dir() / preview_id
    if not preview_dir.exists():
        raise PreviewError("PREVIEW_INVALID", f"preview not found: {preview_id}")

    meta_path = preview_dir / "meta.json"
    if not meta_path.exists():
        raise PreviewError("PREVIEW_INVALID", f"preview meta missing: {preview_id}")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PreviewError("PREVIEW_INVALID", f"preview meta unreadable: {exc}") from exc

    expires_at = _parse_iso(meta["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise PreviewError("PREVIEW_INVALID", f"preview expired: {preview_id}")

    zip_path = Path(meta["zip_path"])
    if not zip_path.exists():
        zip_path = preview_dir / zip_path.name

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except Exception as exc:
        raise PreviewError("PREVIEW_INVALID", f"preview package unreadable: {exc}") from exc

    return PreviewRecord(
        preview_id=preview_id,
        project_root=meta["project_root"],
        fingerprint=meta["fingerprint"],
        created_at=_parse_iso(meta["created_at"]),
        expires_at=expires_at,
        zip_path=zip_path,
        manifest=manifest,
        sessions=[],
        files=0,
        screenshots=0,
        bytes=0,
        skipped=[],
    )


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
