import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from . import models
from .config import Settings
from .db import get_db
from .errors import ApiError
from .security import verify_password
from .web import PageAuthRequired


def get_teacher(request: Request, db: Session = Depends(get_db)) -> models.Teacher:
    tid = request.session.get("teacher_id")
    if not tid:
        raise ApiError(401, "UNAUTHORIZED", "教师未登录")
    t = db.get(models.Teacher, tid)
    if not t:
        raise ApiError(401, "UNAUTHORIZED", "教师不存在")
    return t


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


_student_basic = HTTPBasic(auto_error=False)


def get_student(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(_student_basic),
    db: Session = Depends(get_db),
) -> models.Student:
    rate_limit(request)
    if credentials is None:
        raise ApiError(401, "UNAUTHORIZED", "需要学号和密码")
    students = db.query(models.Student).filter_by(student_no=credentials.username).all()
    if len(students) != 1 or not students[0].password_hash or not verify_password(
        credentials.password, students[0].password_hash
    ):
        raise ApiError(401, "UNAUTHORIZED", "学号或密码错误")
    s = students[0]
    return s


def get_student_page(request: Request, db: Session = Depends(get_db)) -> models.Student:
    if request.session.get("role") != "student":
        raise PageAuthRequired(next_url=str(request.url.path))
    student_id = request.session.get("student_id")
    student = db.get(models.Student, student_id) if student_id else None
    session_version = request.session.get("student_session_version")
    if not student or session_version != student.web_session_version:
        request.session.clear()
        raise PageAuthRequired(next_url=str(request.url.path))
    return student


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    limit = request.app.state.settings.rate_limit_per_minute
    ip = request.client.host if request.client else "unknown"
    # This is enabled only when the deployment binds the app to localhost and
    # its reverse proxy is trusted to set X-Forwarded-For.
    if request.app.state.settings.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            ip = forwarded.split(",", 1)[0].strip() or ip
    now = time.time()
    dq = _hits[ip]
    while dq and dq[0] < now - 60:
        dq.popleft()
    if len(dq) >= limit:
        raise ApiError(429, "RATE_LIMITED", "请求过于频繁，请稍后重试")
    dq.append(now)
