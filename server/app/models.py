from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .utils import utcnow


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    display_name: Mapped[str] = mapped_column(default="")


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    term: Mapped[str] = mapped_column(default="")


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    name: Mapped[str]


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("course_id", "student_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    student_no: Mapped[str]
    name: Mapped[str]
    submit_token_hash: Mapped[str] = mapped_column(unique=True)


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    code: Mapped[str] = mapped_column(unique=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    rubric_json: Mapped[list] = mapped_column(JSON)
    opens_at: Mapped[object] = mapped_column(DateTime)
    deadline: Mapped[object] = mapped_column(DateTime)
    max_package_mb: Mapped[int] = mapped_column(default=50)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    current_attempt_id: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(default="received")
    error: Mapped[str | None] = mapped_column(nullable=True)


class SubmissionAttempt(Base):
    __tablename__ = "submission_attempts"
    __table_args__ = (UniqueConstraint("submission_id", "attempt_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"))
    attempt_no: Mapped[int]
    submitted_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    package_path: Mapped[str]
    size_bytes: Mapped[int]
    manifest_version: Mapped[str]
    status: Mapped[str] = mapped_column(default="received")
    error: Mapped[str | None] = mapped_column(nullable=True)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("submission_attempts.id"))
    grade: Mapped[str]
    dimension_scores_json: Mapped[list] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(default="")
    feedback_json: Mapped[list] = mapped_column(JSON)
    flags_json: Mapped[list] = mapped_column(JSON)
    evidence_json: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(default="")
    prompt_version: Mapped[str] = mapped_column(default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class GroupEvaluation(Base):
    __tablename__ = "group_evaluations"
    __table_args__ = (UniqueConstraint("assignment_id", "group_id", "generation"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    generation: Mapped[int] = mapped_column(default=1)
    grade: Mapped[str]
    rationale: Mapped[str] = mapped_column(default="")
    contribution_json: Mapped[dict] = mapped_column(JSON)
    evidence_json: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class GradeOverride(Base):
    __tablename__ = "grade_overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str]  # individual | group
    target_id: Mapped[str]    # individual: "{assignment_id}:{student_id}";group: "{assignment_id}:{group_id}"
    final_grade: Mapped[str]
    comment: Mapped[str] = mapped_column(default="")
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"))
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    stale: Mapped[bool] = mapped_column(default=False)


class EvalJob(Base):
    __tablename__ = "eval_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"))
    kind: Mapped[str]  # individual | group
    target_id: Mapped[int]
    status: Mapped[str] = mapped_column(default="queued")  # queued|running|done|failed
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
