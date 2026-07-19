import hashlib
import io
import json
import os
import tempfile
import zipfile
from datetime import timedelta

from app.db import SessionLocal
from app import models
from app.errors import ApiError
from app.utils import utcnow
from tests.test_courses_roster import _login


def _setup(client, code=None):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    body = client.post(f"/courses/{cid}/roster",
                       json={"csv": "学号,姓名,小组\n1,甲,G\n"}).json()
    token = body["tokens_csv"].splitlines()[1].split(",")[2]
    now = utcnow()
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "A", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (now - timedelta(days=1)).isoformat(),
        "deadline": (now + timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    return token, code


def _package(code, client_version="0.1.0", fmt="1", student_no="1"):
    files = {"sessions/a.jsonl": b"hello", "code/main.py": b"print(1)"}
    manifest = {
        "format_version": fmt, "assignment_code": code, "student_no": student_no,
        "client_version": client_version, "submitted_at": "2026-07-19T08:00:00Z",
        "files": [{"path": n, "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for n, b in files.items():
            z.writestr(n, b)
    return manifest, buf.getvalue()


def _upload(client, token, code, force=None, **kw):
    manifest, blob = _package(code, **kw)
    data = {"manifest": json.dumps(manifest, ensure_ascii=False)}
    if force:
        data["force"] = "true"
    return client.post("/api/submissions",
                       headers={"Authorization": f"Bearer {token}"},
                       data=data, files={"file": ("p.zip", blob, "application/zip")})


def test_upload_ok_then_409_then_force(client):
    token, code = _setup(client)
    r = _upload(client, token, code)
    assert r.status_code == 201, r.text
    assert r.json()["attempt_no"] == 1
    r = _upload(client, token, code)
    assert r.status_code == 409
    r = _upload(client, token, code, force="true")
    assert r.status_code == 201 and r.json()["attempt_no"] == 2
    db = SessionLocal()
    assert db.query(models.SubmissionAttempt).count() == 2
    assert db.query(models.EvalJob).filter_by(kind="individual", status="queued").count() == 2
    sub = db.query(models.Submission).one()
    assert sub.status == "queued"
    db.close()


def test_upload_rejections(client):
    token, code = _setup(client)
    assert client.post("/api/submissions", data={}, files={}).status_code == 401
    r = _upload(client, token, code, client_version="0.0.1")
    assert r.status_code == 426 and r.json()["error"]["code"] == "CLIENT_OUTDATED"
    r = _upload(client, token, code, fmt="99")
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_MANIFEST_VERSION"
    r = client.post("/api/submissions", headers={"Authorization": f"Bearer {token}"},
                    data={"manifest": json.dumps({"format_version": "1", "assignment_code": "NOPE1234",
                                                  "student_no": "1", "client_version": "0.1.0",
                                                  "submitted_at": "x", "files": []})},
                    files={"file": ("p.zip", _package(code)[1], "application/zip")})
    assert r.status_code == 404


def test_upload_short_client_version_ok(client):
    token, code = _setup(client)
    r = _upload(client, token, code, client_version="0.1")
    assert r.status_code == 201, r.text


def test_upload_wrong_course(client):
    token1, _ = _setup(client)
    cid2 = client.post("/courses", json={"name": "C2", "term": ""}).json()["id"]
    code2 = client.post(f"/courses/{cid2}/assignments", json={
        "title": "A2", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (utcnow() - timedelta(days=1)).isoformat(),
        "deadline": (utcnow() + timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    r = _upload(client, token1, code2)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "WRONG_COURSE"


def test_upload_deadline_passed(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    body = client.post(f"/courses/{cid}/roster",
                       json={"csv": "学号,姓名,小组\n1,甲,G\n"}).json()
    token = body["tokens_csv"].splitlines()[1].split(",")[2]
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "A", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (utcnow() - timedelta(days=2)).isoformat(),
        "deadline": (utcnow() - timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    r = _upload(client, token, code)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "DEADLINE_PASSED"


def test_upload_not_open(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    body = client.post(f"/courses/{cid}/roster",
                       json={"csv": "学号,姓名,小组\n1,甲,G\n"}).json()
    token = body["tokens_csv"].splitlines()[1].split(",")[2]
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "A", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (utcnow() + timedelta(days=1)).isoformat(),
        "deadline": (utcnow() + timedelta(days=2)).isoformat(), "max_package_mb": 50}).json()["code"]
    r = _upload(client, token, code)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "NOT_OPEN"


def test_upload_student_mismatch(client):
    token, code = _setup(client)
    r = _upload(client, token, code, student_no="999")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "STUDENT_MISMATCH"


def test_upload_tempfile_failure_guard(client, monkeypatch):
    token, code = _setup(client)
    def _boom(*args, **kwargs):
        raise ApiError(422, "TMP_FAIL", "临时文件创建失败")
    monkeypatch.setattr(tempfile, "NamedTemporaryFile", _boom)
    r = _upload(client, token, code)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "TMP_FAIL"


def test_upload_package_too_large(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    body = client.post(f"/courses/{cid}/roster",
                       json={"csv": "学号,姓名,小组\n1,甲,G\n"}).json()
    token = body["tokens_csv"].splitlines()[1].split(",")[2]
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "A", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (utcnow() - timedelta(days=1)).isoformat(),
        "deadline": (utcnow() + timedelta(days=1)).isoformat(), "max_package_mb": 1}).json()["code"]
    big = os.urandom(2 * 1024 * 1024)
    files = {"data.bin": big}
    manifest = {
        "format_version": "1", "assignment_code": code, "student_no": "1",
        "client_version": "0.1.0", "submitted_at": "2026-07-19T08:00:00Z",
        "files": [{"path": n, "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for n, b in files.items():
            z.writestr(n, b)
    r = client.post("/api/submissions",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"manifest": json.dumps(manifest, ensure_ascii=False)},
                    files={"file": ("p.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "PACKAGE_TOO_LARGE"


def test_upload_zip_rejected(client):
    token, code = _setup(client)
    manifest = {
        "format_version": "1", "assignment_code": code, "student_no": "1",
        "client_version": "0.1.0", "submitted_at": "2026-07-19T08:00:00Z", "files": [],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        z.writestr("../evil.txt", b"x")
    r = client.post("/api/submissions",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"manifest": json.dumps(manifest, ensure_ascii=False)},
                    files={"file": ("p.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ZIP_REJECTED"


def test_upload_bad_manifest(client):
    token, code = _setup(client)
    r = client.post("/api/submissions",
                    headers={"Authorization": f"Bearer {token}"},
                    data={"manifest": "{not json"},
                    files={"file": ("p.zip", b"", "application/zip")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "BAD_MANIFEST"

