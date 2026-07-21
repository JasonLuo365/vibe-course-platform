import csv
import io

from sqlalchemy.orm import Session

from .. import models
from ..errors import ApiError


def import_roster(db: Session, course_id: int, csv_text: str) -> dict:
    rows = list(csv.DictReader(io.StringIO(csv_text.strip())))
    if not rows or "学号" not in rows[0] or "姓名" not in rows[0] or "小组" not in rows[0]:
        raise ApiError(422, "BAD_ROSTER", "CSV 需含表头：学号,姓名,小组")
    groups: dict[str, models.Group] = {
        g.name: g for g in db.query(models.Group).filter_by(course_id=course_id)
    }
    created = 0
    for row in rows:
        no, name, gname = row["学号"].strip(), row["姓名"].strip(), row["小组"].strip()
        if not no:
            continue
        if gname not in groups:
            g = models.Group(course_id=course_id, name=gname)
            db.add(g)
            db.flush()
            groups[gname] = g
        if db.query(models.Student).filter_by(course_id=course_id, student_no=no).first():
            continue  # 重复学号跳过（幂等重导）
        db.add(models.Student(course_id=course_id, group_id=groups[gname].id,
                              student_no=no, name=name))
        created += 1
    db.commit()
    return {"created_students": created}
