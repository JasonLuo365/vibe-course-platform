import argparse
import os

from .db import create_all, init_engine, SessionLocal
from .config import get_settings
from . import models
from .security import hash_password


def main():
    p = argparse.ArgumentParser(prog="vibe-server")
    sub = p.add_subparsers(dest="cmd", required=True)
    ct = sub.add_parser("create-teacher")
    ct.add_argument("username")
    ct.add_argument("display_name")
    args = p.parse_args()

    s = get_settings()
    init_engine(s.database_url)
    create_all()
    if args.cmd == "create-teacher":
        pw = os.environ.get("VIBE_TEACHER_PASSWORD")
        if not pw:
            raise SystemExit("请设置环境变量 VIBE_TEACHER_PASSWORD")
        db = SessionLocal()
        db.add(models.Teacher(username=args.username, password_hash=hash_password(pw),
                              display_name=args.display_name))
        db.commit()
        print(f"教师 {args.username} 已创建")


main()
