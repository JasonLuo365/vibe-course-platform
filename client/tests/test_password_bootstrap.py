"""Tests for password-based student installation."""

from __future__ import annotations

import tomllib

from vibe_submit import bootstrap


def test_configure_registers_student_and_persists_password(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    seen = {}

    def register(server_url, course_code, student_no, name, password, password_confirm):
        seen.update(
            server_url=server_url,
            course_code=course_code,
            student_no=student_no,
            name=name,
            password=password,
            password_confirm=password_confirm,
        )
        return True

    monkeypatch.setattr(bootstrap, "_student_registration", register)
    assert bootstrap._configure(
        "2026001", "张三", "vc_invite", "student-pass", "student-pass", "https://class.example"
    )
    assert seen == {
        "server_url": "https://class.example",
        "course_code": "vc_invite",
        "student_no": "2026001",
        "name": "张三",
        "password": "student-pass",
        "password_confirm": "student-pass",
    }
    with open(tmp_path / ".vibe-submit" / "config.toml", "rb") as fh:
        saved = tomllib.load(fh)
    assert saved == {
        "server_url": "https://class.example",
        "student_no": "2026001",
        "password": "student-pass",
    }


def test_configure_rejects_mismatched_password_before_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    called = False

    def register(*args):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(bootstrap, "_student_registration", register)
    assert not bootstrap._configure(
        "2026001", "张三", "vc_invite", "student-pass", "other-password", "https://class.example"
    )
    assert called is False


def test_configure_rejects_password_outside_8_to_12_characters(tmp_path, monkeypatch):
    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path))
    called = False

    def register(*args):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(bootstrap, "_student_registration", register)
    assert not bootstrap._configure(
        "2026001", "张三", "vc_invite", "too-long-password", "too-long-password", "https://class.example"
    )
    assert called is False
