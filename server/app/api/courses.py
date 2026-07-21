import secrets
import string

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_student, get_teacher, rate_limit
from ..errors import ApiError
from ..security import hash_token, new_submit_token
from ..services.roster import import_roster

router = APIRouter()


class CourseIn(BaseModel):
    name: str
    term: str = ""


class RosterIn(BaseModel):
    csv: str


class EnrollmentIn(BaseModel):
    max_group_size: int = Field(default=6, ge=2, le=20)


class LockIn(BaseModel):
    locked: bool


class RegisterIn(BaseModel):
    course_code: str
    student_no: str
    name: str

    @field_validator("course_code", "student_no", "name")
    @classmethod
    def required(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or len(value) > 100:
            raise ValueError("字段不能为空或过长")
        return value


class GroupNameIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or len(value) > 40:
            raise ValueError("组名须为 1–40 个字符")
        return value


class JoinIn(BaseModel):
    join_code: str

    @field_validator("join_code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 6 or any(c not in string.ascii_uppercase + string.digits for c in value):
            raise ValueError("组队码格式无效")
        return value


class MoveStudentIn(BaseModel):
    group_id: int | None = None


def _enrollment(db: Session, course_id: int):
    return db.query(models.CourseEnrollment).filter_by(course_id=course_id).first()


def _new_course_code() -> str:
    return "vc_" + secrets.token_urlsafe(18)


def _new_group_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def _group_name_exists(db: Session, course_id: int, name: str) -> bool:
    return any(g.name.casefold() == name.casefold() for g in db.query(models.Group).filter_by(course_id=course_id).all())


def _profile(db: Session, student: models.Student) -> dict:
    group = db.get(models.Group, student.group_id) if student.group_id else None
    enrollment = _enrollment(db, student.course_id)
    return {
        "student_no": student.student_no,
        "name": student.name,
        "course_id": student.course_id,
        "group": {"id": group.id, "name": group.name} if group else None,
        "groups_locked": bool(enrollment and enrollment.groups_locked),
    }


@router.post("/courses")
def create_course(body: CourseIn, db: Session = Depends(get_db),
                  t: models.Teacher = Depends(get_teacher)):
    c = models.Course(name=body.name, term=body.term)
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name, "term": c.term}


@router.post("/courses/{course_id}/enrollment-code")
def create_enrollment_code(course_id: int, body: EnrollmentIn, db: Session = Depends(get_db),
                           t: models.Teacher = Depends(get_teacher)):
    if not db.get(models.Course, course_id):
        raise ApiError(404, "NOT_FOUND", "课程不存在")
    code = _new_course_code()
    enrollment = _enrollment(db, course_id)
    if enrollment is None:
        enrollment = models.CourseEnrollment(
            course_id=course_id,
            code_hash=hash_token(code),
            enrollment_code=code,
            max_group_size=body.max_group_size,
        )
        db.add(enrollment)
    else:
        enrollment.code_hash = hash_token(code)
        enrollment.enrollment_code = code
        enrollment.max_group_size = body.max_group_size
    db.commit()
    return {"course_id": course_id, "enrollment_code": code, "max_group_size": enrollment.max_group_size}


@router.post("/courses/{course_id}/group-lock")
def set_group_lock(course_id: int, body: LockIn, db: Session = Depends(get_db),
                   t: models.Teacher = Depends(get_teacher)):
    enrollment = _enrollment(db, course_id)
    if enrollment is None:
        raise ApiError(422, "REGISTRATION_NOT_CONFIGURED", "请先生成课程邀请码")
    enrollment.groups_locked = body.locked
    db.commit()
    return {"groups_locked": enrollment.groups_locked}


@router.post("/courses/{course_id}/groups")
def teacher_create_group(course_id: int, body: GroupNameIn, db: Session = Depends(get_db),
                         t: models.Teacher = Depends(get_teacher)):
    if not db.get(models.Course, course_id):
        raise ApiError(404, "NOT_FOUND", "课程不存在")
    if _group_name_exists(db, course_id, body.name):
        raise ApiError(409, "GROUP_NAME_EXISTS", "该课程已有同名小组")
    group = models.Group(course_id=course_id, name=body.name)
    db.add(group)
    db.commit()
    return {"id": group.id, "name": group.name}


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
    s.web_session_version += 1
    db.commit()
    return {"student_id": student_id, "token": token}


@router.post("/students/{student_id}/group")
def teacher_move_student(student_id: int, body: MoveStudentIn, db: Session = Depends(get_db),
                         t: models.Teacher = Depends(get_teacher)):
    student = db.get(models.Student, student_id)
    if not student:
        raise ApiError(404, "NOT_FOUND", "学生不存在")
    if body.group_id is not None:
        group = db.get(models.Group, body.group_id)
        if not group or group.course_id != student.course_id:
            raise ApiError(422, "WRONG_GROUP", "小组不属于该学生的课程")
    assignment_ids = [a.id for a in db.query(models.Assignment).filter_by(course_id=student.course_id).all()]
    if assignment_ids and db.query(models.Submission).filter(models.Submission.student_id == student.id, models.Submission.assignment_id.in_(assignment_ids)).first():
        raise ApiError(409, "GROUP_HISTORY_LOCKED", "该学生已有提交，不能调整小组以免影响历史评价")
    student.group_id = body.group_id
    db.commit()
    return _profile(db, student)


@router.post("/api/student-registration", status_code=201)
def student_registration(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    rate_limit(request)
    enrollment = db.query(models.CourseEnrollment).filter_by(code_hash=hash_token(body.course_code)).first()
    if enrollment is None:
        raise ApiError(401, "INVALID_COURSE_CODE", "课程邀请码无效")
    if db.query(models.Student).filter_by(course_id=enrollment.course_id, student_no=body.student_no).first():
        raise ApiError(409, "STUDENT_EXISTS", "该学号已登记，请联系教师重置提交凭证")
    token = new_submit_token()
    student = models.Student(course_id=enrollment.course_id, student_no=body.student_no, name=body.name, submit_token_hash=hash_token(token))
    db.add(student)
    db.commit()
    return {"student_no": student.student_no, "name": student.name, "submit_token": token}


@router.get("/api/student-profile")
def student_profile(student: models.Student = Depends(get_student), db: Session = Depends(get_db)):
    return _profile(db, student)


@router.post("/api/student-groups")
def student_create_group(body: GroupNameIn, student: models.Student = Depends(get_student), db: Session = Depends(get_db)):
    enrollment = _enrollment(db, student.course_id)
    if enrollment is None or enrollment.groups_locked:
        raise ApiError(409, "GROUPS_LOCKED", "当前不能创建小组")
    if student.group_id is not None:
        raise ApiError(409, "ALREADY_GROUPED", "你已在一个小组中")
    if _group_name_exists(db, student.course_id, body.name):
        raise ApiError(409, "GROUP_NAME_EXISTS", "该课程已有同名小组")
    code = _new_group_code()
    while db.query(models.GroupJoinCode).filter_by(code_hash=hash_token(code)).first():
        code = _new_group_code()
    group = models.Group(course_id=student.course_id, name=body.name)
    db.add(group)
    db.flush()
    db.add(models.GroupJoinCode(group_id=group.id, code_hash=hash_token(code)))
    student.group_id = group.id
    db.commit()
    return {"group": {"id": group.id, "name": group.name}, "join_code": code}


@router.post("/api/student-groups/join")
def student_join_group(body: JoinIn, student: models.Student = Depends(get_student), db: Session = Depends(get_db)):
    enrollment = _enrollment(db, student.course_id)
    if enrollment is None or enrollment.groups_locked:
        raise ApiError(409, "GROUPS_LOCKED", "当前不能加入小组")
    if student.group_id is not None:
        raise ApiError(409, "ALREADY_GROUPED", "你已在一个小组中")
    link = db.query(models.GroupJoinCode).filter_by(code_hash=hash_token(body.join_code)).first()
    group = db.get(models.Group, link.group_id) if link else None
    if group is None or group.course_id != student.course_id:
        raise ApiError(404, "GROUP_NOT_FOUND", "组队码无效")
    if db.query(models.Student).filter_by(group_id=group.id).count() >= enrollment.max_group_size:
        raise ApiError(409, "GROUP_FULL", "该小组人数已满")
    student.group_id = group.id
    db.commit()
    return _profile(db, student)
