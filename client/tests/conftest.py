import json
import os

import pytest


@pytest.fixture
def make_session(tmp_path):
    """Factory for rollout session jsonl files."""

    def _make(
        name="session.jsonl",
        session_id="s1",
        cwd=None,
        timestamp="2026-07-19T10:00:00Z",
        lines=None,
        bad_line=False,
    ):
        codex = tmp_path / "codex" / "sessions"
        codex.mkdir(parents=True, exist_ok=True)
        path = codex / name
        if cwd is None:
            cwd = str(tmp_path / "project")
        meta = {
            "type": "session_meta",
            "payload": {"id": session_id, "timestamp": timestamp, "cwd": cwd},
        }
        out_lines = [json.dumps(meta)]
        if lines:
            for line in lines:
                out_lines.append(json.dumps(line) if isinstance(line, dict) else line)
        if bad_line:
            out_lines.append("this is not valid json")
        path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        return path

    return _make


@pytest.fixture
def make_project(tmp_path):
    """Factory for temporary project trees."""

    def _make(files=None, dirs=None, symlink=None):
        root = tmp_path / "project"
        root.mkdir(parents=True, exist_ok=True)
        if dirs:
            for d in dirs:
                (root / d).mkdir(parents=True, exist_ok=True)
        if files:
            for relpath, content in files.items():
                p = root / relpath
                p.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    p.write_bytes(content)
                else:
                    p.write_text(content, encoding="utf-8")
        if symlink:
            target_name, link_name = symlink
            target = root / target_name
            link = root / link_name
            try:
                os.symlink(target, link)
            except OSError as exc:
                if getattr(exc, "winerror", None) == 1314:
                    pytest.skip("symbolic links require elevated privileges on Windows")
                raise
        return root

    return _make
