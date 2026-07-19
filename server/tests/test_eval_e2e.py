import hashlib
import io
import json
import zipfile
from datetime import timedelta

from app import models
from app.db import SessionLocal
from app.eval.worker import run_worker_once
from app.utils import utcnow
from tests.test_courses_roster import _login
from tests.test_eval_pipeline import FakeLLMProvider, _valid_group_json, _valid_individual_json


def _setup_with_students(client, csv_text):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
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
    return tokens, code


def _rollout_bytes():
    lines = [
        {
            "type": "session_meta",
            "payload": {"id": "sess-abc", "timestamp": "2026-07-19T10:00:00+08:00"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": "Implement a todo list",
                "timestamp": "2026-07-19T10:01:00+08:00",
            },
        },
    ]
    return "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines).encode("utf-8")


def _package(code, student_no):
    files = {"sessions/sess-abc.jsonl": _rollout_bytes(), "code/main.py": b"print(1)"}
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


class TestGroupEvaluationFlow:
    def test_group_evaluation_generation_increments_on_reupload(self, client, settings):
        tokens, code = _setup_with_students(
            client, "学号,姓名,小组\n1,甲,G\n2,乙,G\n"
        )
        assert _upload(client, tokens["1"], code, "1").status_code == 201
        assert _upload(client, tokens["2"], code, "2").status_code == 201

        # Order: member1 individual, member2 individual, group gen1,
        # then force-reupload member1 -> individual, group gen2.
        provider = FakeLLMProvider(
            responses=[
                _valid_individual_json(),
                _valid_individual_json(),
                _valid_group_json(),
                _valid_individual_json(),
                _valid_group_json(),
            ]
        )
        db = SessionLocal()

        # Evaluate both members; second evaluation triggers group eval.
        assert run_worker_once(db, provider, settings) == 1
        assert run_worker_once(db, provider, settings) == 1

        ges = db.query(models.GroupEvaluation).order_by(models.GroupEvaluation.generation).all()
        assert len(ges) == 1
        assert ges[0].generation == 1

        # Force re-upload member 1.
        r = _upload(client, tokens["1"], code, "1", force="true")
        assert r.status_code == 201 and r.json()["attempt_no"] == 2

        assert run_worker_once(db, provider, settings) == 1
        ges = db.query(models.GroupEvaluation).order_by(models.GroupEvaluation.generation).all()
        assert len(ges) == 2
        assert [g.generation for g in ges] == [1, 2]
        db.close()


class TestDeadlineSweep:
    def test_deadline_sweep_evaluates_incomplete_group_with_missing_note(self, client, settings):
        tokens, code = _setup_with_students(
            client, "学号,姓名,小组\n1,甲,G\n2,乙,G\n"
        )
        assert _upload(client, tokens["1"], code, "1").status_code == 201

        provider = FakeLLMProvider(
            responses=[_valid_individual_json(), _valid_group_json()]
        )
        db = SessionLocal()

        # Evaluate the only submitted member; group not ready.
        assert run_worker_once(db, provider, settings) == 1
        assert db.query(models.GroupEvaluation).count() == 0

        # Move deadline to the past.
        assignment = db.query(models.Assignment).filter_by(code=code).one()
        assignment.deadline = utcnow() - timedelta(days=1)
        db.commit()

        # Sweep should create a group evaluation noting the missing member.
        assert run_worker_once(db, provider, settings) == 1
        ge = db.query(models.GroupEvaluation).one()
        assert ge.generation == 1
        assert ge.rationale.startswith("缺员:")
        assert "2" in ge.rationale
        assert ge.contribution_json["missing"] == ["2"]
        db.close()

