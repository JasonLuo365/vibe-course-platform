from app.db import SessionLocal
from app import models
from tests.test_auth import _mk_teacher


def _login(client):
    _mk_teacher()
    assert client.post("/login", json={"username": "admin", "password": "pw123456"}).status_code == 200


def test_students_and_analytics_pages_are_protected_and_render(client):
    assert client.get("/students", follow_redirects=False).status_code == 302
    _login(client)
    course_id = client.post("/courses", json={"name": "VC101", "term": "2026"}).json()["id"]
    client.post(f"/courses/{course_id}/roster", json={"csv": "学号,姓名,小组\n20260001,张三,G1\n"})
    students = client.get("/students")
    assert students.status_code == 200
    assert "20260001" in students.text and "张三" in students.text
    analytics = client.get("/analytics")
    assert analytics.status_code == 200
    assert "数据分析" in analytics.text


def test_students_page_offers_token_reset(client):
    _login(client)
    course_id = client.post("/courses", json={"name": "VC101", "term": "2026"}).json()["id"]
    client.post(f"/courses/{course_id}/roster", json={"csv": "学号,姓名,小组\n20260001,张三,G1\n"})
    db = SessionLocal()
    student_id = db.query(models.Student).one().id
    db.close()
    response = client.post(f"/students/{student_id}/reset-token")
    assert response.status_code == 200
    assert response.json()["token"].startswith("vs_")
