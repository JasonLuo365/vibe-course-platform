"""Outbox persistence for failed submissions."""

from __future__ import annotations

import json
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, _config_dir, validate_server_url
from .errors import OutboxError


def _outbox_dir() -> Path:
    return _config_dir() / "outbox"


def _entry_path(outbox_id: str) -> Path:
    """Return an outbox path while rejecting path traversal attempts."""
    if not outbox_id or Path(outbox_id).name != outbox_id:
        raise OutboxError("invalid outbox id")
    return _outbox_dir() / outbox_id


def save_outbox(zip_path: Path, manifest: dict, cfg: Config) -> str:
    """Persist a submission zip and its manifest to the outbox.

    Returns the generated ``outbox_id``.
    """
    outbox_id = secrets.token_urlsafe(8)
    outbox_path = _outbox_dir() / outbox_id
    outbox_path.mkdir(parents=True, exist_ok=True)

    dest_zip = outbox_path / Path(zip_path).name
    shutil.copy2(zip_path, dest_zip)

    meta = {
        "outbox_id": outbox_id,
        "assignment_code": manifest.get("assignment_code"),
        "student_no": cfg.student_no,
        "server_url": cfg.server_url,
        "saved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "zip_name": dest_zip.name,
        "manifest": manifest,
    }
    (outbox_path / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return outbox_id


def list_outbox() -> list[dict]:
    """Return a list of outbox entries with id, assignment_code, size, saved_at."""
    base = _outbox_dir()
    if not base.exists():
        return []

    entries: list[dict] = []
    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        meta_path = path / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        zip_path = path / meta.get("zip_name", "")
        size = zip_path.stat().st_size if zip_path.exists() else 0
        entries.append(
            {
                "id": path.name,
                "assignment_code": meta.get("assignment_code"),
                "size": size,
                "saved_at": meta.get("saved_at"),
            }
        )
    return entries


def get_outbox(outbox_id: str) -> tuple[Path, dict]:
    """Return the persisted zip path and manifest for an outbox entry."""
    path = _entry_path(outbox_id)
    if not path.exists():
        raise OutboxError(f"outbox entry not found: {outbox_id}")

    meta_path = path / "meta.json"
    if not meta_path.exists():
        raise OutboxError(f"outbox meta missing: {outbox_id}")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OutboxError(f"outbox meta unreadable: {outbox_id}") from exc

    zip_name = meta.get("zip_name")
    if not zip_name:
        raise OutboxError(f"outbox zip name missing: {outbox_id}")

    zip_path = path / zip_name
    if not zip_path.exists():
        raise OutboxError(f"outbox zip missing: {outbox_id}")

    manifest = meta.get("manifest", {})
    return zip_path, manifest


def get_outbox_config(outbox_id: str) -> Config:
    """Reconstruct a Config object from an outbox entry (no submit_token)."""
    path = _entry_path(outbox_id)
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    return Config(
        server_url=meta.get("server_url", ""),
        student_no=meta.get("student_no", ""),
        submit_token="",
        source="outbox",
    )


def retry_config(outbox_id: str, active_config: Config) -> Config:
    """Use the original destination with the current student's credential."""
    saved = get_outbox_config(outbox_id)
    if saved.student_no and saved.student_no != active_config.student_no:
        raise OutboxError("outbox entry belongs to a different student")
    return Config(
        server_url=validate_server_url(saved.server_url or active_config.server_url),
        student_no=active_config.student_no,
        submit_token=active_config.submit_token,
        source="outbox",
    )


def remove_outbox(outbox_id: str) -> None:
    """Remove an entry only after the server has accepted its package."""
    path = _entry_path(outbox_id)
    if not path.is_dir():
        raise OutboxError(f"outbox entry not found: {outbox_id}")
    shutil.rmtree(path)

