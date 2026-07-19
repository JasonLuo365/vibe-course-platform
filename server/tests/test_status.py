from datetime import timedelta

from app.utils import utcnow
from tests.test_submissions_upload import _setup, _upload


def test_status_flow(client):
    token, code = _setup(client)
    h = {"Authorization": f"Bearer {token}"}
    r = client.get(f"/api/submissions/status?assignment_code={code}", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "none"
    _upload(client, token, code)
    r = client.get(f"/api/submissions/status?assignment_code={code}", headers=h)
    body = r.json()
    assert body["status"] == "queued"
    assert body["assignment_code"] == code
    assert body["submission_id"] > 0 and body["size_bytes"] > 0
    assert body["submitted_at"]
    assert client.get("/api/submissions/status?assignment_code=NOPE1234",
                      headers=h).status_code == 404


def test_status_cross_course_returns_404(client):
    token1, _ = _setup(client)
    cid2 = client.post("/courses", json={"name": "C2", "term": ""}).json()["id"]
    code2 = client.post(f"/courses/{cid2}/assignments", json={
        "title": "A2", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (utcnow() - timedelta(days=1)).isoformat(),
        "deadline": (utcnow() + timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    r = client.get(f"/api/submissions/status?assignment_code={code2}",
                   headers={"Authorization": f"Bearer {token1}"})
    assert r.status_code == 404
