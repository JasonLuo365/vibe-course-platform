"""Tests for vibe_submit.api HTTP client and error mapping."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from vibe_submit.api import ApiError, get_meta, get_status, upload
from vibe_submit.config import Config


@pytest.fixture
def cfg():
    return Config(
        server_url="https://example.com",
        student_no="2026001",
        submit_token="secret-token",
        source="global",
    )


@pytest.fixture
def manifest():
    return {
        "format_version": "1",
        "assignment_code": "HW01",
        "student_no": "2026001",
        "client_version": "0.1.0",
        "submitted_at": "2026-07-19T10:00:00Z",
        "files": [],
        "stats": {"sessions": 0, "files": 0, "bytes": 0},
    }


def test_get_meta_success(cfg):
    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer secret-token"
        return httpx.Response(200, json={"assignment_code": "HW01", "accepts": True})

    result = get_meta(cfg, "HW01", transport=httpx.MockTransport(handler))
    assert result["accepts"] is True


def test_upload_success(cfg, manifest, tmp_path):
    zip_path = tmp_path / "test.zip"
    zip_path.write_bytes(b"zipdata")

    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer secret-token"
        return httpx.Response(
            201,
            json={"submission_id": "sub-1", "attempt_no": 1},
        )

    result = upload(cfg, zip_path, manifest, force=False, transport=httpx.MockTransport(handler))
    assert result["submission_id"] == "sub-1"


def test_upload_includes_force_field(cfg, manifest, tmp_path):
    zip_path = tmp_path / "test.zip"
    zip_path.write_bytes(b"zipdata")
    seen: dict = {}

    def handler(request: httpx.Request):
        seen["content_type"] = request.headers.get("content-type", "")
        seen["body"] = request.content
        return httpx.Response(201, json={"submission_id": "sub-1"})

    upload(cfg, zip_path, manifest, force=True, transport=httpx.MockTransport(handler))
    body = seen["body"]
    assert b'name="force"' in body
    assert b"true" in body
    assert b'name="manifest"' in body
    assert b'name="file"' in body


@pytest.mark.parametrize(
    "status,error_code",
    [
        (401, "UNAUTHORIZED"),
        (404, "NOT_FOUND"),
        (409, "DUPLICATE_SUBMISSION"),
        (422, "VALIDATION_ERROR"),
        (426, "VERSION_REQUIRED"),
    ],
)
def test_error_statuses_raise_api_error(cfg, status, error_code):
    payload = {"error": {"code": error_code, "message": "boom"}}

    def handler(request: httpx.Request):
        return httpx.Response(status, json=payload)

    with pytest.raises(ApiError) as exc_info:
        get_meta(cfg, "HW01", transport=httpx.MockTransport(handler))
    err = exc_info.value
    assert err.status == status
    assert err.code == error_code
    assert err.message == "boom"
    assert err.payload == payload


def test_network_error_maps_to_api_error(cfg):
    def handler(request: httpx.Request):
        raise httpx.ConnectError("offline")

    with pytest.raises(ApiError) as exc_info:
        get_meta(cfg, "HW01", transport=httpx.MockTransport(handler))
    err = exc_info.value
    assert err.status == 0
    assert err.code == "NETWORK"
    assert "offline" in err.message


def test_get_status_success(cfg):
    def handler(request: httpx.Request):
        assert str(request.url).endswith("/api/assignments/HW01/submissions/status")
        return httpx.Response(200, json={"status": "graded"})

    result = get_status(cfg, "HW01", transport=httpx.MockTransport(handler))
    assert result["status"] == "graded"


def test_upload_non_2xx_raises_api_error(cfg, manifest, tmp_path):
    zip_path = tmp_path / "test.zip"
    zip_path.write_bytes(b"zipdata")

    def handler(request: httpx.Request):
        return httpx.Response(500, text="server exploded")

    with pytest.raises(ApiError) as exc_info:
        upload(cfg, zip_path, manifest, transport=httpx.MockTransport(handler))
    assert exc_info.value.status == 500
