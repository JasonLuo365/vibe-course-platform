import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .parser import RolloutTimeline
from .prompts import (
    GROUP_SCHEMA,
    INDIVIDUAL_SCHEMA,
    PROMPT_VERSION,
    group_messages,
    individual_messages,
)


class DimensionScore(BaseModel):
    name: str
    weight: int
    score: int
    rationale: str


class Evidence(BaseModel):
    session_id: str
    turn: int
    quote: str = Field(..., max_length=200)


class EvalOut(BaseModel):
    grade: Literal["A", "B", "C", "D", "E"]
    dimension_scores: list[DimensionScore]
    evidence: list[Evidence]
    rationale: str
    feedback: list[str]
    flags: list[str]


class EvalError(Exception):
    """Raised when evaluation fails after all retries."""


# Common entry / high-value file names used to prioritize code digest snippets.
_ENTRY_FILES = {
    "main.py",
    "app.py",
    "manage.py",
    "index.py",
    "server.py",
    "__init__.py",
    "readme.md",
    "requirements.txt",
}


def _format_timeline(timeline: RolloutTimeline) -> str:
    lines = [f"会话: {timeline.session_id} ({len(timeline.turns)} turns)"]
    for i, turn in enumerate(timeline.turns):
        ts = turn.ts or ""
        preview = turn.text.replace("\n", " ")
        if len(preview) > 500:
            preview = preview[:500] + "..."
        lines.append(f"  [{i}] {turn.kind} {ts}\n    {preview}")
    return "\n".join(lines)


def build_evidence_pack(
    timelines: list[RolloutTimeline],
    code_digest: str,
    metrics: dict,
    max_chars: int = 120000,
) -> str:
    parts = [
        "=== 指标 ===\n" + json.dumps(metrics, ensure_ascii=False, indent=2),
        "=== 代码节选 ===\n" + code_digest,
        "=== Rollout 记录 ===",
    ]
    for timeline in timelines:
        parts.append(_format_timeline(timeline))

    full = "\n\n".join(parts)
    if len(full) <= max_chars:
        return full

    note = f"\n\n...【内容已截断，中部省略；原始长度 {len(full)}】...\n\n"
    if len(note) >= max_chars:
        return full[:max_chars]

    available = max_chars - len(note)
    head_len = available // 2
    tail_len = available - head_len
    return full[:head_len] + note + full[-tail_len:]


def code_digest(extract_dir: str, max_files: int = 20, max_chars: int = 8000) -> str:
    root = Path(extract_dir)
    if not root.exists():
        return f"目录不存在：{extract_dir}"

    tree_lines: list[str] = []
    candidates: list[tuple[Path, int]] = []

    for path in root.rglob("*"):
        rel = path.relative_to(root)
        depth = len(rel.parts)
        if depth > 3:
            continue
        indent = "  " * (depth - 1)
        if path.is_dir():
            tree_lines.append(f"{indent}{rel.name}/")
        elif path.is_file():
            tree_lines.append(f"{indent}{rel.name}")
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            candidates.append((rel, size))

    tree = "=== 目录树（限深 3）===\n" + "\n".join(tree_lines)

    def priority(item: tuple[Path, int]) -> tuple[int, int]:
        rel, size = item
        name = rel.name.lower()
        if name in _ENTRY_FILES:
            return (3, size)
        if name.endswith(".py"):
            return (2, size)
        return (1, size)

    candidates.sort(key=priority, reverse=True)
    selected = candidates[:max_files]

    parts: list[str] = [tree]
    budget = max_chars - len(tree) - 20

    for rel, _ in selected:
        if budget <= 0:
            break
        abs_path = root / rel
        header = f"\n\n--- {rel.as_posix()} ---\n"
        try:
            text = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            text = ""

        room = budget - len(header) - len("\n...[省略]...")
        if room <= 0:
            break
        chunk = text[:room]
        if len(text) > len(chunk):
            chunk += "\n...[省略]..."
        parts.append(header + chunk)
        budget -= len(header) + len(chunk)

    digest = "".join(parts)
    if len(digest) > max_chars:
        note = "\n...[目录/节选截断]..."
        digest = digest[: max_chars - len(note)] + note
    return digest


def _validate_evidence(
    evidence: list[Evidence], timelines: list[RolloutTimeline]
) -> None:
    timeline_by_id = {t.session_id: t for t in timelines}
    for ev in evidence:
        timeline = timeline_by_id.get(ev.session_id)
        if timeline is None:
            raise EvalError(
                f"证据回查失败：session_id '{ev.session_id}' 不存在"
            )
        if ev.turn < 0 or ev.turn >= len(timeline.turns):
            raise EvalError(
                f"证据回查失败：turn {ev.turn} 超出会话 '{ev.session_id}' 的范围 "
                f"(共 {len(timeline.turns)} turns)"
            )
        if len(ev.quote) > 200:
            raise EvalError(
                f"证据回查失败：quote 长度 {len(ev.quote)} 超过 200 字"
            )


def _error_note(exc: Exception) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return f"输出不是合法 JSON：{exc}"
    if isinstance(exc, ValidationError):
        return f"输出字段校验失败：{exc.errors(include_url=False)}"
    return str(exc)


def _append_error_note(
    messages: list[dict[str, str]], error_note: str
) -> list[dict[str, str]]:
    new_messages = [dict(m) for m in messages]
    for msg in reversed(new_messages):
        if msg.get("role") == "user":
            msg["content"] = (
                msg.get("content", "") + "\n\n[上次输出错误，请修正后重新输出]\n" + error_note
            )
            return new_messages
    new_messages.append({"role": "user", "content": error_note})
    return new_messages


def _clamp_quotes(data: dict) -> None:
    """LLM 输出的超长 quote 截断至 200 字符并写入 flags（审计透明）。

    提示词层面的硬性约束已要求 ≤200 字符，但真实模型仍会偶发超长；
    证据定位依赖 session_id+turn，截断不损害可追溯性。
    """
    clamped = 0
    for ev in data.get("evidence") or []:
        q = ev.get("quote")
        if isinstance(q, str) and len(q) > 200:
            ev["quote"] = q[:197] + "..."
            clamped += 1
    if clamped:
        flags = data.setdefault("flags", [])
        flags.append(f"系统提示：{clamped} 条证据 quote 超长，已截断至 200 字符")


def _evaluate_once(
    messages: list[dict[str, str]],
    schema: dict,
    provider,
    timelines: list[RolloutTimeline] | None = None,
) -> EvalOut:
    raw = provider.complete(messages, json_schema=schema, max_tokens=4096)
    data = json.loads(raw)
    _clamp_quotes(data)
    eval_out = EvalOut.model_validate(data)
    if timelines is not None:
        _validate_evidence(eval_out.evidence, timelines)
    else:
        for ev in eval_out.evidence:
            if len(ev.quote) > 200:
                raise EvalError(f"quote 长度 {len(ev.quote)} 超过 200 字")
    return eval_out


def evaluate_individual(
    timelines: list[RolloutTimeline],
    code_digest: str,
    metrics: dict,
    rubric: list[dict],
    provider,
) -> dict:
    evidence_pack = build_evidence_pack(timelines, code_digest, metrics)
    messages = individual_messages(evidence_pack, metrics, rubric)

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            eval_out = _evaluate_once(
                messages, INDIVIDUAL_SCHEMA, provider, timelines=timelines
            )
            return eval_out.model_dump() | {"prompt_version": PROMPT_VERSION}
        except (json.JSONDecodeError, ValidationError, EvalError) as exc:
            last_error = exc
            messages = _append_error_note(messages, _error_note(exc))

    raise EvalError(f"个人评估失败，已重试 2 次：{last_error}")


def evaluate_group(
    member_evals: list[dict],
    metrics: dict,
    rubric: list[dict],
    provider,
) -> dict:
    messages = group_messages(member_evals, metrics, rubric)

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            eval_out = _evaluate_once(messages, GROUP_SCHEMA, provider)
            return eval_out.model_dump() | {"prompt_version": PROMPT_VERSION}
        except (json.JSONDecodeError, ValidationError, EvalError) as exc:
            last_error = exc
            messages = _append_error_note(messages, _error_note(exc))

    raise EvalError(f"小组评估失败，已重试 2 次：{last_error}")
