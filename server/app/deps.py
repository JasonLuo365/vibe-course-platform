from fastapi import Depends, Request
from sqlalchemy.orm import Session

from . import models
from .db import get_db
from .errors import ApiError


def get_teacher(request: Request, db: Session = Depends(get_db)) -> models.Teacher:
    tid = request.session.get("teacher_id")
    if not tid:
        raise ApiError(401, "UNAUTHORIZED", "教师未登录")
    t = db.get(models.Teacher, tid)
    if not t:
        raise ApiError(401, "UNAUTHORIZED", "教师不存在")
    return t
