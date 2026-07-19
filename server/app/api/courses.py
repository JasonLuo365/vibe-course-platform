from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_teacher
from ..errors import ApiError
from ..security import hash_token, new_submit_token
from ..services.roster import import_roster

router = APIRouter()


class CourseIn(BaseModel):
    name: str
    term: str = ""


class RosterIn(BaseModel):
    csv: str


@router.post("/courses")
def create_course(body: CourseIn, db: Session = Depends(get_db),
                  t: models.Teacher = Depends(get_teacher)):
    c = models.Course(name=body.name, term=body.term)
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name, "term": c.term}


@router.post("/courses/{course_id}/roster")
def roster(course_id: int, body: RosterIn, db: Session = Depends(get_db),
           t: models.Teacher = Depends(get_teacher)):
    if not db.get(models.Course, course_id):
        raise ApiError(404, "NOT_FOUND", "课程不存在")
    return import_roster(db, course_id, body.csv)


@router.post("/students/{student_id}/reset-token")
def reset_token(student_id: int, db: Session = Depends(get_db),
                t: models.Teacher = Depends(get_teacher)):
    s = db.get(models.Student, student_id)
    if not s:
        raise ApiError(404, "NOT_FOUND", "学生不存在")
    token = new_submit_token()
    s.submit_token_hash = hash_token(token)
    db.commit()
    return {"student_id": student_id, "token": token}

