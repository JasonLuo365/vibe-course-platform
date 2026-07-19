import pytest
from vibe_submit.sessions import SessionInfo, find_sessions, read_session_info, session_index


def test_read_session_info_ok(make_session):
    path = make_session(
        session_id="s1", cwd="/proj", timestamp="2026-07-19T10:00:00+00:00"
    )
    info = read_session_info(path)
    assert isinstance(info, SessionInfo)
    assert info.session_id == "s1"
    assert info.cwd == "/proj"
    from datetime import datetime, timezone

    assert info.started_at == datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


def test_read_session_info_missing_meta(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text('{"type":"other"}\n', encoding="utf-8")
    assert read_session_info(path) is None


def test_read_session_info_bad_json(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text("not json\n", encoding="utf-8")
    assert read_session_info(path) is None


def test_find_sessions_filters_cwd_and_since(make_session, tmp_path):
    from datetime import datetime, timezone

    project = tmp_path / "project"
    project.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    make_session(
        name="match.jsonl",
        session_id="match",
        cwd=str(project),
        timestamp="2026-07-19T12:00:00Z",
    )
    make_session(
        name="wrong.jsonl",
        session_id="wrong",
        cwd=str(other),
        timestamp="2026-07-19T12:00:00Z",
    )
    make_session(
        name="old.jsonl",
        session_id="old",
        cwd=str(project),
        timestamp="2026-07-19T08:00:00Z",
    )
    since = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
    sessions = find_sessions(tmp_path / "codex", project, since)
    assert [s.session_id for s in sessions] == ["match"]


def test_session_index_counts_messages_and_tolerates_bad_lines(make_session):
    lines = [
        {
            "type": "response_item",
            "payload": {
                "role": "user",
                "content": "hi",
                "timestamp": "2026-07-19T10:01:00Z",
            },
        },
        {"type": "event_msg", "payload": {"role": "assistant", "content": "ok"}},
        {"type": "response_item", "payload": {"role": "system", "content": "x"}},
    ]
    path = make_session(session_id="idx1", lines=lines, bad_line=True)
    idx = session_index(path)
    assert idx["session_id"] == "idx1"
    assert idx["message_count"] == 2
    assert idx["started_at"] == "2026-07-19T10:00:00Z"
    assert idx["ended_at"] == "2026-07-19T10:01:00Z"

