"""HTTP API client for the submission server."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .config import Config
from .errors import ApiError

DEFAULT_TIMEOUT = 60.0


def get_meta(cfg: Config, assignment_code: str, transport=None) -> dict:
    """Fetch assignment metadata from the server."""
    url = f"{cfg.server_url.rstrip('/')}/api/assignments/{assignment_code}/meta"
    return _request("GET", url, cfg, transport=transport)


def upload(
    cfg: Config,
    zip_path: Path,
    manifest: dict,
    force: bool = False,
    transport=None,
) -> dict:
    """Upload a submission package as multipart form data.

    The multipart body contains ``manifest`` (JSON), ``file`` (zip), and
    ``force`` (boolean string).  HTTPS certificate verification is always
    enabled and cannot be disabled.
    """
    assignment_code = manifest["assignment_code"]
    url = f"{cfg.server_url.rstrip('/')}/api/submissions"

    headers = {"Authorization": f"Bearer {cfg.submit_token}"}
    data = {"force": "true" if force else "false"}
    files = {
        "manifest": (
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            "application/json",
        ),
        "file": (
            Path(zip_path).name,
            Path(zip_path).read_bytes(),
            "application/zip",
        ),
    }

    return _request(
        "POST",
        url,
        cfg,
        transport=transport,
        data=data,
        files=files,
        extra_headers=headers,
    )


def get_status(cfg: Config, assignment_code: str, transport=None) -> dict:
    """Fetch the latest submission status for an assignment."""
    url = (
        f"{cfg.server_url.rstrip('/')}/"
        f"api/submissions/status?assignment_code={assignment_code}"
    )
    return _request("GET", url, cfg, transport=transport)


def _request(
    method: str,
    url: str,
    cfg: Config,
    transport=None,
    **kwargs,
) -> dict:
    extra_headers = kwargs.pop("extra_headers", {})
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {cfg.submit_token}",
        **extra_headers,
    }

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, transport=transport) as client:
            response = client.request(method, url, headers=headers, **kwargs)
    except httpx.RequestError as exc:
        raise ApiError(0, "NETWORK", str(exc), None) from exc

    return _handle_response(response)


def _handle_response(response: httpx.Response) -> dict:
    status = response.status_code
    try:
        payload = response.json()
    except Exception:
        payload = None

    if 200 <= status < 300:
        return payload if isinstance(payload, dict) else {}

    if status in (401, 404, 409, 422, 426):
        error = (payload or {}).get("error", {})
        code = error.get("code", "UNKNOWN")
        message = error.get("message", response.text)
        raise ApiError(status, code, message, payload)

    raise ApiError(status, "HTTP_ERROR", response.text, payload)
