from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_student, get_teacher, rate_limit
from ..errors import ApiError
from ..security import hash_password, verify_password

router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str


class StudentLoginIn(BaseModel):
    student_no: str
    password: str


class StudentPasswordResetIn(BaseModel):
    student_no: str
    password: str
    password_confirm: str


def _valid_password(password: str) -> bool:
    return 8 <= len(password) <= 12


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
    return RedirectResponse(url="/login", status_code=303)


@router.post("/student/login")
def student_login(body: StudentLoginIn, request: Request, db: Session = Depends(get_db)):
    students = db.query(models.Student).filter_by(student_no=body.student_no).all()
    if len(students) != 1 or not students[0].password_hash or not verify_password(
        body.password, students[0].password_hash
    ):
        raise ApiError(401, "UNAUTHORIZED", "学号或密码错误")
    student = students[0]
    request.session.clear()
    request.session["role"] = "student"
    request.session["student_id"] = student.id
    request.session["student_session_version"] = student.web_session_version
    return {"ok": True}


@router.post("/student/password/reset")
def reset_student_password(
    body: StudentPasswordResetIn, request: Request, db: Session = Depends(get_db)
):
    rate_limit(request)
    if body.password != body.password_confirm:
        raise ApiError(422, "PASSWORD_MISMATCH", "两次输入的密码不一致")
    if not _valid_password(body.password):
        raise ApiError(422, "WEAK_PASSWORD", "密码长度须为 8 到 12 个字符")
    students = db.query(models.Student).filter_by(student_no=body.student_no).all()
    if len(students) == 1:
        student = students[0]
        student.password_hash = hash_password(body.password)
        student.web_session_version += 1
        db.commit()
    # Keep the response identical for unknown or ambiguous student numbers.
    return {"ok": True}


@router.post("/student/logout")
def student_logout(request: Request):
    return logout(request)


@router.get("/api/whoami")
def whoami(t: models.Teacher = Depends(get_teacher)):
    return {"username": t.username, "display_name": t.display_name}


@router.get("/api/student/ping")
def student_ping(s: models.Student = Depends(get_student)):
    return {"student_no": s.student_no, "name": s.name}
