"""Bootstrap command for setting up a student machine end-to-end."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import ConfigError, _codex_home, _global_config_path, _toml_str, validate_server_url

DEFAULT_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _uv_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def _is_local_url(url: str) -> bool:
    if url.startswith(("file:", "/")):
        return True
    if "://" not in url and Path(url).exists():
        return True
    parsed = urlparse(url)
    return parsed.scheme in ("", "file")


def _marketplace_name(url: str, name: str | None) -> str:
    if name:
        return name
    if _is_local_url(url):
        return Path(url).name or "local"
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.replace(".", "_")
    return "course"


def _ensure_uv(index_url: str) -> bool:
    if shutil.which("uvx"):
        print("✓ uv check: uvx found")
        return True

    print("✗ uv check: uvx not found; installing...")
    env = os.environ.copy()
    env["UV_INDEX_URL"] = index_url

    if sys.platform == "win32":
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "ByPass",
            "-c",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ]
    else:
        cmd = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]

    try:
        subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"✗ uv check: installation failed ({stderr})")
        return False

    uv_bin = str(_uv_bin_dir())
    current_path = os.environ.get("PATH", "")
    if uv_bin not in current_path.split(os.pathsep):
        os.environ["PATH"] = uv_bin + os.pathsep + current_path

    print("✓ uv check: installed")
    return True


def _marketplace_section(name: str, url: str) -> list[str]:
    source_type = "local" if _is_local_url(url) else "git"
    return [
        f"\n[marketplaces.{name}]\n",
        f"source_type = \"{source_type}\"\n",
        f"source = {_toml_str(url)}\n",
        f"last_updated = \"{_now_iso()}\"\n",
    ]


def _register_marketplace(url: str, name: str | None) -> bool:
    mp_name = _marketplace_name(url, name)

    if shutil.which("codex"):
        try:
            result = subprocess.run(
                ["codex", "plugin", "marketplace", "add", url],
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            print(f"✗ marketplace: registration failed ({exc})")
            return False

        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0 or "already added" in output.lower():
            if "already added" in output.lower():
                print(f"skipped marketplace: '{mp_name}' already added")
            else:
                print(f"✓ marketplace: '{mp_name}' registered via codex CLI")
            return True

        print(f"✗ marketplace: registration failed ({output.strip()})")
        return False

    # Codex CLI is missing: write the desktop-only fallback config.
    home = _codex_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.toml"

    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    section_header = f"[marketplaces.{mp_name}]"

    if section_header in existing:
        print(f"skipped marketplace: '{mp_name}' already configured")
    else:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        existing += "".join(_marketplace_section(mp_name, url))
        config_path.write_text(existing, encoding="utf-8")
        print(f"✓ marketplace: '{mp_name}' written to {config_path}")

    print("Note: desktop-only students should also install Codex CLI when convenient.")
    return True


def _write_config_preserving(path: Path, updates: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        lines = [f"{key} = {_toml_str(value)}\n" for key, value in updates.items()]
        path.write_text("".join(lines), encoding="utf-8")
        _chmod_private(path)
        return

    text = path.read_text(encoding="utf-8")
    has_section = any(line.strip() == "[vibe-submit]" for line in text.splitlines())
    target_section = "vibe-submit" if has_section else None

    lines = text.splitlines(keepends=True)
    new_lines: list[str] = []
    updated: set[str] = set()
    current_section: str | None = None

    def _flush_missing() -> None:
        if current_section != target_section or target_section is None:
            return
        for key, value in updates.items():
            if key not in updated:
                new_lines.append(f"{key} = {_toml_str(value)}\n")
                updated.add(key)

    for raw_line in lines:
        stripped = raw_line.strip()
        section = _section_name(stripped)
        if section is not None:
            _flush_missing()
            current_section = section

        key = _top_level_key(stripped)
        if key in updates and current_section == target_section:
            new_lines.append(f"{key} = {_toml_str(updates[key])}\n")
            updated.add(key)
        else:
            new_lines.append(raw_line)

    _flush_missing()

    # For top-level updates, append any missing keys before the first section.
    if target_section is None:
        remaining = [k for k in updates if k not in updated]
        if remaining:
            first_section_idx = next(
                (
                    i
                    for i, line in enumerate(new_lines)
                    if _section_name(line.strip()) is not None
                ),
                len(new_lines),
            )
            inserts = [f"{key} = {_toml_str(updates[key])}\n" for key in remaining]
            new_lines[first_section_idx:first_section_idx] = inserts
            updated.update(remaining)

    # Fallback: append anything that escaped (should not happen).
    for key, value in updates.items():
        if key not in updated:
            new_lines.append(f"{key} = {_toml_str(value)}\n")

    path.write_text("".join(new_lines), encoding="utf-8")
    _chmod_private(path)


def _section_name(line: str) -> str | None:
    if line.startswith("[") and line.endswith("]"):
        return line[1:-1].strip()
    return None


def _top_level_key(line: str) -> str | None:
    if "=" not in line or line.startswith("#"):
        return None
    return line.split("=", 1)[0].strip()


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass


def _student_registration(
    server_url: str, course_code: str, student_no: str, name: str, password: str, password_confirm: str
) -> bool:
    try:
        response = httpx.post(
            f"{server_url}/api/student-registration",
            json={
                "course_code": course_code,
                "student_no": student_no,
                "name": name,
                "password": password,
                "password_confirm": password_confirm,
            },
            timeout=30.0,
        )
    except httpx.RequestError as exc:
        print(f"config: registration failed ({exc})")
        return False
    if response.is_success:
        return True
    try:
        message = response.json().get("error", {}).get("message", response.text)
    except Exception:
        message = response.text
    print(f"config: registration failed ({message})")
    return False


def _configure(
    student_no: str | None,
    name: str | None,
    course_code: str | None,
    password: str | None,
    password_confirm: str | None,
    server_url: str | None,
) -> bool:
    if server_url is None:
        server_url = input("server URL: ").strip()
    if course_code is None:
        course_code = input("课程邀请码: ").strip()
    if student_no is None:
        student_no = input("学号: ").strip()
    if name is None:
        name = input("姓名: ").strip()
    print("密码要求：8–12 位。为便于核对，输入内容会直接显示在终端。")
    if password is None:
        password = input("用户密码: ")
    if password_confirm is None:
        password_confirm = input("确认密码: ")
    if password != password_confirm:
        print("config: 两次输入的密码不一致")
        return False
    if not 8 <= len(password) <= 12:
        print("config: 密码长度须为 8 到 12 个字符")
        return False

    try:
        server_url = validate_server_url(server_url)
    except ConfigError as exc:
        print(f"✗ config: {exc}")
        return False
    if not _student_registration(server_url, course_code, student_no, name, password, password_confirm):
        return False

    path = _global_config_path()
    _write_config_preserving(
        path,
        {
            "server_url": server_url,
            "student_no": student_no,
            "password": password,
        },
    )
    print(f"✓ config: written to {path}")
    return True


def _run_doctor() -> int:
    from . import cli

    return cli._cmd_doctor(argparse.Namespace())


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    ok = True

    if not _ensure_uv(args.index_url or DEFAULT_INDEX_URL):
        ok = False

    if not _register_marketplace(args.marketplace_url, args.marketplace_name):
        ok = False

    if not _configure(
        args.student_no,
        args.name,
        args.course_code,
        args.password,
        args.password_confirm,
        args.server,
    ):
        ok = False

    doctor_code = _run_doctor()
    if doctor_code == 0:
        print("✓ doctor: checks passed")
    else:
        print("✗ doctor: checks reported problems")
        ok = False

    return 0 if ok else 1

