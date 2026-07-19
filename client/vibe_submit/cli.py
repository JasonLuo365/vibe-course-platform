"""Command-line interface for vibe-submit."""

from __future__ import annotations

import argparse
import httpx
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import installed_version
from .api import ApiError, get_meta, upload
from .collect import FileEntry, collect_project
from .config import Config, ConfigError, ServerChangeRequired, _codex_home, load_config
from .outbox import get_outbox, list_outbox, remove_outbox, retry_config, save_outbox
from .package import build_package
from .sessions import find_sessions, session_index

# Transport seam for tests that mock the server's /health endpoint.
_health_transport = None


def _client_version() -> str:
    """Backward-compatible internal name for the installed client version."""
    return installed_version()


def _parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, normalising trailing Z to +00:00."""
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _confirm_server_change(url: str) -> bool:
    print(f"Project config wants a different server URL: {url}")
    answer = input("Use the project server URL? [y/N]: ")
    return answer.strip().lower().startswith("y")


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _is_screenshot(entry: FileEntry) -> bool:
    return (
        entry.relpath.startswith("screenshots/")
        or entry.relpath.startswith("screenshots\\")
    ) and Path(entry.relpath).suffix.lower() in _IMAGE_EXTENSIONS


def _partition_files(files: list[FileEntry]) -> tuple[list[FileEntry], list[FileEntry]]:
    code_files: list[FileEntry] = []
    screenshots: list[FileEntry] = []
    for entry in files:
        if _is_screenshot(entry):
            screenshots.append(entry)
        else:
            code_files.append(entry)
    return code_files, screenshots


def _print_preview(
    sessions,
    code_files: list[FileEntry],
    screenshots: list[FileEntry],
    skipped: list[str],
    package_size: int,
) -> None:
    total_bytes = sum(e.size for e in code_files + screenshots)
    print("Preview:")
    print(f"  Sessions: {len(sessions)}")
    for session in sessions:
        idx = session_index(session.path)
        print(
            f"    {session.session_id} | "
            f"started {idx.get('started_at', '?')} | "
            f"ended {idx.get('ended_at', '?')} | "
            f"messages {idx.get('message_count', 0)}"
        )
    print(f"  Code files: {len(code_files)}")
    print(f"  Screenshots: {len(screenshots)}")
    print(f"  Total content bytes: {total_bytes}")
    print(f"  Package size: {package_size} bytes")
    print(f"  Skipped denylist entries: {len(skipped)}")
    for item in skipped:
        print(f"    - {item}")


def _cmd_submit(args: argparse.Namespace) -> int:
    project_root = Path(args.project).resolve()

    try:
        cfg = load_config(project_root, confirm=_confirm_server_change)
    except ServerChangeRequired as exc:
        print(
            f"Server URL change required: {exc.url}. "
            "Confirm interactively with the CLI.",
            file=sys.stderr,
        )
        return 1
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        meta = get_meta(cfg, args.code)
    except ApiError as exc:
        print(f"Failed to fetch assignment meta: {exc}", file=sys.stderr)
        return 1

    if not meta.get("accepts", True):
        print(
            f"Assignment {args.code} is not accepting submissions.",
            file=sys.stderr,
        )
        return 2

    opens_at = meta.get("opens_at")
    since = _parse_iso(opens_at) if opens_at else None

    sessions = find_sessions(_codex_home(), project_root, since)
    files, skipped = collect_project(project_root)
    code_files, screenshots = _partition_files(files)

    package_meta = {
        "assignment_code": args.code,
        "student_no": cfg.student_no,
        "client_version": _client_version(),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path, manifest, stats = build_package(
            project_root,
            sessions,
            code_files,
            screenshots,
            package_meta,
            Path(tmpdir),
        )
        package_size = zip_path.stat().st_size
        _print_preview(sessions, code_files, screenshots, skipped, package_size)

        if not args.yes:
            answer = input("Submit? [y/N]: ")
            if answer.strip().lower() != "y":
                print("Submission cancelled.")
                return 0

        try:
            result = upload(cfg, zip_path, manifest, force=args.force)
        except ApiError as exc:
            if exc.status == 409 and not args.force:
                print(
                    f"Conflict: {exc.message}. "
                    "Use --force to overwrite the previous attempt.",
                    file=sys.stderr,
                )
                return 3
            if exc.status == 0 or exc.status >= 500:
                outbox_id = save_outbox(zip_path, manifest, cfg)
                print(
                    f"Network/server error ({exc.code}); "
                    f"submission saved to outbox {outbox_id}. "
                    f"Run `vibe-submit retry {outbox_id}` later.",
                    file=sys.stderr,
                )
                return 1
            print(f"Upload failed ({exc.status}/{exc.code}): {exc.message}", file=sys.stderr)
            return 1

    print(
        f"Submitted successfully: submission_id={result.get('submission_id')} "
        f"attempt_no={result.get('attempt_no')}"
    )
    return 0


def _cmd_retry(args: argparse.Namespace) -> int:
    if args.outbox_id is None:
        entries = list_outbox()
        if not entries:
            print("No outbox entries.")
            return 0
        print("Outbox entries:")
        for entry in entries:
            print(
                f"  {entry['id']} | {entry['assignment_code']} | "
                f"{entry['size']} bytes | {entry['saved_at']}"
            )
        return 0

    try:
        zip_path, manifest = get_outbox(args.outbox_id)
    except Exception as exc:
        print(f"Cannot load outbox entry: {exc}", file=sys.stderr)
        return 1

    try:
        cfg = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    try:
        cfg = retry_config(args.outbox_id, cfg)
    except Exception as exc:
        print(f"Cannot retry outbox entry: {exc}", file=sys.stderr)
        return 1

    try:
        result = upload(cfg, zip_path, manifest, force=False)
    except ApiError as exc:
        print(f"Retry failed ({exc.status}/{exc.code}): {exc.message}", file=sys.stderr)
        return 1

    try:
        remove_outbox(args.outbox_id)
    except Exception as exc:
        print(f"Retry succeeded, but could not remove outbox entry: {exc}", file=sys.stderr)

    print(
        f"Retried successfully: submission_id={result.get('submission_id')} "
        f"attempt_no={result.get('attempt_no')}"
    )
    return 0


def _cmd_doctor(_args: argparse.Namespace) -> int:
    ok = True

    try:
        cfg = load_config()
        print("[OK] Configuration loaded")
    except Exception as exc:
        print(f"[FAIL] Configuration: {exc}")
        ok = False
        cfg = None

    sessions_dir = _codex_home() / "sessions"
    if sessions_dir.exists() and sessions_dir.is_dir():
        print("[OK] Codex sessions directory found")
    else:
        print("[FAIL] Codex sessions directory not found")
        ok = False

    if cfg:
        reachable, reason = _check_server(cfg.server_url)
        if reachable:
            print("[OK] Server reachable")
        else:
            print(f"[FAIL] Server check: {reason}")
            ok = False

    print(f"[INFO] Client version: {_client_version()}")
    return 0 if ok else 1


def _check_server(server_url: str) -> tuple[bool, str]:
    """Probe the server's health endpoint."""
    url = f"{server_url.rstrip('/')}/health"
    try:
        with httpx.Client(timeout=10, transport=_health_transport) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, str(exc)

    if response.status_code != 200:
        return False, f"HTTP {response.status_code}"

    try:
        data = response.json()
    except Exception as exc:
        return False, f"invalid JSON: {exc}"

    if data.get("status") != "ok":
        return False, f"unexpected status: {data!r}"

    return True, ""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibe-submit",
        description="Vibe Coding homework submission client",
    )
    parser.set_defaults(func=None)
    sub = parser.add_subparsers(dest="command")

    submit_parser = sub.add_parser("submit", help="Submit an assignment")
    submit_parser.add_argument("--code", required=True, help="Assignment code")
    submit_parser.add_argument(
        "--project", default=".", help="Project root directory (default: current directory)"
    )
    submit_parser.add_argument(
        "--yes", action="store_true", help="Skip interactive confirmation"
    )
    submit_parser.add_argument(
        "--force", action="store_true", help="Force overwrite on conflict"
    )
    submit_parser.set_defaults(func=_cmd_submit)

    retry_parser = sub.add_parser("retry", help="Retry or list outbox submissions")
    retry_parser.add_argument("outbox_id", nargs="?", help="Outbox entry to retry")
    retry_parser.set_defaults(func=_cmd_retry)

    doctor_parser = sub.add_parser("doctor", help="Check client health")
    doctor_parser.set_defaults(func=_cmd_doctor)

    from .bootstrap import DEFAULT_INDEX_URL, _cmd_bootstrap

    bootstrap_parser = sub.add_parser("bootstrap", help="Set up this machine for submissions")
    bootstrap_parser.add_argument(
        "--index-url",
        default=DEFAULT_INDEX_URL,
        help="PyPI index URL used while bootstrapping uv (default: Tsinghua mirror)",
    )
    bootstrap_parser.add_argument(
        "--marketplace-url",
        required=True,
        help="Codex marketplace URL to register",
    )
    bootstrap_parser.add_argument(
        "--marketplace-name",
        default=None,
        help="Marketplace name (default: derived from URL)",
    )
    bootstrap_parser.add_argument(
        "--student-no",
        default=None,
        help="Student number (non-interactive mode)",
    )
    bootstrap_parser.add_argument(
        "--token",
        default=None,
        help="Submit token (non-interactive mode)",
    )
    bootstrap_parser.add_argument(
        "--server",
        default=None,
        help="Server URL (non-interactive mode)",
    )
    bootstrap_parser.set_defaults(func=_cmd_bootstrap)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.func is None:
        parser.print_help()
        sys.exit(1)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

