import io
import sys

import pytest

from app import cli, models
from app.main import create_app


def _run_cli(monkeypatch, settings, args, stdin_text=""):
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["vibe-server", *args])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    cli.main()


def test_cli_prepares_classroom(monkeypatch, capsys, settings):
    # Initialize the test database once, then exercise the public operator commands.
    create_app(settings)

    monkeypatch.setenv("VIBE_TEACHER_PASSWORD", "a-safe-test-password")
    _run_cli(monkeypatch, settings, ["create-teacher", "teacher", "Teacher"])
    assert '"username": "teacher"' in capsys.readouterr().out

    _run_cli(monkeypatch, settings, ["create-course", "Vibe", "--term", "2026夏"])
    assert '"id": 1' in capsys.readouterr().out

    _run_cli(
        monkeypatch,
        settings,
        ["import-roster", "1", "--input", "-"],
        "学号,姓名,小组\n20260001,张三,第1组\n",
    )
    roster_output = capsys.readouterr().out
    assert "submit_token" in roster_output
    assert "vs_" in roster_output

    _run_cli(
        monkeypatch,
        settings,
        ["create-assignment", "1", "--input", "-"],
        """{
          "title": "作业", "rubric": [{"name": "功能", "weight": 100}],
          "opens_at": "2026-07-20T08:00:00+08:00",
          "deadline": "2026-07-20T23:59:00+08:00"
        }""",
    )
    assignment_output = capsys.readouterr().out
    assert '"id": 1' in assignment_output


def test_cli_rejects_duplicate_teacher(monkeypatch, settings):
    create_app(settings)
    monkeypatch.setenv("VIBE_TEACHER_PASSWORD", "a-safe-test-password")
    _run_cli(monkeypatch, settings, ["create-teacher", "teacher", "Teacher"])
    with pytest.raises(SystemExit, match="Teacher already exists"):
        _run_cli(monkeypatch, settings, ["create-teacher", "teacher", "Teacher"])
