from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .. import models
from ..api.assignments import AssignmentIn, _new_code
from ..api.courses import CourseIn, create_course_enrollment
from ..db import get_db
from ..deps import get_student_page, get_teacher
from ..eval.prompts import PROMPT_PROFILE_LABELS
from ..errors import ApiError
from . import PageAuthRequired
from .board import board_data, progress_for_assignment
from ..services.student_portal import dashboard_data, submission_feedback_data
from ..utils import teacher_local_to_naive_utc

router = APIRouter()


def _prompt_profiles(selected: str = "generic_experiment") -> list[tuple[str, str]]:
    """Return the available reusable prompt templates for teacher forms."""
    profiles = list(PROMPT_PROFILE_LABELS.items())
    if selected and selected not in PROMPT_PROFILE_LABELS:
        profiles.append((selected, f"当前自定义档案：{selected}"))
    return profiles


def get_teacher_page(request: Request, db: Session = Depends(get_db)) -> models.Teacher:
    tid = request.session.get("teacher_id")
    if not tid:
        raise PageAuthRequired(next_url=str(request.url.path))
    t = db.get(models.Teacher, tid)
    if not t:
        raise PageAuthRequired(next_url=str(request.url.path))
    return t


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    tid = request.session.get("teacher_id")
    if not tid:
        return RedirectResponse("/login")
    teacher = db.get(models.Teacher, tid)
    if teacher is None:
        return RedirectResponse("/login")
    from ..main import templates
    courses = db.query(models.Course).all()
    assignments = db.query(models.Assignment).all()
    enrollments = {
        enrollment.course_id: enrollment
        for enrollment in db.query(models.CourseEnrollment).all()
    }
    rows = [
        {
            "course": c,
            "assignments": [a for a in assignments if a.course_id == c.id],
        }
        for c in courses
    ]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"rows": rows, "enrollments": enrollments, "teacher": teacher},
    )


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    from ..main import templates

    return templates.TemplateResponse(
        request,
        "login.html",
        {"next_url": next, "flash": ""},
    )


@router.get("/student/password/reset", response_class=HTMLResponse)
def student_password_reset_page(request: Request):
    from ..main import templates

    return templates.TemplateResponse(request, "student_password_reset.html", {"flash": ""})


@router.get("/student", response_class=HTMLResponse)
def student_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    student: models.Student = Depends(get_student_page),
):
    from ..main import templates

    data = dashboard_data(db, student)
    return templates.TemplateResponse(
        request,
        "student_dashboard.html",
        {**data, "student": student},
    )


@router.get("/student/submissions/{sid}", response_class=HTMLResponse)
def student_submission_feedback(
    request: Request,
    sid: int,
    db: Session = Depends(get_db),
    student: models.Student = Depends(get_student_page),
):
    from ..main import templates

    submission = db.get(models.Submission, sid)
    if submission is None or submission.student_id != student.id:
        raise ApiError(404, "NOT_FOUND", "提交不存在")
    data = submission_feedback_data(db, student, submission)
    return templates.TemplateResponse(
        request,
        "student_feedback.html",
        {**data, "student": student},
    )


@router.get("/assignments/{aid}/board", response_class=HTMLResponse)
def board_page(
    request: Request,
    aid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates

    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    data = board_data(db, assignment)
    return templates.TemplateResponse(
        request,
        "board.html",
        {
            "teacher": t,
            "assignment": data["assignment"],
            "groups": data["groups"],
            "progress": data["progress"],
        },
    )


@router.get("/api/assignments/{aid}/progress")
def progress_api(
    aid: int,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher),
):
    if db.get(models.Assignment, aid) is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    return progress_for_assignment(db, aid)


@router.get("/students", response_class=HTMLResponse)
def students_page(
    request: Request,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    """Show the roster, group membership and latest submission state."""
    from ..main import templates

    courses = db.query(models.Course).order_by(models.Course.id).all()
    course_by_id = {course.id: course for course in courses}
    groups = {g.id: g.name for g in db.query(models.Group).all()}
    groups_by_course: dict[int, list[models.Group]] = {}
    for group in db.query(models.Group).order_by(models.Group.course_id, models.Group.name).all():
        groups_by_course.setdefault(group.course_id, []).append(group)
    enrollments = {
        item.course_id: item
        for item in db.query(models.CourseEnrollment).all()
    }
    students = (
        db.query(models.Student)
        .order_by(models.Student.course_id, models.Student.student_no)
        .all()
    )
    statuses: dict[int, list[str]] = {}
    for submission in db.query(models.Submission).all():
        statuses.setdefault(submission.student_id, []).append(submission.status)
    rows = [
        {
            "student": student,
            "course": course_by_id.get(student.course_id),
            "group": groups.get(student.group_id, "未分组"),
            "group_id": student.group_id,
            "statuses": statuses.get(student.id, []),
        }
        for student in students
    ]
    return templates.TemplateResponse(
        request,
        "students.html",
        {
            "teacher": t,
            "rows": rows,
            "courses": courses,
            "groups_by_course": groups_by_course,
            "enrollments": enrollments,
        },
    )


@router.get("/courses/new", response_class=HTMLResponse)
def new_course_page(
    request: Request,
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates

    return templates.TemplateResponse(request, "course_form.html", {"teacher": t})


@router.post("/courses/new")
async def create_course_page(
    request: Request,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    form = await request.form()
    try:
        body = CourseIn.model_validate({
            "name": str(form.get("name", "")),
            "term": str(form.get("term", "")),
        })
    except (ValueError, TypeError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", f"课程配置不正确：{exc}") from exc
    existing = next(
        (
            course for course in db.query(models.Course).all()
            if course.name.casefold() == body.name.casefold()
            and course.term.casefold() == body.term.casefold()
        ),
        None,
    )
    if existing:
        raise ApiError(409, "COURSE_EXISTS", "同名课程和学期/班级已存在")
    course = models.Course(name=body.name, term=body.term)
    db.add(course)
    db.flush()
    create_course_enrollment(db, course.id)
    db.commit()
    return RedirectResponse(url="/", status_code=302)


@router.get("/assignments/new", response_class=HTMLResponse)
@router.get("/courses/{course_id}/assignments/new", response_class=HTMLResponse)
def new_assignment_page(
    request: Request,
    course_id: int | None = None,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    from ..main import templates
    courses = db.query(models.Course).order_by(models.Course.id).all()
    if not courses:
        return RedirectResponse(url="/courses/new", status_code=302)
    selected_course = db.get(models.Course, course_id) if course_id is not None else courses[0]
    if selected_course is None:
        raise ApiError(404, "NOT_FOUND", "课程不存在")
    return templates.TemplateResponse(
        request,
        "assignment_form.html",
        {
            "teacher": t,
            "courses": courses,
            "selected_course": selected_course,
            "prompt_profiles": _prompt_profiles(),
        },
    )


@router.post("/assignments/new")
async def create_assignment_page(request: Request, db: Session = Depends(get_db), t: models.Teacher = Depends(get_teacher_page)):
    form = await request.form()
    try:
        course_id = int(str(form.get("course_id", "")))
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", "请选择已有课程") from exc
    course = db.get(models.Course, course_id)
    if course is None:
        raise ApiError(404, "NOT_FOUND", "课程不存在")
    try:
        body = AssignmentIn.model_validate({
            "title": str(form.get("title", "")),
            "description": str(form.get("description", "")),
            "evaluation_profile": str(form.get("evaluation_profile", "generic_experiment")),
            "evaluation_instructions": str(form.get("evaluation_instructions", "")),
            "opens_at": str(form.get("opens_at", "")),
            "deadline": str(form.get("deadline", "")),
            "max_package_mb": str(form.get("max_package_mb", "50")),
        })
    except (ValueError, TypeError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", f"作业配置不正确：{exc}") from exc
    assignment = models.Assignment(
        course_id=course.id,
        code=_new_code(db),
        title=body.title,
        description=body.description,
        rubric_json=[item.model_dump() for item in body.rubric],
        evaluation_profile=body.evaluation_profile,
        evaluation_instructions=body.evaluation_instructions,
        opens_at=teacher_local_to_naive_utc(body.opens_at),
        deadline=teacher_local_to_naive_utc(body.deadline),
        max_package_mb=body.max_package_mb,
    )
    db.add(assignment)
    db.commit()
    return RedirectResponse(url=f"/assignments/{assignment.id}/board", status_code=302)


@router.get("/assignments/{aid}/evaluation-config", response_class=HTMLResponse)
def evaluation_config_page(request: Request, aid: int, db: Session = Depends(get_db), t: models.Teacher = Depends(get_teacher_page)):
    from ..main import templates
    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    return templates.TemplateResponse(
        request,
        "evaluation_config.html",
        {
            "teacher": t,
            "assignment": assignment,
            "prompt_profiles": _prompt_profiles(assignment.evaluation_profile or "generic_experiment"),
        },
    )


@router.post("/assignments/{aid}/evaluation-config")
async def save_evaluation_config(request: Request, aid: int, db: Session = Depends(get_db), t: models.Teacher = Depends(get_teacher_page)):
    assignment = db.get(models.Assignment, aid)
    if assignment is None:
        raise ApiError(404, "NOT_FOUND", "作业不存在")
    form = await request.form()
    profile = str(form.get("evaluation_profile", "generic_experiment")).strip()
    instructions = str(form.get("evaluation_instructions", "")).strip()
    if not profile or len(profile) > 100:
        raise ApiError(422, "VALIDATION_ERROR", "评价档案不能为空且最多 100 个字符")
    if len(instructions) > 12000:
        raise ApiError(422, "VALIDATION_ERROR", "评估提示词最多 12000 个字符")
    assignment.evaluation_profile = profile
    assignment.evaluation_instructions = instructions
    db.commit()
    return RedirectResponse(url=f"/assignments/{aid}/board", status_code=302)


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(
    request: Request,
    db: Session = Depends(get_db),
    t: models.Teacher = Depends(get_teacher_page),
):
    """Provide a small course-level summary for teachers."""
    from ..main import templates

    status_counts: dict[str, int] = {}
    grade_counts: dict[str, int] = {}
    submissions = db.query(models.Submission).all()
    for submission in submissions:
        status_counts[submission.status] = status_counts.get(submission.status, 0) + 1
    for evaluation in db.query(models.Evaluation).all():
        grade_counts[evaluation.grade] = grade_counts.get(evaluation.grade, 0) + 1
    return templates.TemplateResponse(
        request,
        "analytics.html",
        {
            "teacher": t,
            "submissions": len(submissions),
            "status_counts": status_counts,
            "grade_counts": grade_counts,
        },
    )
