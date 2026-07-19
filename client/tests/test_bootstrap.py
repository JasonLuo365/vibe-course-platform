"""Tests for vibe_submit.bootstrap."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def bootstrap_env(monkeypatch, tmp_path):
    """Isolate bootstrap's on-disk homes, PATH and doctor's network check."""
    from vibe_submit import cli

    monkeypatch.setenv("VIBE_SUBMIT_HOME", str(tmp_path / "vibe-submit-home"))
    monkeypatch.setenv("VIBE_CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("PATH", r"C:\Windows\System32")

    # Make doctor's server and sessions checks pass by default so tests focus
    # on bootstrap behaviour, not the machine state.
    (tmp_path / "codex-home" / "sessions").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "_check_server", lambda url: (True, ""))
    return tmp_path


@pytest.fixture
def which_state(monkeypatch):
    state = {"uvx": False, "codex": False}

    def fake_which(name, path=None):
        if name == "uvx" and state["uvx"]:
            return str(Path.home() / ".local" / "bin" / "uvx")
        if name == "codex" and state["codex"]:
            return str(Path.home() / ".local" / "bin" / "codex")
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    return state


@pytest.fixture
def run_bootstrap(monkeypatch):
    def _run(args):
        from vibe_submit import cli

        captured = {"code": None, "stdout": "", "stderr": ""}

        def fake_exit(code=0):
            captured["code"] = code
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", fake_exit)
        stdout = io.StringIO()
        stderr = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout)
        monkeypatch.setattr(sys, "stderr", stderr)
        try:
            cli.main([str(a) for a in args])
        except SystemExit as exc:
            captured["code"] = exc.code
        captured["stdout"] = stdout.getvalue()
        captured["stderr"] = stderr.getvalue()
        return captured

    return _run


@pytest.fixture
def capture_subprocess(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def _read_toml(path: Path) -> dict:
    import tomllib

    if not path.exists():
        return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def test_uv_missing_installs_with_mirror_env(
    bootstrap_env, which_state, capture_subprocess, run_bootstrap
):
    which_state["uvx"] = False
    which_state["codex"] = False

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--marketplace-name",
            "course",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    installer_calls = [
        c for c in capture_subprocess if "install" in str(c["args"]).lower()
    ]
    assert len(installer_calls) == 1
    call = installer_calls[0]
    assert "powershell" in str(call["args"]).lower() or "curl" in str(call["args"]).lower()
    env = call["kwargs"].get("env", {})
    assert env.get("UV_INDEX_URL") == "https://pypi.tuna.tsinghua.edu.cn/simple"
    # Mirror must NOT leak into the parent process environment.
    assert os.environ.get("UV_INDEX_URL") is None
    # Standard install dir prepended to PATH for this process.
    expected_bin = str(Path.home() / ".local" / "bin")
    assert os.environ["PATH"].startswith(expected_bin)


def test_uv_missing_uses_custom_index_url(
    bootstrap_env, which_state, capture_subprocess, run_bootstrap
):
    which_state["uvx"] = False
    custom = "https://custom.example/simple"

    run_bootstrap(
        [
            "bootstrap",
            "--index-url",
            custom,
            "--marketplace-url",
            "https://example.com/marketplace",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    installer_calls = [
        c for c in capture_subprocess if "install" in str(c["args"]).lower()
    ]
    assert installer_calls[0]["kwargs"]["env"].get("UV_INDEX_URL") == custom


def test_uv_present_skips_install(bootstrap_env, which_state, capture_subprocess, run_bootstrap):
    which_state["uvx"] = True
    which_state["codex"] = False

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    assert not capture_subprocess
    assert "skipped" in captured["stdout"].lower() or "ok" in captured["stdout"].lower()


def test_codex_present_runs_marketplace_add(
    bootstrap_env, which_state, capture_subprocess, run_bootstrap
):
    which_state["uvx"] = True
    which_state["codex"] = True
    url = "https://example.com/marketplace"

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            url,
            "--marketplace-name",
            "course",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    add_calls = [c for c in capture_subprocess if "marketplace" in c["args"]]
    assert len(add_calls) == 1
    assert add_calls[0]["args"] == ["codex", "plugin", "marketplace", "add", url]


def test_codex_present_tolerates_already_added(
    bootstrap_env, which_state, monkeypatch, run_bootstrap
):
    which_state["uvx"] = True
    which_state["codex"] = True

    def fake_run(args, **kwargs):
        return MagicMock(returncode=0, stdout="marketplace already added", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--marketplace-name",
            "course",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    assert "skipped" in captured["stdout"].lower()


def test_codex_missing_writes_marketplace_config_preserving_existing(
    bootstrap_env, which_state, run_bootstrap
):
    which_state["uvx"] = True
    which_state["codex"] = False
    url = "https://example.com/marketplace"

    codex_home = Path(os.environ["VIBE_CODEX_HOME"])
    codex_home.mkdir(parents=True, exist_ok=True)
    existing_config = codex_home / "config.toml"
    existing_config.write_text('[plugin]\nkey = "keep-me"\n', encoding="utf-8")

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            url,
            "--marketplace-name",
            "course",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    text = existing_config.read_text(encoding="utf-8")
    assert '[plugin]' in text
    assert 'key = "keep-me"' in text
    assert '[marketplaces.course]' in text
    assert 'source_type = "git"' in text
    assert f'source = "{url}"' in text
    assert "last_updated" in text
    assert "desktop-only" in captured["stdout"].lower()


def test_config_flags_write_config(bootstrap_env, which_state, run_bootstrap):
    which_state["uvx"] = True
    which_state["codex"] = False

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    cfg_path = Path(os.environ["VIBE_SUBMIT_HOME"]) / ".vibe-submit" / "config.toml"
    data = _read_toml(cfg_path)
    assert data["server_url"] == "https://server.example"
    assert data["student_no"] == "2026001"
    assert data["submit_token"] == "secret-token"
    assert "config" in captured["stdout"].lower()


def test_config_preserves_existing_keys(bootstrap_env, which_state, run_bootstrap):
    which_state["uvx"] = True
    which_state["codex"] = False

    cfg_dir = Path(os.environ["VIBE_SUBMIT_HOME"]) / ".vibe-submit"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "config.toml"
    cfg_path.write_text(
        'other_key = "preserve"\nserver_url = "https://old.example"\n',
        encoding="utf-8",
    )

    run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--server",
            "https://new.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    data = _read_toml(cfg_path)
    assert data["other_key"] == "preserve"
    assert data["server_url"] == "https://new.example"
    assert data["student_no"] == "2026001"


def test_config_prompts_when_flags_missing(bootstrap_env, which_state, monkeypatch, run_bootstrap):
    which_state["uvx"] = True
    which_state["codex"] = False

    inputs = iter(["2026001", "secret-token", "https://server.example"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
        ]
    )

    assert captured["code"] == 0
    cfg_path = Path(os.environ["VIBE_SUBMIT_HOME"]) / ".vibe-submit" / "config.toml"
    data = _read_toml(cfg_path)
    assert data["student_no"] == "2026001"
    assert data["submit_token"] == "secret-token"
    assert data["server_url"] == "https://server.example"


def test_doctor_runs_at_end(bootstrap_env, which_state, monkeypatch, run_bootstrap):
    which_state["uvx"] = True
    which_state["codex"] = False

    calls = []

    def fake_cmd_doctor(args):
        calls.append(args)
        return 0

    monkeypatch.setattr("vibe_submit.cli._cmd_doctor", fake_cmd_doctor)

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    assert len(calls) == 1
    assert "doctor" in captured["stdout"].lower()


def test_idempotent_second_run(bootstrap_env, which_state, capture_subprocess, run_bootstrap):
    which_state["uvx"] = False
    which_state["codex"] = False

    run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--marketplace-name",
            "course",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    # Second run: uv now present, codex CLI present.
    capture_subprocess.clear()
    which_state["uvx"] = True
    which_state["codex"] = True

    captured = run_bootstrap(
        [
            "bootstrap",
            "--marketplace-url",
            "https://example.com/marketplace",
            "--marketplace-name",
            "course",
            "--server",
            "https://server.example",
            "--student-no",
            "2026001",
            "--token",
            "secret-token",
        ]
    )

    assert captured["code"] == 0
    assert any("marketplace" in str(c["args"]) for c in capture_subprocess)

