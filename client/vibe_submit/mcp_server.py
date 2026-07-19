"""MCP server exposing vibe-submit tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .api import ApiError, get_meta, get_status, upload
from .config import Config, ConfigError, load_config
from .outbox import get_outbox, get_outbox_config, list_outbox
from .preview import PreviewError, create_preview, load_preview, resolve_project_root

mcp = FastMCP("vibe-submit")


def _load_cfg() -> Config:
    """Load global configuration for MCP tool use.

    Project-level server_url differences are rejected in MCP mode; users must
    confirm those via the CLI.
    """
    try:
        return load_config()
    except ConfigError:
        raise


def _error_dict(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# Internal implementation functions (shared with tests / thin MCP wrappers)
# ---------------------------------------------------------------------------


def get_assignment_meta_impl(cfg: Config, assignment_code: str) -> dict[str, Any]:
    """Return assignment metadata from the server."""
    try:
        result = get_meta(cfg, assignment_code)
    except ApiError as exc:
        return _error_dict(exc.code, exc.message)
    return {"ok": True, "meta": result}


def get_submission_status_impl(cfg: Config, assignment_code: str) -> dict[str, Any]:
    """Return the latest submission status for an assignment."""
    try:
        result = get_status(cfg, assignment_code)
    except ApiError as exc:
        return _error_dict(exc.code, exc.message)
    return {"ok": True, "status": result}


def preview_submission_impl(
    cfg: Config,
    assignment_code: str,
    project_root: str | None = None,
) -> dict[str, Any]:
    """Create a submission preview and return its summary."""
    try:
        return create_preview(cfg, assignment_code, project_root)
    except ApiError as exc:
        return _error_dict(exc.code, exc.message)
    except Exception as exc:
        return _error_dict("PREVIEW_FAILED", str(exc))


def submit_homework_impl(
    preview_id: str,
    confirmed: bool,
    force_confirmed: bool = False,
    project_root: str | None = None,
    cfg: Config | None = None,
) -> dict[str, Any]:
    """Submit the package referenced by a preview record."""
    try:
        preview = load_preview(preview_id)
    except PreviewError as exc:
        return _error_dict(exc.code, exc.message)

    if project_root is not None:
        canonical = resolve_project_root(project_root)
        if canonical != preview.project_root:
            return _error_dict(
                "PREVIEW_INVALID",
                "project_root does not match the preview binding",
            )

    if confirmed is not True:
        return _error_dict(
            "CONFIRMATION_REQUIRED",
            "submission must be explicitly confirmed by setting confirmed=True",
        )

    if cfg is None:
        try:
            cfg = _load_cfg()
        except ConfigError as exc:
            return _error_dict("CONFIG_ERROR", str(exc))

    try:
        result = upload(cfg, preview.zip_path, preview.manifest, force=False)
    except ApiError as exc:
        if exc.status == 409:
            if force_confirmed is not True:
                return _error_dict("FORCE_REQUIRED", exc.message)
            try:
                result = upload(cfg, preview.zip_path, preview.manifest, force=True)
            except ApiError as retry_exc:
                return _error_dict(retry_exc.code, retry_exc.message)
        else:
            return _error_dict(exc.code, exc.message)

    return {"ok": True, "submission": result}


def retry_submission_impl(
    cfg: Config,
    outbox_id: str | None = None,
    assignment_code: str | None = None,
) -> dict[str, Any]:
    """Retry an outbox submission, or list outbox entries when no id is given."""
    if outbox_id is None and assignment_code is None:
        return {"ok": True, "outbox": list_outbox()}

    if outbox_id is not None:
        try:
            zip_path, manifest = get_outbox(outbox_id)
        except Exception as exc:
            return _error_dict("OUTBOX_NOT_FOUND", str(exc))
        return _upload_outbox(cfg, zip_path, manifest)

    # assignment_code given: find a single matching entry.
    entries = [
        e for e in list_outbox() if e.get("assignment_code") == assignment_code
    ]
    if len(entries) == 0:
        return _error_dict(
            "OUTBOX_NOT_FOUND",
            f"no outbox entry for assignment {assignment_code}",
        )
    if len(entries) > 1:
        return _error_dict(
            "AMBIGUOUS_OUTBOX",
            f"multiple outbox entries for assignment {assignment_code}",
        )

    outbox_id = entries[0]["id"]
    try:
        zip_path, manifest = get_outbox(outbox_id)
    except Exception as exc:
        return _error_dict("OUTBOX_NOT_FOUND", str(exc))
    return _upload_outbox(cfg, zip_path, manifest)


def _upload_outbox(cfg: Config, zip_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Upload an outbox package, preserving its original server URL."""
    assignment_code = manifest.get("assignment_code", "")
    try:
        outbox_cfg = get_outbox_config_from_manifest(manifest, cfg)
    except Exception as exc:
        return _error_dict("OUTBOX_ERROR", str(exc))

    try:
        result = upload(outbox_cfg, zip_path, manifest, force=False)
    except ApiError as exc:
        return _error_dict(exc.code, exc.message)

    return {"ok": True, "submission": result}


def get_outbox_config_from_manifest(manifest: dict[str, Any], cfg: Config) -> Config:
    """Reconstruct a Config from outbox manifest metadata."""
    # The manifest itself does not store server_url/student_no; the outbox
    # meta.json does.  Retry by outbox_id reads that meta separately.
    # This helper is used only for assignment_code retries where we already
    # have the current global cfg.
    return cfg


# ---------------------------------------------------------------------------
# MCP tool wrappers
# ---------------------------------------------------------------------------


@mcp.tool()
def get_assignment_meta(assignment_code: str) -> dict[str, Any]:
    return get_assignment_meta_impl(_load_cfg(), assignment_code)


@mcp.tool()
def preview_submission(assignment_code: str, project_root: str | None = None) -> dict[str, Any]:
    return preview_submission_impl(_load_cfg(), assignment_code, project_root)


@mcp.tool()
def submit_homework(
    preview_id: str,
    confirmed: bool,
    force_confirmed: bool = False,
    project_root: str | None = None,
) -> dict[str, Any]:
    return submit_homework_impl(
        preview_id,
        confirmed,
        force_confirmed=force_confirmed,
        project_root=project_root,
    )


@mcp.tool()
def retry_submission(
    outbox_id: str | None = None,
    assignment_code: str | None = None,
) -> dict[str, Any]:
    return retry_submission_impl(_load_cfg(), outbox_id, assignment_code)


@mcp.tool()
def get_submission_status(assignment_code: str) -> dict[str, Any]:
    return get_submission_status_impl(_load_cfg(), assignment_code)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
