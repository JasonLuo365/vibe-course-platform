import hashlib
import io
import json
import zipfile

from app.db import SessionLocal
from app import models
from tests.test_courses_roster import _login


def _setup(client, code=None):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    body = client.post(f"/courses/{cid}/roster",
                       json={"csv": "学号,姓名,小组\n1,甲,G\n"}).json()
    token = body["tokens_csv"].splitlines()[1].split(",")[2]
    from datetime import timedelta
    from app.utils import utcnow
    now = utcnow()
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "A", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (now - timedelta(days=1)).isoformat(),
        "deadline": (now + timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    return token, code


def _package(code, client_version="0.1.0", fmt="1"):
    files = {"sessions/a.jsonl": b"hello", "code/main.py": b"print(1)"}
    manifest = {
        "format_version": fmt, "assignment_code": code, "student_no": "1",
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
