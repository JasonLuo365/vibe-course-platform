import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_settings_dep, get_teacher
from ..errors import ApiError
from ..utils import utcnow

router = APIRouter()

_ALPHABET = string.ascii_uppercase + string.digits


class RubricItem(BaseModel):
    name: str
    weight: int
    description: str = ""


class AssignmentIn(BaseModel):
    title: str
    description: str = ""
    rubric: list[RubricItem]
    opens_at: datetime
    deadline: datetime
    max_package_mb: int = 50

    @field_validator("rubric")
    @classmethod
    def weights_sum_100(cls, v):
        if not v or sum(i.weight for i in v) != 100:
            raise ValueError("rubric 权重和必须为 100")
        return v


def _as_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _new_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        if not db.query(models.Assignment).filter_by(code=code).first():
            return code


@router.post("/courses/{course_id}/assignments")
def create_assignment(course_id: int, body: AssignmentIn, db: Session = Depends(get_db),
                      t: models.Teacher = Depends(get_teacher)):
    if not db.get(models.Course, course_id):
        raise ApiError(404, "NOT_FOUND", "课程不存在")
    a = models.Assignment(
        course_id=course_id, code=_new_code(db), title=body.title,
        description=body.description,
        rubric_json=[i.model_dump() for i in body.rubric],
        opens_at=_as_naive_utc(body.opens_at),
        deadline=_as_naive_utc(body.deadline),
        max_package_mb=body.max_package_mb)
    db.add(a)
    db.commit()
    return {"id": a.id, "code": a.code}


@router.get("/api/assignments/{code}/meta")
def assignment_meta(code: str, db: Session = Depends(get_db),
                    s=Depends(get_settings_dep)):
    a = db.query(models.Assignment).filter_by(code=code).first()
    if not a:
        raise ApiError(404, "NOT_FOUND", "作业码不存在")
    now = utcnow()
    accepts, reason = True, ""
    if now < a.opens_at:
        accepts, reason = False, "作业未开放"
    elif now > a.deadline:
        accepts, reason = False, "已过截止时间"
    return {
        "title": a.title,
        "opens_at": a.opens_at.isoformat(),
        "deadline": a.deadline.isoformat(),
        "max_package_mb": a.max_package_mb,
        "accepts": accepts,
        "reason": reason,
        "min_client_version": s.min_client_version,
        "supported_manifest_versions": s.supported_manifest_versions,
    }

