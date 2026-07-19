import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from . import models
from .config import Settings
from .db import get_db
from .errors import ApiError
from .security import hash_token


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


def get_student(request: Request, db: Session = Depends(get_db)) -> models.Student:
    rate_limit(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少 Bearer token")
    s = db.query(models.Student).filter_by(submit_token_hash=hash_token(auth[7:])).first()
    if not s:
        raise ApiError(401, "UNAUTHORIZED", "token 无效或已重置")
    return s


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    limit = request.app.state.settings.rate_limit_per_minute
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    dq = _hits[ip]
    while dq and dq[0] < now - 60:
        dq.popleft()
    if len(dq) >= limit:
        raise ApiError(429, "RATE_LIMITED", "请求过于频繁，请稍后重试")
    dq.append(now)
