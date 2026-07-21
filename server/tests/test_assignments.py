from datetime import timedelta, timezone

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


def test_assignment_evaluation_config_can_be_reserved_and_updated(client):
    _login(client)
    cid = _course(client)
    now = utcnow()
    created = client.post(f"/courses/{cid}/assignments", json={
        "title": "实验占位", "description": "", "rubric": RUBRIC,
        "evaluation_profile": "teacher-01-experiment-01",
        "evaluation_instructions": "【占位】等待教师提供实验题目与参考答案。",
        "opens_at": (now - timedelta(days=1)).isoformat(),
        "deadline": (now + timedelta(days=7)).isoformat(), "max_package_mb": 50,
    })
    assert created.status_code == 200, created.text
    assignment_id = created.json()["id"]

    updated = client.put(f"/assignments/{assignment_id}/evaluation-config", json={
        "evaluation_profile": "teacher-01-experiment-01",
        "evaluation_instructions": "【占位】已收集题目，等待编写专属提示词。",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["evaluation_profile"] == "teacher-01-experiment-01"
    assert "等待编写" in updated.json()["evaluation_instructions"]


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


def test_create_assignment_aware_datetime_converted_to_utc(client):
    _login(client)
    cid = _course(client)
    now = utcnow()
    tz = timezone(timedelta(hours=8))
    opens_at = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0).replace(tzinfo=tz)
    deadline = (now + timedelta(days=7)).replace(hour=8, minute=0, second=0, microsecond=0).replace(tzinfo=tz)
    r = client.post(f"/courses/{cid}/assignments", json={
        "title": "TZ", "description": "", "rubric": RUBRIC,
        "opens_at": opens_at.isoformat(),
        "deadline": deadline.isoformat(), "max_package_mb": 50})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    m = client.get(f"/api/assignments/{code}/meta").json()
    assert m["opens_at"] == opens_at.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
    assert m["deadline"] == deadline.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
