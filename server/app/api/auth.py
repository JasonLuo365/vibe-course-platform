from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_student, get_teacher
from ..errors import ApiError
from ..security import verify_password

router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Teacher).filter_by(username=body.username).first()
    if not t or not verify_password(body.password, t.password_hash):
        raise ApiError(401, "UNAUTHORIZED", "用户名或密码错误")
    request.session["teacher_id"] = t.id
    return {"ok": True}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/whoami")
def whoami(t: models.Teacher = Depends(get_teacher)):
    return {"username": t.username, "display_name": t.display_name}


@router.get("/api/student/ping")
def student_ping(s: models.Student = Depends(get_student)):
    return {"student_no": s.student_no, "name": s.name}
