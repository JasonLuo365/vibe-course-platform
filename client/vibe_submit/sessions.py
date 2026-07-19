"""Session discovery and indexing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SessionInfo:
    path: Path
    session_id: str
    cwd: str
    started_at: datetime


def _parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, normalising trailing Z to +00:00."""
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso_utc(dt: datetime) -> str:
    """Return a UTC ISO string with Z suffix."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_session_info(path: Path) -> SessionInfo | None:
    """Read the first line of a rollout jsonl and return session metadata.

    Returns ``None`` if the file has no ``session_meta`` line, the JSON is
    malformed, or required fields are missing.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if data.get("type") != "session_meta":
                    return None
                payload = data.get("payload", {})
                session_id = payload.get("id")
                timestamp = payload.get("timestamp")
                cwd = payload.get("cwd")
                if not session_id or not timestamp or cwd is None:
                    return None
                try:
                    started_at = _parse_iso(timestamp)
                except Exception:
                    return None
                return SessionInfo(
                    path=Path(path),
                    session_id=str(session_id),
                    cwd=str(cwd),
                    started_at=started_at,
                )
    except Exception:
        return None
    return None


def find_sessions(
    codex_home: Path, project_root: Path, since: datetime | None = None
) -> list[SessionInfo]:
    """Discover rollout sessions matching ``project_root`` and optional time filter."""
    root_resolved = Path(project_root).resolve()
    sessions: list[SessionInfo] = []
    search_root = Path(codex_home) / "sessions"
    if search_root.exists():
        for path in search_root.rglob("*.jsonl"):
            info = read_session_info(path)
            if info is None:
                continue
            try:
                cwd_resolved = Path(info.cwd).resolve()
            except Exception:
                continue
            if cwd_resolved != root_resolved:
                continue
            if since is not None:
                since_aware = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
                if info.started_at < since_aware:
                    continue
            sessions.append(info)
    sessions.sort(key=lambda s: s.started_at)
    return sessions


# Message line types known to carry a user/assistant role.
_MESSAGE_TYPES = {"response_item", "event_msg", "message", "chat_message"}


def session_index(path: Path) -> dict:
    """Return a summary dict for a session file.

    The dict contains ``session_id``, ``started_at`` (ISO UTC), ``ended_at``
    (ISO UTC, taken from the latest timestamp seen), and ``message_count``
    (lines whose ``type`` is a known message type and whose payload role is
    ``user`` or ``assistant``).  Malformed lines are skipped.
    """
    info = read_session_info(path)
    if info is None:
        return {}

    ended_at = info.started_at
    message_count = 0

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
                ts = payload.get("timestamp") or data.get("timestamp")
                if ts:
                    try:
                        line_dt = _parse_iso(ts)
                        if line_dt > ended_at:
                            ended_at = line_dt
                    except Exception:
                        pass

                if data.get("type") in _MESSAGE_TYPES:
                    role = payload.get("role") if isinstance(payload, dict) else None
                    if role in ("user", "assistant"):
                        message_count += 1
    except Exception:
        pass

    return {
        "session_id": info.session_id,
        "started_at": _iso_utc(info.started_at),
        "ended_at": _iso_utc(ended_at),
        "message_count": message_count,
    }

