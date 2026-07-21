import json
import pathlib
from dataclasses import dataclass

MAX_TURN_CHARS = 2000


@dataclass(frozen=True, slots=True)
class Turn:
    kind: str
    text: str
    ts: str | None


@dataclass(frozen=True, slots=True)
class RolloutTimeline:
    session_id: str
    path: str
    turns: list[Turn]


def _extract_text(payload: dict) -> str:
    """Best-effort text extraction from content/input/arguments/output fields."""
    # 1. content list of dicts
    content = payload.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return "\n".join(parts)

    # 2. plain string content
    if isinstance(content, str):
        return content

    # 3. common single-string fields
    for key in ("arguments", "input", "output", "command", "result", "text"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                pass

    # 4. fallback: flatten the whole payload
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def _extract_ts(payload: dict) -> str | None:
    for key in ("timestamp", "ts", "created_at"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def _classify_kind(payload: dict) -> str:
    role = payload.get("role")
    if role == "user":
        return "user"
    if role == "assistant":
        return "assistant"

    payload_type = payload.get("type")
    if isinstance(payload_type, str):
        if payload_type in {
            "function_call",
            "function_call_output",
            "local_shell_call",
            "custom_tool_call",
        }:
            return "tool"
        # Some rollouts use generic "tool_call" / "tool_output" as well.
        if "tool" in payload_type:
            return "tool"

    return "other"


def parse_rollout(path: str) -> RolloutTimeline:
    p = pathlib.Path(path)
    session_id = p.stem
    turns: list[Turn] = []
    skipped = 0

    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        # Fault tolerance: if file cannot be read, return empty timeline.
        return RolloutTimeline(session_id=session_id, path=path, turns=turns)

    for idx, raw in enumerate(lines):
        raw = raw.strip()
        if not raw:
            continue

        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            skipped += 1
            continue

        if not isinstance(record, dict):
            skipped += 1
            continue

        payload = record.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        record_type = record.get("type")

        if idx == 0 and record_type == "session_meta":
            meta_payload = payload
            if "id" in meta_payload:
                session_id = str(meta_payload["id"]) or session_id
            continue

        kind = _classify_kind(payload)
        text = _extract_text(payload)
        ts = _extract_ts(payload)

        if len(text) > MAX_TURN_CHARS:
            text = text[:MAX_TURN_CHARS]

        turns.append(Turn(kind=kind, text=text, ts=ts))

    return RolloutTimeline(session_id=session_id, path=path, turns=turns)
