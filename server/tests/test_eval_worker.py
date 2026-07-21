import hashlib
import io
import json
import zipfile
from datetime import timedelta

import pytest

from app import models
from app.db import SessionLocal
from app.eval.worker import claim_next_job, run_worker_once
from app.utils import utcnow
from tests.test_courses_roster import _login
from tests.test_eval_pipeline import FakeLLMProvider, _valid_individual_json


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


class TestClaimNextJob:
    def test_claims_queued_job_first(self, client, settings):
        _setup_with_students(client, "学号,姓名,小组\n1,甲,G\n")
        db = SessionLocal()
        job = models.EvalJob(assignment_id=1, kind="individual", target_id=1, status="queued")
        db.add(job)
        db.commit()

        claimed = claim_next_job(db)
        assert claimed is not None
        assert claimed.id == job.id
        db.close()


class TestRunWorkerOnce:
    def test_evaluates_upload_and_marks_done(self, client, settings):
        # Two-member group, but only one student submits -> individual eval, no group eval.
        tokens, code = _setup_with_students(client, "学号,姓名,小组\n1,甲,G\n2,乙,G\n")
        r = _upload(client, tokens["1"], code, "1")
        assert r.status_code == 201

        provider = FakeLLMProvider(responses=[_valid_individual_json()])
        db = SessionLocal()
        processed = run_worker_once(db, provider, settings)
        assert processed == 1

        att = db.query(models.SubmissionAttempt).one()
        sub = db.query(models.Submission).one()
        job = db.query(models.EvalJob).one()
        ev = db.query(models.Evaluation).one()

        assert att.status == "evaluated"
        assert sub.status == "evaluated"
        assert job.status == "done"
        assert ev.grade == "B"
        assert ev.model == settings.llm_model
        assert ev.prompt_version == "v3"
        assert db.query(models.GroupEvaluation).count() == 0
        db.close()

    def test_group_eval_failure_isolated(self, client, settings):
        tokens, code = _setup_with_students(client, "学号,姓名,小组\n1,甲,G\n2,乙,G\n")
        assert _upload(client, tokens["1"], code, "1").status_code == 201
        assert _upload(client, tokens["2"], code, "2").status_code == 201

        # Two individual responses; the third LLM call (group eval) exhausts the queue
        # and raises, which must not affect the individual eval success or job state.
        provider = FakeLLMProvider(
            responses=[_valid_individual_json(), _valid_individual_json()]
        )
        db = SessionLocal()
        processed = run_worker_once(db, provider, settings)
        assert processed == 1
        processed = run_worker_once(db, provider, settings)
        assert processed == 1

        attempts = db.query(models.SubmissionAttempt).order_by(models.SubmissionAttempt.id).all()
        subs = db.query(models.Submission).order_by(models.Submission.id).all()
        jobs = db.query(models.EvalJob).order_by(models.EvalJob.id).all()
        assert all(a.status == "evaluated" for a in attempts)
        assert all(s.status == "evaluated" for s in subs)
        assert all(j.status == "done" for j in jobs)
        assert db.query(models.GroupEvaluation).count() == 0
        db.close()

    def test_retries_exhausted_marks_failed(self, client, settings):
        tokens, code = _setup_with_students(client, "学号,姓名,小组\n1,甲,G\n")
        r = _upload(client, tokens["1"], code, "1")
        assert r.status_code == 201

        def _boom(*_a, **_kw):
            raise RuntimeError("boom")

        provider = FakeLLMProvider(callable=_boom)
        db = SessionLocal()

        for i in range(3):
            processed = run_worker_once(db, provider, settings)
            assert processed == 0

            job = db.query(models.EvalJob).one()
            if i < 2:
                assert job.status == "running"
                assert job.attempts == i + 1
                # Immediately after failure the job is NOT reclaimable.
                assert claim_next_job(db) is None
                # Backdate updated_at so backoff (attempts * 60s) has elapsed.
                job.updated_at = utcnow() - timedelta(seconds=job.attempts * 60)
                db.commit()
                assert claim_next_job(db) is not None
            else:
                assert job.attempts == 3
                assert job.status == "failed"

        att = db.query(models.SubmissionAttempt).one()
        sub = db.query(models.Submission).one()
        job = db.query(models.EvalJob).one()

        assert job.attempts == 3
        assert job.status == "failed"
        assert att.status == "failed"
        assert sub.status == "failed"
        assert "boom" in (job.last_error or "")
        db.close()
