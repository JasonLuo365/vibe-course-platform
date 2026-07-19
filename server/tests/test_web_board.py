"""TDD tests for Task 1: teacher page skeleton, login page, board, progress API."""
import hashlib
import io
import json
import zipfile
from datetime import timedelta

from app import models
from app.db import SessionLocal
from app.eval.worker import run_worker_once
from app.utils import utcnow
from tests.test_auth import _mk_teacher
from tests.test_eval_pipeline import FakeLLMProvider, _valid_individual_json


def _login(client):
    _mk_teacher()
    return client.post("/login", json={"username": "admin", "password": "pw123456"})


def _setup_course_and_assignment(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    csv_text = "学号,姓名,小组\n2024001,张三,G1\n2024002,李四,G1\n2024003,王五,G2\n"
    body = client.post(f"/courses/{cid}/roster", json={"csv": csv_text}).json()
    tokens = {}
    for line in body["tokens_csv"].splitlines()[1:]:
        no, _name, token = line.split(",")
        tokens[no] = token
    now = utcnow()
    code = client.post(
        f"/courses/{cid}/assignments",
        json={
            "title": "A",
            "description": "",
            "rubric": [{"name": "x", "weight": 100, "description": ""}],
            "opens_at": (now - timedelta(days=1)).isoformat(),
            "deadline": (now + timedelta(days=1)).isoformat(),
            "max_package_mb": 50,
        },
    ).json()["code"]
    return cid, tokens, code


def _package(code, student_no):
    files = {"sessions/sess-abc.jsonl": b"{}", "code/main.py": b"print(1)"}
    manifest = {
        "format_version": "1",
        "assignment_code": code,
        "student_no": student_no,
        "client_version": "0.1.0",
        "submitted_at": "2026-07-19T08:00:00Z",
        "files": [{"path": n, "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for n, b in files.items():
            z.writestr(n, b)
    return manifest, buf.getvalue()


def _upload(client, token, code, student_no, force=None):
    manifest, blob = _package(code, student_no)
    data = {"manifest": json.dumps(manifest, ensure_ascii=False)}
    if force:
        data["force"] = "true"
    return client.post(
        "/api/submissions",
        headers={"Authorization": f"Bearer {token}"},
        data=data,
        files={"file": ("p.zip", blob, "application/zip")},
    )


class TestLoginPage:
    def test_login_page_renders_form(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert "form" in r.text.lower()
        assert "username" in r.text.lower()

    def test_login_page_preserves_next_param(self, client):
        r = client.get("/login?next=/assignments/1/board")
        assert r.status_code == 200
        assert "/assignments/1/board" in r.text


class TestBoardPage:
    def test_board_redirects_when_unauthenticated(self, client):
        r = client.get("/assignments/1/board", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]
        assert "next=" in r.headers["location"]

    def test_board_404_for_missing_assignment(self, client):
        _login(client)
        r = client.get("/assignments/999/board")
        assert r.status_code == 404

    def test_board_shows_roster_cells_without_submissions(self, client):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        aid = db.query(models.Assignment).one().id
        db.close()
        r = client.get(f"/assignments/{aid}/board")
        assert r.status_code == 200
        assert "2024001" in r.text
        assert "张三" in r.text
        assert "2024002" in r.text
        assert "李四" in r.text

    def test_board_shows_grade_after_evaluation(self, client, settings):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        aid = assignment.id
        tokens = {}
        for line in client.get("/api/whoami").json():
            pass
        # Re-read tokens from DB since setup used the API.
        students = db.query(models.Student).all()
        for s in students:
            # Find token by submitting for the first student only to keep test simple.
            pass
        db.close()

        # Use the CSV-import tokens stored in DB by import_roster.
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        aid = assignment.id
        students = db.query(models.Student).order_by(models.Student.student_no).all()
        s1 = students[0]
        # Build a fake submit token from the hash stored in DB.
        token = "vs_testtoken"
        # We cannot reverse the hash, so instead create a fresh token mapping manually.
        from app.security import hash_token, new_submit_token
        token = new_submit_token()
        s1.submit_token_hash = hash_token(token)
        db.commit()
        db.close()

        assert _upload(client, token, assignment.code, s1.student_no).status_code == 201

        provider = FakeLLMProvider(responses=[_valid_individual_json()])
        db = SessionLocal()
        run_worker_once(db, provider, settings)
        db.close()

        r = client.get(f"/assignments/{aid}/board")
        assert r.status_code == 200
        assert s1.student_no in r.text
        assert "B" in r.text
        assert "AI" in r.text or "最终" in r.text

    def test_board_stale_override_falls_back_to_ai_grade(self, client, settings):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        aid = assignment.id
        s1 = db.query(models.Student).order_by(models.Student.student_no).first()
        from app.security import hash_token, new_submit_token
        token = new_submit_token()
        s1.submit_token_hash = hash_token(token)
        teacher = db.query(models.Teacher).one()
        db.commit()
        db.close()

        assert _upload(client, token, assignment.code, s1.student_no).status_code == 201
        provider = FakeLLMProvider(responses=[_valid_individual_json()])
        db = SessionLocal()
        run_worker_once(db, provider, settings)
        # AI 评为 B；教师调分为 A（未 stale）
        ov = models.GradeOverride(target_type="individual",
                                  target_id=f"{aid}:{s1.id}", final_grade="A",
                                  comment="", teacher_id=teacher.id, stale=False)
        db.add(ov)
        db.commit()
        db.close()
        r = client.get(f"/assignments/{aid}/board")
        assert "最终: A" in r.text

        # override 标记 stale 后应回退显示 AI 的 B
        db = SessionLocal()
        ov = db.query(models.GradeOverride).one()
        ov.stale = True
        db.commit()
        db.close()
        r = client.get(f"/assignments/{aid}/board")
        assert "最终: B" in r.text
        assert "最终: A" not in r.text
        assert "基于旧提交" in r.text


class TestProgressAPI:
    def test_progress_requires_teacher(self, client):
        r = client.get("/api/assignments/1/progress")
        assert r.status_code == 401

    def test_progress_json_shape(self, client):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        aid = db.query(models.Assignment).one().id
        db.close()
        r = client.get(f"/api/assignments/{aid}/progress")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"total_submissions", "evaluated", "failed", "queued"}
        assert all(isinstance(v, int) for v in body.values())
        assert body["total_submissions"] == 0
        assert body["evaluated"] == 0
        assert body["failed"] == 0
        assert body["queued"] == 0

    def test_progress_counts_after_upload(self, client, settings):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        aid = assignment.id
        s1 = db.query(models.Student).order_by(models.Student.student_no).first()
        from app.security import hash_token, new_submit_token
        token = new_submit_token()
        s1.submit_token_hash = hash_token(token)
        db.commit()
        db.close()

        assert _upload(client, token, assignment.code, s1.student_no).status_code == 201

        r = client.get(f"/api/assignments/{aid}/progress")
        assert r.status_code == 200
        body = r.json()
        assert body["total_submissions"] == 1
        assert body["queued"] == 1
        assert body["evaluated"] == 0

        provider = FakeLLMProvider(responses=[_valid_individual_json()])
        db = SessionLocal()
        run_worker_once(db, provider, settings)
        db.close()

        r = client.get(f"/api/assignments/{aid}/progress")
        assert r.status_code == 200
        body = r.json()
        assert body["total_submissions"] == 1
        assert body["evaluated"] == 1
        assert body["queued"] == 0


class TestDashboard:
    def test_root_redirects_to_login_when_unauthenticated(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/login"

    def test_dashboard_lists_course_and_assignment_links(self, client):
        _setup_course_and_assignment(client)
        r = client.get("/")
        assert r.status_code == 200
        assert "Vibe" in r.text
        assert "总览板" in r.text
        assert "/assignments/" in r.text and "/board" in r.text
