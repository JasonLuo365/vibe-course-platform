import json
import pathlib
import re
from dataclasses import dataclass

MAX_TURN_CHARS = 2000


@dataclass(frozen=True, slots=True)
class Turn:
    kind: str
    text: str
    ts: str | None
    from_history_envelope: bool = False


@dataclass(frozen=True, slots=True)
class RolloutTimeline:
    session_id: str
    path: str
    turns: list[Turn]


_CODEX_HISTORY_ENVELOPE = re.compile(
    r"the following is the codex agent history (?:whose request action you are assessing|added since your last approval assessment)",
    re.IGNORECASE,
)
_CODEX_HISTORY_ENTRY = re.compile(
    r"^\[(?P<index>\d+)\]\s+(?P<role>user|assistant|developer|system|tool[^:]*):\s*",
    re.IGNORECASE | re.MULTILINE,
)
_HIDDEN_PROMPT_MARKERS = (
    "<recommended_plugins>",
    "<permissions instructions>",
    "<environment_context>",
    "<developer",
    "the following is the codex agent history whose request action you are assessing",
    "the following is the codex agent history added since your last approval assessment",
    "continue the same review based on the latest transcript",
)


def is_displayable_human_prompt(text: str) -> bool:
    """Return whether a prompt is safe and useful to show to a teacher."""
    cleaned = " ".join(text.split())
    if len(cleaned) < 2 or len(cleaned) > 6000:
        return False
    lowered = cleaned.lower()
    if any(marker in lowered for marker in _HIDDEN_PROMPT_MARKERS):
        return False
    replacement_ratio = cleaned.count("\ufffd") / max(len(cleaned), 1)
    control_ratio = sum(
        ord(char) < 32 and char not in "\n\t" for char in cleaned
    ) / max(len(cleaned), 1)
    return replacement_ratio < 0.03 and control_ratio < 0.03


def extract_history_envelope_user_prompts(text: str) -> list[tuple[str, str]] | None:
    """Extract labelled human requests from a Codex history-envelope record.

    ``None`` means this is an ordinary user turn and should be handled as-is.
    An empty list means a recognised envelope contained no safe human request;
    callers must not expose the enclosing synthetic context as a prompt.
    """
    if not _CODEX_HISTORY_ENVELOPE.search(text):
        return None

    entries = list(_CODEX_HISTORY_ENTRY.finditer(text))
    prompts: list[tuple[str, str]] = []
    for pos, entry in enumerate(entries):
        if entry.group("role").lower() != "user":
            continue
        end = entries[pos + 1].start() if pos + 1 < len(entries) else len(text)
        prompt = text[entry.end() : end].strip()
        if is_displayable_human_prompt(prompt):
            prompts.append((entry.group("index"), prompt))
    return prompts


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
    seen_history_entries: set[tuple[str, str]] = set()
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

        # Codex may resume an approval/assessment interaction by putting the
        # complete earlier transcript in a synthetic ``user`` record. Expand
        # this before truncation, retain only labelled human requests, and
        # prevent repeated history envelopes from duplicating them.
        if kind == "user":
            history_prompts = extract_history_envelope_user_prompts(text)
            if history_prompts is not None:
                for index, prompt in history_prompts:
                    key = (index, prompt)
                    if key in seen_history_entries:
                        continue
                    seen_history_entries.add(key)
                    turns.append(Turn(
                        kind="user",
                        text=prompt[:MAX_TURN_CHARS],
                        ts=ts,
                        from_history_envelope=True,
                    ))
                continue

        if len(text) > MAX_TURN_CHARS:
            text = text[:MAX_TURN_CHARS]

        turns.append(Turn(kind=kind, text=text, ts=ts))

    return RolloutTimeline(session_id=session_id, path=path, turns=turns)
