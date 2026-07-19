"""Configuration loading for vibe-submit."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .errors import ConfigError, ServerChangeRequired


@dataclass(frozen=True)
class Config:
    """Resolved submission configuration."""

    server_url: str
    student_no: str
    submit_token: str
    source: str


def validate_server_url(value: str) -> str:
    """Accept only a normal HTTPS origin for student submissions."""
    url = str(value).strip().rstrip("/")
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError("server_url must be an HTTPS origin, for example https://class.example.edu")
    return url


def _codex_home() -> Path:
    home = os.environ.get("VIBE_CODEX_HOME")
    if home:
        return Path(home)
    return Path.home() / ".codex"


def _config_dir() -> Path:
    """Return the vibe-submit home directory."""
    home = os.environ.get("VIBE_SUBMIT_HOME")
    base = Path(home) if home else Path.home()
    return base / ".vibe-submit"


def _global_config_path() -> Path:
    return _config_dir() / "config.toml"


def _project_config_path(project_root: Path | None) -> Path | None:
    if project_root is None:
        return None
    return Path(project_root) / ".vibe-submit.toml"


def _get_key(data: dict, key: str) -> str | None:
    """Read a top-level key or a key under the [vibe-submit] section."""
    if key in data:
        return data[key]
    section = data.get("vibe-submit", {})
    if isinstance(section, dict):
        return section.get(key)
    return None


def load_config(
    project_root: Path | str | None = None,
    *,
    confirm: Callable[[str], bool] | None = None,
) -> Config:
    """Load configuration, preferring the global config file.

    If ``project_root`` contains a ``.vibe-submit.toml`` with a ``server_url``
    that differs from the global value, a ``confirm`` callback is invoked for
    CLI interactive confirmation.  If no callback is provided (library/MCP use),
    ``ServerChangeRequired`` is raised instead.
    """
    global_path = _global_config_path()
    if not global_path.exists():
        raise ConfigError(f"global config not found: {global_path}")

    with open(global_path, "rb") as fh:
        global_data = tomllib.load(fh)

    server_url = _get_key(global_data, "server_url")
    student_no = _get_key(global_data, "student_no")
    submit_token = _get_key(global_data, "submit_token")

    if not server_url or not student_no or not submit_token:
        raise ConfigError(
            "global config missing one of required fields: "
            "server_url, student_no, submit_token"
        )

    server_url = validate_server_url(str(server_url))
    source = "global"
    project_path = _project_config_path(
        Path(project_root) if project_root is not None else None
    )

    if project_path and project_path.exists():
        with open(project_path, "rb") as fh:
            project_data = tomllib.load(fh)
        project_url = _get_key(project_data, "server_url")
        if project_url:
            project_url = validate_server_url(str(project_url))
        if project_url and project_url != server_url:
            if confirm is None:
                raise ServerChangeRequired(project_url)
            if not confirm(project_url):
                raise ConfigError("server URL change not confirmed")
            server_url = project_url
            source = "project"
        elif project_url:
            source = "project"

    return Config(
        server_url=server_url,
        student_no=str(student_no),
        submit_token=str(submit_token),
        source=source,
    )


def write_config(path: Path, data: dict) -> None:
    """Write a minimal TOML config file with restricted permissions.

    Permissions are set to ``0o600`` on POSIX systems; on Windows this is
    best-effort and failures are ignored.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f'server_url = {_toml_str(data.get("server_url", ""))}\n',
        f'student_no = {_toml_str(data.get("student_no", ""))}\n',
        f'submit_token = {_toml_str(data.get("submit_token", ""))}\n',
    ]
    path.write_text("".join(lines), encoding="utf-8")

    try:
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass


def _toml_str(value: str) -> str:
    """Return a basic TOML string literal; values are assumed simple strings."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

