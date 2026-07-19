import json
import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_settings_dep, get_student
from ..errors import ApiError
from ..services.jobs import enqueue_individual
from ..services.packages import extract_package, store_package
from ..services.zipcheck import ZipReject, validate_zip
from ..utils import utcnow

router = APIRouter()


class ManifestFile(BaseModel):
    path: str
    sha256: str


class ManifestIn(BaseModel):
    format_version: str
    assignment_code: str
    student_no: str
    client_version: str
    submitted_at: str
    files: list[ManifestFile]


def _ver_tuple(v: str) -> tuple:
    try:
        parts = [int(x) for x in v.split(".")]
    except ValueError:
        return (0,)
    return tuple((parts + [0, 0, 0])[:3])


@router.post("/api/submissions", status_code=201)
async def submit(
    manifest: str = Form(...),
    file: UploadFile = File(...),
    force: str | None = Form(None),
    student: models.Student = Depends(get_student),
    db: Session = Depends(get_db),
    s=Depends(get_settings_dep),
):
    try:
        m = ManifestIn(**json.loads(manifest))
    except Exception as e:
        raise ApiError(422, "BAD_MANIFEST", f"manifest 解析失败: {e}")
    if _ver_tuple(m.client_version) < _ver_tuple(s.min_client_version):
        raise ApiError(426, "CLIENT_OUTDATED", "客户端版本过旧",
                       min_client_version=s.min_client_version,
                       upgrade_instructions="重跑 bootstrap 或 codex plugin marketplace upgrade")
    if m.format_version not in s.supported_manifest_versions:
        raise ApiError(422, "UNSUPPORTED_MANIFEST_VERSION", "manifest 版本不受支持",
                       supported_manifest_versions=s.supported_manifest_versions)
    if m.student_no != student.student_no:
        raise ApiError(422, "STUDENT_MISMATCH", "manifest 学号与 token 身份不符")
    a = db.query(models.Assignment).filter_by(code=m.assignment_code).first()
    if not a:
        raise ApiError(404, "NOT_FOUND", "作业码不存在")
    if a.course_id != student.course_id:
        raise ApiError(422, "WRONG_COURSE", "该作业不属于你的课程")
    if utcnow() < a.opens_at:
        raise ApiError(422, "NOT_OPEN", "作业未开放")
    if utcnow() > a.deadline:
        raise ApiError(422, "DEADLINE_PASSED", "已过截止时间")
    # 落临时文件（大小受限）
    limit = a.max_package_mb * 1024 * 1024
    tmp = None
    size = 0
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, dir=s.data_dir, suffix=".zip")
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise ApiError(422, "PACKAGE_TOO_LARGE", "提交包超过大小上限")
            tmp.write(chunk)
        tmp.close()
        try:
            validate_zip(tmp.name, [f.model_dump() for f in m.files], s)
        except ZipReject as e:
            raise ApiError(422, "ZIP_REJECTED", str(e))
        sub = db.query(models.Submission).filter_by(
            assignment_id=a.id, student_id=student.id).first()
        if sub and sub.current_attempt_id is not None and force != "true":
            raise ApiError(409, "ALREADY_SUBMITTED", "已提交过；确认覆盖请以 force=true 重传")
        if not sub:
            sub = models.Submission(assignment_id=a.id, student_id=student.id, status="received")
            db.add(sub)
            db.flush()
        attempt_no = (db.query(models.SubmissionAttempt)
                      .filter_by(submission_id=sub.id).count()) + 1
        att = models.SubmissionAttempt(
            submission_id=sub.id, attempt_no=attempt_no, submitted_at=utcnow(),
            package_path="", size_bytes=size, manifest_version=m.format_version, status="received")
        db.add(att)
        db.flush()
        att.package_path = store_package(s, a.id, student.id, att.id, tmp.name)
        extract_package(s, att.id, os.path.join(s.data_dir, att.package_path))
        sub.current_attempt_id = att.id
        sub.status = "queued"
        att.status = "queued"

        # Mark any existing grade overrides as stale before committing the new attempt.
        _mark_overrides_stale(db, a.id, student.id, student.group_id)

        enqueue_individual(db, a.id, att.id)
        db.commit()
        return {"submission_id": sub.id, "attempt_no": attempt_no}
    finally:
        if tmp is not None:
            try:
                if not tmp.closed:
                    tmp.close()
            except Exception:
                pass
            try:
                if os.path.exists(tmp.name):
                    os.unlink(tmp.name)
            except OSError:
                pass


def _mark_overrides_stale(db: Session, assignment_id: int, student_id: int, group_id: int | None):
    (
        db.query(models.GradeOverride)
        .filter(models.GradeOverride.target_type == "individual")
        .filter(models.GradeOverride.target_id == f"{assignment_id}:{student_id}")
        .update({"stale": True}, synchronize_session=False)
    )
    if group_id is not None:
        (
            db.query(models.GradeOverride)
            .filter(models.GradeOverride.target_type == "group")
            .filter(models.GradeOverride.target_id == f"{assignment_id}:{group_id}")
            .update({"stale": True}, synchronize_session=False)
        )


@router.get("/api/submissions/status")
def submission_status(assignment_code: str,
                      student: models.Student = Depends(get_student),
                      db: Session = Depends(get_db)):
    a = db.query(models.Assignment).filter_by(code=assignment_code).first()
    if not a:
        raise ApiError(404, "NOT_FOUND", "作业码不存在")
    if a.course_id != student.course_id:
        raise ApiError(404, "NOT_FOUND", "作业码不存在")
    sub = db.query(models.Submission).filter_by(
        assignment_id=a.id, student_id=student.id).first()
    if not sub or not sub.current_attempt_id:
        return {"submission_id": 0, "assignment_code": assignment_code, "status": "none",
                "submitted_at": "", "size_bytes": 0, "error": None}
    att = db.get(models.SubmissionAttempt, sub.current_attempt_id)
    return {"submission_id": sub.id, "assignment_code": assignment_code,
            "status": sub.status, "submitted_at": att.submitted_at.isoformat(),
            "size_bytes": att.size_bytes, "error": sub.error}

