"""TDD tests for Task 2: submission detail page, override, and stale hook."""
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
            "rubric": [
                {"name": "需求理解", "weight": 30, "description": ""},
                {"name": "实现质量", "weight": 40, "description": ""},
                {"name": "迭代能力", "weight": 30, "description": ""},
            ],
            "opens_at": (now - timedelta(days=1)).isoformat(),
            "deadline": (now + timedelta(days=1)).isoformat(),
            "max_package_mb": 50,
        },
    ).json()["code"]
    return cid, tokens, code


def _package(code, student_no, session_text="Implement a todo list"):
    files = {
        "sessions/sess-abc.jsonl": json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": session_text}],
                    "timestamp": "2026-07-19T10:01:00+08:00",
                },
            },
            ensure_ascii=False,
        ).encode()
        + b"\n"
        + json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "I'll create a FastAPI app."}],
                    "timestamp": "2026-07-19T10:02:00+08:00",
                },
            },
            ensure_ascii=False,
        ).encode()
        + b"\n",
        "code/main.py": b"print(1)",
        "screenshots/sc.png": b"fake-image-data",
    }
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


def _upload(client, token, code, student_no, force=None, session_text="Implement a todo list"):
    manifest, blob = _package(code, student_no, session_text)
    data = {"manifest": json.dumps(manifest, ensure_ascii=False)}
    if force:
        data["force"] = "true"
    return client.post(
        "/api/submissions",
        headers={"Authorization": f"Bearer {token}"},
        data=data,
        files={"file": ("p.zip", blob, "application/zip")},
    )


class TestDetailPage:
    def test_detail_redirects_when_unauthenticated(self, client):
        r = client.get("/submissions/1", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]

    def test_detail_404_for_missing_submission(self, client):
        _login(client)
        r = client.get("/submissions/999")
        assert r.status_code == 404

    def test_detail_shows_grade_dimensions_quote_and_conversation(self, client, settings):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        s1 = db.query(models.Student).order_by(models.Student.student_no).first()
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

        db = SessionLocal()
        sub = db.query(models.Submission).filter_by(assignment_id=assignment.id, student_id=s1.id).one()
        sid = sub.id
        db.close()

        r = client.get(f"/submissions/{sid}")
        assert r.status_code == 200
        text = r.text
        assert "B" in text
        assert "需求理解" in text
        assert "Implement a todo list" in text
        assert "I'll create a FastAPI app." in text
        assert "main.py" in text
        assert "sc.png" in text


class TestOverride:
    def test_override_post_updates_final_grade_on_board(self, client, settings):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        s1 = db.query(models.Student).order_by(models.Student.student_no).first()
        from app.security import hash_token, new_submit_token
        token = new_submit_token()
        s1.submit_token_hash = hash_token(token)
        db.commit()
        db.close()

        assert _upload(client, token, assignment.code, s1.student_no).status_code == 201

        provider = FakeLLMProvider(responses=[_valid_individual_json()])
        db = SessionLocal()
        run_worker_once(db, provider, settings)
        eval_id = db.query(models.Evaluation).one().id
        sid = db.query(models.Submission).one().id
        db.close()

        r = client.post(
            f"/evaluations/{eval_id}/override",
            data={"final_grade": "C", "comment": "needs work"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert f"/submissions/{sid}" in r.headers["location"]

        r = client.get(f"/assignments/{assignment.id}/board")
        assert r.status_code == 200
        text = r.text
        assert "AI: B" in text
        assert "最终: C" in text


class TestStaleHook:
    def test_reupload_marks_override_stale(self, client, settings):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        s1 = db.query(models.Student).order_by(models.Student.student_no).first()
        from app.security import hash_token, new_submit_token
        token = new_submit_token()
        s1.submit_token_hash = hash_token(token)
        db.commit()
        db.close()

        assert _upload(client, token, assignment.code, s1.student_no).status_code == 201

        provider = FakeLLMProvider(responses=[_valid_individual_json()])
        db = SessionLocal()
        run_worker_once(db, provider, settings)
        eval_id = db.query(models.Evaluation).one().id
        db.close()

        client.post(f"/evaluations/{eval_id}/override", data={"final_grade": "A", "comment": "ok"})

        # Re-upload with force; stale hook should mark the override stale before commit.
        r = _upload(client, token, assignment.code, s1.student_no, force="true")
        assert r.status_code == 201

        db = SessionLocal()
        override = db.query(models.GradeOverride).one()
        assert override.stale is True
        sid = db.query(models.Submission).one().id
        db.close()

        r = client.get(f"/assignments/{assignment.id}/board")
        assert r.status_code == 200
        assert "基于旧提交" in r.text
        assert f"/submissions/{sid}" in r.text


class TestGroupOverride:
    def test_group_override_creates_row_and_redirects(self, client):
        _setup_course_and_assignment(client)
        db = SessionLocal()
        assignment = db.query(models.Assignment).one()
        g1 = db.query(models.Group).filter_by(name="G1").one()
        db.add(
            models.GroupEvaluation(
                assignment_id=assignment.id,
                group_id=g1.id,
                grade="B",
                rationale="ok",
                contribution_json={},
                evidence_json=[],
            )
        )
        db.commit()
        geval = db.query(models.GroupEvaluation).one()
        db.close()

        r = client.post(
            f"/group-evaluations/{geval.id}/override",
            data={"final_grade": "A", "comment": "great"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert f"/assignments/{assignment.id}/board" in r.headers["location"]

        db = SessionLocal()
        override = db.query(models.GradeOverride).one()
        assert override.target_type == "group"
        assert override.target_id == f"{assignment.id}:{g1.id}"
        assert override.final_grade == "A"
        assert override.comment == "great"
        assert override.stale is False
        db.close()
