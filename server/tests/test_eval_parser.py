import json

import pytest

from app.eval.metrics import compute_metrics
from app.eval.parser import RolloutTimeline, Turn, parse_rollout


def _write_jsonl(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


@pytest.fixture
def good_rollout(tmp_path):
    """A realistic multi-type rollout with session_meta, user, assistant,
    function_call, function_call_output, local_shell_call and one bad line."""
    path = tmp_path / "sess-abc.jsonl"
    lines = [
        {
            "type": "session_meta",
            "payload": {
                "id": "sess-abc",
                "timestamp": "2026-07-19T10:00:00+08:00",
                "cwd": "/workspace",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Implement a todo list"}],
                "timestamp": "2026-07-19T10:01:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "I'll create a FastAPI app."}],
                "timestamp": "2026-07-19T10:02:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "write_file",
                "arguments": '{"path": "src/main.py", "content": "print(1)"}',
                "timestamp": "2026-07-19T10:03:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "output": "Traceback: FileNotFoundError: no such file src/main.py",
                "timestamp": "2026-07-19T10:04:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Create the src directory first, then retry."}],
                "timestamp": "2026-07-19T10:05:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "local_shell_call",
                "command": "mkdir -p src && touch src/main.py",
                "timestamp": "2026-07-19T10:06:00+08:00",
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "patch",
                "arguments": '{"path": "src/main.py", "diff": "+print(2)"}',
                "timestamp": "2026-07-19T10:07:00+08:00",
            },
        },
        # Unknown shape should be counted as skipped/"other", never raise.
        {
            "type": "weird_unknown",
            "payload": {"foo": "bar"},
        },
    ]
    _write_jsonl(path, lines)
    # Append a malformed line
    with open(path, "a", encoding="utf-8") as f:
        f.write("this is not json\n")
    return str(path)


@pytest.fixture
def missing_meta_rollout(tmp_path):
    """A rollout file that lacks session_meta; parser should still return a timeline."""
    path = tmp_path / "fallback-id.jsonl"
    lines = [
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": "hi",
            },
        },
    ]
    _write_jsonl(path, lines)
    return str(path)


@pytest.fixture
def no_ts_rollout(tmp_path):
    path = tmp_path / "no-ts.jsonl"
    lines = [
        {"type": "session_meta", "payload": {"id": "no-ts", "timestamp": "2026-07-19T10:00:00Z"}},
        {
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": "x"},
        },
    ]
    _write_jsonl(path, lines)
    return str(path)


class TestParseRollout:
    def test_dataclasses(self):
        t = Turn(kind="user", text="hi", ts=None)
        rt = RolloutTimeline(session_id="s", path="/tmp/x.jsonl", turns=[t])
        assert rt.session_id == "s"
        assert rt.turns[0].kind == "user"

    def test_parses_session_meta_and_turns(self, good_rollout):
        timeline = parse_rollout(good_rollout)
        assert timeline.session_id == "sess-abc"
        assert timeline.path == good_rollout
        kinds = [t.kind for t in timeline.turns]
        assert kinds == ["user", "assistant", "tool", "tool", "user", "tool", "tool", "other"]
        assert timeline.turns[2].text == '{"path": "src/main.py", "content": "print(1)"}'
        assert "Traceback" in timeline.turns[3].text
        assert timeline.turns[0].ts == "2026-07-19T10:01:00+08:00"
        assert timeline.turns[2].ts == "2026-07-19T10:03:00+08:00"

    def test_missing_meta_uses_filename(self, missing_meta_rollout):
        timeline = parse_rollout(missing_meta_rollout)
        assert timeline.session_id == "fallback-id"
        assert len(timeline.turns) == 2
        assert timeline.turns[0].kind == "user"
        assert timeline.turns[1].kind == "assistant"

    def test_truncates_long_text(self, tmp_path):
        path = tmp_path / "long.jsonl"
        lines = [
            {"type": "session_meta", "payload": {"id": "long", "timestamp": "2026-07-19T10:00:00Z"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "x" * 5000}],
                },
            },
        ]
        _write_jsonl(path, lines)
        timeline = parse_rollout(str(path))
        assert len(timeline.turns[0].text) == 2000

    def test_expands_history_envelope_before_truncating(self, tmp_path):
        path = tmp_path / "history-envelope.jsonl"
        long_prompt = "first request " + "x" * 2500
        envelope = (
            "The following is the Codex agent history added since your last approval assessment.\n\n"
            "[1] developer: hidden policy\n\n"
            f"[2] user: {long_prompt}\n\n"
            "[3] assistant: hidden historical reply\n\n"
            "[4] user: second request\n\n"
            "[5] tool js call: hidden tool input"
        )
        lines = [
            {"type": "session_meta", "payload": {"id": "history", "timestamp": "2026-07-19T10:00:00Z"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": envelope,
                    "timestamp": "2026-07-19T10:01:00Z",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": "latest response",
                },
            },
        ]
        _write_jsonl(path, lines)

        timeline = parse_rollout(str(path))

        assert [turn.kind for turn in timeline.turns] == ["user", "user", "assistant"]
        assert len(timeline.turns[0].text) == 2000
        assert timeline.turns[0].from_history_envelope is True
        assert timeline.turns[1].from_history_envelope is True
        assert timeline.turns[1].text == "second request"
        assert timeline.turns[2].text == "latest response"
        assert compute_metrics([timeline])["user_turns"] == 2

    def test_bad_lines_are_skipped(self, good_rollout):
        timeline = parse_rollout(good_rollout)
        # The 9 good lines produce 8 turns (session_meta excluded), bad line skipped.
        assert len(timeline.turns) == 8

    def test_plain_string_content(self, no_ts_rollout):
        timeline = parse_rollout(no_ts_rollout)
        assert timeline.turns[0].text == "x"


class TestComputeMetrics:
    def test_basic_metrics(self, good_rollout):
        timeline = parse_rollout(good_rollout)
        metrics = compute_metrics([timeline])
        assert metrics["sessions"] == 1
        assert metrics["turns"] == 8
        assert metrics["user_turns"] == 2
        # First turn ts 10:01, last 10:07 => 6 minutes
        assert metrics["duration_min"] == 6
        assert metrics["error_fix_cycles"] == 1
        # src/main.py appears multiple times but should be counted once
        assert metrics["files_touched"] == 1

    def test_multi_session_metrics(self, good_rollout, missing_meta_rollout, no_ts_rollout):
        timelines = [
            parse_rollout(good_rollout),
            parse_rollout(missing_meta_rollout),
            parse_rollout(no_ts_rollout),
        ]
        metrics = compute_metrics(timelines)
        assert metrics["sessions"] == 3
        assert metrics["turns"] == 8 + 2 + 1
        assert metrics["user_turns"] == 2 + 1 + 1
        # good: 6min, missing: no ts -> 0, no-ts: only one turn ts -> 0
        assert metrics["duration_min"] == 6
        assert metrics["error_fix_cycles"] == 1

    def test_empty_timelines(self):
        metrics = compute_metrics([])
        assert metrics == {
            "sessions": 0,
            "turns": 0,
            "user_turns": 0,
            "duration_min": 0,
            "error_fix_cycles": 0,
            "files_touched": 0,
        }

    def test_files_touched_heuristic(self, tmp_path):
        """Multiple distinct paths in tool text should be counted distinctly."""
        path = tmp_path / "files.jsonl"
        lines = [
            {"type": "session_meta", "payload": {"id": "files", "timestamp": "2026-07-19T10:00:00Z"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "write_file",
                    "arguments": '{"path": "app/models.py", "content": ""}',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "write_file",
                    "arguments": '{"path": "app/main.py", "content": ""}',
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": "wrote app/models.py again",
                },
            },
        ]
        _write_jsonl(path, lines)
        timeline = parse_rollout(str(path))
        metrics = compute_metrics([timeline])
        assert metrics["files_touched"] == 2
