from datetime import timedelta

from app.utils import utcnow
from tests.test_courses_roster import _login


def _course(client):
    return client.post("/courses", json={"name": "C", "term": ""}).json()["id"]


RUBRIC = [{"name": "prompt质量", "weight": 30, "description": "d"},
          {"name": "迭代策略", "weight": 25, "description": "d"},
          {"name": "调试与问题解决", "weight": 20, "description": "d"},
          {"name": "完成度", "weight": 15, "description": "d"},
          {"name": "代码质量", "weight": 10, "description": "d"}]


def test_create_assignment_and_meta(client):
    _login(client)
    cid = _course(client)
    now = utcnow()
    r = client.post(f"/courses/{cid}/assignments", json={
        "title": "作业3", "description": "做一个网页", "rubric": RUBRIC,
        "opens_at": (now - timedelta(days=1)).isoformat(),
        "deadline": (now + timedelta(days=7)).isoformat(), "max_package_mb": 50})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert len(code) == 8
    r = client.get(f"/api/assignments/{code}/meta")
    assert r.status_code == 200
    m = r.json()
    assert m["title"] == "作业3" and m["accepts"] is True and m["reason"] == ""
    assert m["min_client_version"] == "0.1.0"
    assert m["supported_manifest_versions"] == ["1"]
    assert m["max_package_mb"] == 50


def test_rubric_weight_sum(client):
    _login(client)
    cid = _course(client)
    now = utcnow().isoformat()
    r = client.post(f"/courses/{cid}/assignments", json={
        "title": "X", "description": "", "rubric": [{"name": "a", "weight": 50, "description": ""}],
        "opens_at": now, "deadline": now, "max_package_mb": 50})
    assert r.status_code == 422


def test_meta_after_deadline(client):
    _login(client)
    cid = _course(client)
    now = utcnow()
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "X", "description": "", "rubric": RUBRIC,
        "opens_at": (now - timedelta(days=9)).isoformat(),
        "deadline": (now - timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    m = client.get(f"/api/assignments/{code}/meta").json()
    assert m["accepts"] is False and "截止" in m["reason"]
