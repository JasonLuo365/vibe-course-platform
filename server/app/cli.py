"""Small, operator-facing commands for preparing a classroom deployment."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import models
from .api.assignments import AssignmentIn, _as_naive_utc, _new_code
from .api.courses import create_course_enrollment
from .config import get_settings
from .db import SessionLocal, create_all, init_engine
from .errors import ApiError
from .security import hash_password
from .services.roster import import_roster


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8-sig")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vibe-server")
    sub = p.add_subparsers(dest="cmd", required=True)

    ct = sub.add_parser("create-teacher", help="Create a teacher account.")
    ct.add_argument("username")
    ct.add_argument("display_name")

    cc = sub.add_parser("create-course", help="Create a course shared by all teachers.")
    cc.add_argument("name")
    cc.add_argument("--term", default="")

    ir = sub.add_parser("import-roster", help="Import roster CSV and print one-time student tokens.")
    ir.add_argument("course_id", type=int)
    ir.add_argument("--input", default="-", help="UTF-8 CSV path, or - for stdin.")

    ca = sub.add_parser("create-assignment", help="Create an assignment from UTF-8 JSON.")
    ca.add_argument("course_id", type=int)
    ca.add_argument("--input", default="-", help="JSON path, or - for stdin.")
    return p


def main():
    args = _parser().parse_args()
    settings = get_settings()
    init_engine(settings.database_url)
    create_all()
    db = SessionLocal()
    try:
        if args.cmd == "create-teacher":
            pw = os.environ.get("VIBE_TEACHER_PASSWORD")
            if not pw:
                raise SystemExit("Set VIBE_TEACHER_PASSWORD before creating a teacher.")
            if db.query(models.Teacher).filter_by(username=args.username).first():
                raise SystemExit(f"Teacher already exists: {args.username}")
            teacher = models.Teacher(
                username=args.username,
                password_hash=hash_password(pw),
                display_name=args.display_name,
            )
            db.add(teacher)
            db.commit()
            print(json.dumps({"id": teacher.id, "username": teacher.username}, ensure_ascii=False))

        elif args.cmd == "create-course":
            course = models.Course(name=args.name, term=args.term)
            db.add(course)
            db.flush()
            _enrollment, code = create_course_enrollment(db, course.id)
            db.commit()
            print(json.dumps({"id": course.id, "name": course.name, "term": course.term,
                              "enrollment_code": code}, ensure_ascii=False))

        elif args.cmd == "import-roster":
            if not db.get(models.Course, args.course_id):
                raise SystemExit(f"Course does not exist: {args.course_id}")
            result = import_roster(db, args.course_id, _read_input(args.input))
            print(f'{{"created_students": {result["created_students"]}}}')
            print(f"Created {result['created_students']} student(s).", file=sys.stderr)

        elif args.cmd == "create-assignment":
            if not db.get(models.Course, args.course_id):
                raise SystemExit(f"Course does not exist: {args.course_id}")
            body = AssignmentIn.model_validate_json(_read_input(args.input))
            assignment = models.Assignment(
                course_id=args.course_id,
                code=_new_code(db),
                title=body.title,
                description=body.description,
                rubric_json=[item.model_dump() for item in body.rubric],
                evaluation_profile=body.evaluation_profile,
                evaluation_instructions=body.evaluation_instructions,
                opens_at=_as_naive_utc(body.opens_at),
                deadline=_as_naive_utc(body.deadline),
                max_package_mb=body.max_package_mb,
            )
            db.add(assignment)
            db.commit()
            print(json.dumps({"id": assignment.id, "code": assignment.code}, ensure_ascii=False))

    except ApiError as exc:
        db.rollback()
        raise SystemExit(f"{exc.code}: {exc.message}") from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
