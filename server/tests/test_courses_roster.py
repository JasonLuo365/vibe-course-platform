from app.db import SessionLocal
from app import models
from app.security import hash_token
from tests.test_auth import _mk_teacher


def _login(client):
    _mk_teacher()
    client.post("/login", json={"username": "admin", "password": "pw123456"})


def test_roster_import_and_tokens(client):
    _login(client)
    r = client.post("/courses", json={"name": "VC101", "term": "2026秋"})
    cid = r.json()["id"]
    csv_text = "学号,姓名,小组\n2024001,张三,第1组\n2024002,李四,第1组\n2024003,王五,第2组\n"
    r = client.post(f"/courses/{cid}/roster", json={"csv": csv_text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_students"] == 3
    assert "2024001" in body["tokens_csv"] and "vs_" in body["tokens_csv"]
    db = SessionLocal()
    students = db.query(models.Student).all()
    assert len(students) == 3
    assert db.query(models.Group).count() == 2
    # 明文不出现在库中
    assert all(len(s.submit_token_hash) == 64 for s in students)
    # 用导出的 token 能认证
    token_line = [l for l in body["tokens_csv"].splitlines() if l.startswith("2024001")][0]
    token = token_line.split(",")[2]
    assert db.query(models.Student).filter_by(submit_token_hash=hash_token(token)).count() == 1
    db.close()


def test_reset_token(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    client.post(f"/courses/{cid}/roster", json={"csv": "学号,姓名,小组\n1,甲,G\n"})
    db = SessionLocal()
    sid = db.query(models.Student).one().id
    old_hash = db.query(models.Student).one().submit_token_hash
    db.close()
    r = client.post(f"/students/{sid}/reset-token")
    assert r.status_code == 200 and r.json()["token"].startswith("vs_")
    db = SessionLocal()
    s = db.query(models.Student).one()
    assert s.submit_token_hash != old_hash
    db.close()


def test_roster_requires_teacher(client):
    assert client.post("/courses", json={"name": "C", "term": ""}).status_code == 401

