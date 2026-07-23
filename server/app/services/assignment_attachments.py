"""Storage helpers for teacher-provided assignment reference files."""

import os
import secrets
import shutil
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings
from ..errors import ApiError

_CHUNK_SIZE = 1024 * 1024


def attachment_directory(settings: Settings, assignment_id: int) -> Path:
    return Path(settings.data_dir).resolve() / "assignment_attachments" / str(assignment_id)


def store_assignment_attachments(
    db: Session,
    settings: Settings,
    assignment_id: int,
    uploads: list[UploadFile],
) -> list[models.AssignmentAttachment]:
    """Persist a bounded group of uploaded files using generated storage names."""
    uploads = [upload for upload in uploads if upload.filename]
    if len(uploads) > settings.assignment_attachment_max_files:
        raise ApiError(
            422,
            "TOO_MANY_ATTACHMENTS",
            f"一次最多上传 {settings.assignment_attachment_max_files} 个作业附件",
        )
    if not uploads:
        return []

    final_dir = attachment_directory(settings, assignment_id)
    staging_dir = final_dir.parent / f".staging-{assignment_id}-{secrets.token_hex(8)}"
    max_file_bytes = settings.assignment_attachment_max_file_mb * 1024 * 1024
    max_total_bytes = settings.assignment_attachment_max_total_mb * 1024 * 1024
    total_bytes = 0
    completed: list[tuple[str, str, int]] = []
    moved_paths: list[Path] = []

    try:
        staging_dir.mkdir(parents=True, exist_ok=False)
        for upload in uploads:
            original_name = Path(upload.filename or "").name.strip()
            if not original_name or original_name in {".", ".."}:
                raise ApiError(422, "INVALID_ATTACHMENT", "附件文件名不合法")
            suffix = Path(original_name).suffix[:20]
            stored_name = f"{secrets.token_hex(16)}{suffix}"
            staged_path = staging_dir / stored_name
            size_bytes = 0
            with staged_path.open("wb") as target:
                while chunk := upload.file.read(_CHUNK_SIZE):
                    size_bytes += len(chunk)
                    total_bytes += len(chunk)
                    if size_bytes > max_file_bytes:
                        raise ApiError(
                            422,
                            "ATTACHMENT_TOO_LARGE",
                            f"单个附件不能超过 {settings.assignment_attachment_max_file_mb} MB",
                        )
                    if total_bytes > max_total_bytes:
                        raise ApiError(
                            422,
                            "ATTACHMENTS_TOO_LARGE",
                            f"全部附件不能超过 {settings.assignment_attachment_max_total_mb} MB",
                        )
                    target.write(chunk)
            completed.append((original_name, stored_name, size_bytes))

        final_dir.mkdir(parents=True, exist_ok=True)
        for _, stored_name, _ in completed:
            destination = final_dir / stored_name
            os.replace(staging_dir / stored_name, destination)
            moved_paths.append(destination)

        attachments = [
            models.AssignmentAttachment(
                assignment_id=assignment_id,
                original_name=original_name,
                stored_name=stored_name,
                size_bytes=size_bytes,
            )
            for original_name, stored_name, size_bytes in completed
        ]
        db.add_all(attachments)
        return attachments
    except Exception:
        for path in moved_paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
