from app import models
from app.db import SessionLocal
from app.security import hash_password


def _mk_teacher(username="admin", password="pw123456"):
    db = SessionLocal()
    t = models.Teacher(username=username, password_hash=hash_password(password),
                       display_name="Admin")
    db.add(t)
    db.commit()
    db.close()


def test_login_logout_and_protected(client):
    _mk_teacher()
    assert client.get("/api/whoami").status_code == 401
    r = client.post("/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    r = client.post("/login", json={"username": "admin", "password": "pw123456"})
    assert r.status_code == 200
    r = client.get("/api/whoami")
    assert r.status_code == 200 and r.json()["username"] == "admin"
    client.post("/logout")
    assert client.get("/api/whoami").status_code == 401

