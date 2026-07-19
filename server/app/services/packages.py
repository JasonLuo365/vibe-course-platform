import os
import shutil

from ..config import Settings
from .zipcheck import safe_extract


def store_package(s: Settings, assignment_id: int, student_id: int,
                  attempt_id: int, tmp_zip: str) -> str:
    rel = os.path.join("packages", str(assignment_id), str(student_id), f"{attempt_id}.zip")
    dest = os.path.join(s.data_dir, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(tmp_zip, dest)
    return rel


def extract_package(s: Settings, attempt_id: int, zip_path: str) -> str:
    dest = os.path.join(s.data_dir, "extracted", str(attempt_id))
    safe_extract(zip_path, dest)
    return dest

