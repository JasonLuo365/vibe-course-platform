# P2 服务器核心 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付可运行的 FastAPI 服务器核心：数据模型、教师认证、课程/花名册/submit_token、作业/rubric/meta、学生 Bearer 认证、ZIP 安全校验、上传与状态端点、eval_jobs 入队。

**Architecture:** 模块化单体（spec §2）：`server/app` 按 api/services 分层，SQLAlchemy 2.x + SQLite（`create_all`，Alembic 留待演进），会话用签名 cookie，学生用 Bearer submit_token。评估 worker（P3）消费本计划落库的 `eval_jobs`；教师页面（P4）消费本计划的 API 与模型。

**Tech Stack:** Python ≥3.10、FastAPI、SQLAlchemy 2.x、pydantic v2、pydantic-settings、uvicorn、pytest + TestClient。

## Global Constraints

- 严格遵循 spec（`docs/superpowers/specs/2026-07-17-vibe-coding-homework-eval-design.md`）§4 数据模型/API、§7 错误语义；以下值逐字采用：
  - 错误响应统一 `{"error": {"code": "...", "message": "...", ...}}`；状态码：401 token 无效、409 已提交、422 校验失败、426 CLIENT_OUTDATED、429 限流。
  - `submit_token` = `"vs_" + token_urlsafe(24)`，库中只存 sha256 hex，明文仅导入/重置时一次性导出。
  - 学生端 meta 返回含 `min_client_version`、`supported_manifest_versions`；manifest `format_version` 当前仅支持 `"1"`。
  - 每次提交产生新的 `submission_attempts` 行（不可变）；`submissions` 为当前态指针。
  - ZIP 校验（spec §4）：拒绝路径穿越/绝对路径/符号链接/重复路径；限额：单文件 ≤10MB、总数 ≤5000、总解压 ≤250MB、压缩比 ≤100；manifest 文件集合一致 + 逐文件 SHA-256 回查；临时目录安全解压后原子移动。
  - 时间一律 naive UTC（辅助函数 `utcnow()`），禁止混入 aware datetime。
- TDD：每个任务先写失败测试再实现；测试全部在 `server/tests/`，运行目录为 `server/`。
- 目录：`server/app/`（包 `app`）、`server/tests/`；不改动 `docs/`、`spikes/`。
- 每任务结束 commit；中文 commit message。

---

### Task 1: 项目骨架与 /health

**Files:**
- Create: `server/pyproject.toml`
- Create: `server/app/__init__.py`
- Create: `server/app/config.py`
- Create: `server/app/main.py`
- Create: `server/tests/__init__.py`
- Create: `server/tests/conftest.py`
- Create: `server/tests/test_health.py`

**Interfaces:**
- Consumes: 无
- Produces: `Settings`（pydantic-settings，env 前缀 `VIBE_`）；`create_app(settings) -> FastAPI`；测试 fixture `client`（tmp 数据库+tmp data 目录的 TestClient）

- [ ] **Step 1: pyproject.toml 并安装**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vibe-server"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.2", "httpx>=0.27"]

[project.scripts]
vibe-server = "app.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

```powershell
cd server
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"
```

- [ ] **Step 2: 写失败测试 test_health.py 与 conftest.py**

```python
# server/tests/conftest.py
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path / "data"),
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        session_secret="test-secret",
    )


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
```

```python
# server/tests/test_health.py
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 3: 运行确认失败**

Run: `cd server; pytest tests/test_health.py -v`
Expected: FAIL（404，路由不存在/模块不存在）

- [ ] **Step 4: 实现 config.py 与 main.py**

```python
# server/app/config.py
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIBE_", env_file=".env", extra="ignore")

    data_dir: str = "data"
    database_url: str = "sqlite:///data/app.db"
    session_secret: str = "dev-secret-change-me"
    session_cookie: str = "vibe_session"
    min_client_version: str = "0.1.0"
    supported_manifest_versions: list[str] = ["1"]
    default_max_package_mb: int = 50
    max_file_mb: int = 10
    max_files: int = 5000
    max_uncompressed_mb: int = 250
    max_compression_ratio: float = 100.0
    rate_limit_per_minute: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# server/app/main.py
from fastapi import FastAPI

from .config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="vibe-server")
    app.state.settings = settings

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: 运行确认通过**

Run: `cd server; pytest tests/test_health.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add server/
git commit -m "feat(server): 项目骨架与 /health"
```

---

### Task 2: 数据库基座与全部数据模型

**Files:**
- Create: `server/app/db.py`
- Create: `server/app/utils.py`
- Create: `server/app/models.py`
- Modify: `server/app/main.py`（接入 init_engine/create_all）
- Create: `server/tests/test_models.py`

**Interfaces:**
- Consumes: Task 1 的 `Settings`、`create_app`
- Produces: `Base`、`init_engine(url)`、`create_all()`、`get_db()`；`utcnow()`；模型：`Teacher/Course/Group/Student/Assignment/Submission/SubmissionAttempt/Evaluation/GroupEvaluation/GradeOverride/EvalJob`（字段同 spec §4）

- [ ] **Step 1: 写失败测试 test_models.py**

```python
# server/tests/test_models.py
from app import models
from app.db import SessionLocal
from app.utils import utcnow


def test_create_all_and_insert(client):
    db = SessionLocal()
    t = models.Teacher(username="admin", password_hash="x", display_name="Admin")
    c = models.Course(name="VC101", term="2026秋")
    db.add_all([t, c])
    db.flush()
    g = models.Group(course_id=c.id, name="第1组")
    db.add(g)
    db.flush()
    s = models.Student(course_id=c.id, group_id=g.id, student_no="2024001",
                       name="张三", submit_token_hash="h" * 64)
    a = models.Assignment(course_id=c.id, code="HW3X7K2Q", title="作业3",
                          description="d", rubric_json=[{"name": "prompt质量", "weight": 100, "description": "d"}],
                          opens_at=utcnow(), deadline=utcnow(), max_package_mb=50)
    db.add_all([s, a])
    db.flush()
    sub = models.Submission(assignment_id=a.id, student_id=s.id, status="received")
    db.add(sub)
    db.flush()
    att = models.SubmissionAttempt(submission_id=sub.id, attempt_no=1, submitted_at=utcnow(),
                                   package_path="p.zip", size_bytes=10, manifest_version="1", status="received")
    db.add(att)
    db.flush()
    sub.current_attempt_id = att.id
    ev = models.Evaluation(attempt_id=att.id, grade="B", dimension_scores_json=[], rationale="r",
                           feedback_json=[], flags_json=[], evidence_json=[], model="m", prompt_version="v1")
    ge = models.GroupEvaluation(assignment_id=a.id, group_id=g.id, generation=1, grade="B",
                                rationale="r", contribution_json={}, evidence_json=[])
    ov = models.GradeOverride(target_type="individual", target_id=f"{a.id}:{s.id}",
                              final_grade="A", comment="ok", teacher_id=t.id, stale=False)
    job = models.EvalJob(assignment_id=a.id, kind="individual", target_id=att.id, status="queued", attempts=0)
    db.add_all([ev, ge, ov, job])
    db.commit()
    assert db.query(models.Student).one().student_no == "2024001"
    assert db.query(models.EvalJob).one().status == "queued"
    db.close()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server; pytest tests/test_models.py -v`
Expected: FAIL（app.db / app.models / app.utils 不存在）

- [ ] **Step 3: 实现 db.py、utils.py、models.py**

```python
# server/app/utils.py
from datetime import datetime, timezone


def utcnow() -> datetime:
    """全项目唯一时间源：naive UTC（spec 约束）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
```

```python
# server/app/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal = sessionmaker(expire_on_commit=False)


def init_engine(url: str):
    global _engine
    _engine = create_engine(url, connect_args={"check_same_thread": False})
    SessionLocal.configure(bind=_engine)
    return _engine


def create_all():
    from . import models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(_engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

```python
# server/app/models.py
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
    target_id: Mapped[str]    # individual: "{assignment_id}:{student_id}"；group: "{assignment_id}:{group_id}"
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
```

- [ ] **Step 4: main.py 接入数据库**

在 `create_app` 中 `app.state.settings = settings` 之后加：

```python
    from .db import create_all, init_engine
    init_engine(settings.database_url)
    create_all()
```

- [ ] **Step 5: 运行确认通过**

Run: `cd server; pytest tests/test_models.py -v`
Expected: 1 passed（同时 test_health 仍过）

- [ ] **Step 6: Commit**

```bash
git add server/
git commit -m "feat(server): 数据库基座与全部数据模型"
```

---

### Task 3: 教师认证（密码哈希、登录 session、create-teacher CLI）

**Files:**
- Create: `server/app/security.py`
- Create: `server/app/errors.py`
- Create: `server/app/deps.py`
- Create: `server/app/api/__init__.py`
- Create: `server/app/api/auth.py`
- Create: `server/app/cli.py`
- Modify: `server/app/main.py`（SessionMiddleware + 路由 + 异常处理器）
- Create: `server/tests/test_auth.py`

**Interfaces:**
- Consumes: Task 2 的模型与 `get_db`
- Produces: `hash_password/verify_password/new_submit_token/hash_token`；`ApiError(status, code, message, **extra)`；`get_teacher(request, db) -> Teacher`（401）；`POST /login`、`POST /logout`；`vibe-server create-teacher <username> <display_name>`（密码从环境变量 `VIBE_TEACHER_PASSWORD` 读，打印结果）

- [ ] **Step 1: 写失败测试 test_auth.py**

```python
# server/tests/test_auth.py
from app import models
from app.db import SessionLocal
from app.security import hash_password


def _mk_teacher(username="admin", password="pw123456"):
    db = SessionLocal()
    t = models.Teacher(username=username, password_hash=hash_password(password),
                       display_name="Admin")
    db.add(t)
    db.commit()
    db.close()


def test_login_logout_and_protected(client):
    _mk_teacher()
    assert client.get("/api/whoami").status_code == 401
    r = client.post("/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    r = client.post("/login", json={"username": "admin", "password": "pw123456"})
    assert r.status_code == 200
    r = client.get("/api/whoami")
    assert r.status_code == 200 and r.json()["username"] == "admin"
    client.post("/logout")
    assert client.get("/api/whoami").status_code == 401
```

- [ ] **Step 2: 运行确认失败** → 404/401 不符

- [ ] **Step 3: 实现**

```python
# server/app/security.py
import hashlib
import hmac
import secrets


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    iters = 200_000
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iters)
    return f"pbkdf2${iters}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def new_submit_token() -> str:
    return "vs_" + secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
```

```python
# server/app/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        self.status, self.code, self.message, self.extra = status, code, message, extra


async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status,
                        content={"error": {"code": exc.code, "message": exc.message, **exc.extra}})
```

```python
# server/app/deps.py
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from . import models
from .db import get_db
from .errors import ApiError


def get_teacher(request: Request, db: Session = Depends(get_db)) -> models.Teacher:
    tid = request.session.get("teacher_id")
    if not tid:
        raise ApiError(401, "UNAUTHORIZED", "教师未登录")
    t = db.get(models.Teacher, tid)
    if not t:
        raise ApiError(401, "UNAUTHORIZED", "教师不存在")
    return t
```

```python
# server/app/api/auth.py
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_teacher
from ..errors import ApiError
from ..security import verify_password

router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Teacher).filter_by(username=body.username).first()
    if not t or not verify_password(body.password, t.password_hash):
        raise ApiError(401, "UNAUTHORIZED", "用户名或密码错误")
    request.session["teacher_id"] = t.id
    return {"ok": True}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/whoami")
def whoami(t: models.Teacher = Depends(get_teacher)):
    return {"username": t.username, "display_name": t.display_name}
```

```python
# server/app/cli.py
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
```

main.py：在 `create_app` 中注册：

```python
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from .api import auth
from .config import Settings, get_settings
from .errors import ApiError, api_error_handler


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="vibe-server")
    app.state.settings = settings
    from .db import create_all, init_engine
    init_engine(settings.database_url)
    create_all()
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret,
                       session_cookie=settings.session_cookie)
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(auth.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server; pytest tests/test_auth.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add server/
git commit -m "feat(server): 教师认证与 create-teacher CLI"
```

---

### Task 4: 课程创建与花名册（token 生成/导出/重置）

**Files:**
- Create: `server/app/services/__init__.py`
- Create: `server/app/services/roster.py`
- Create: `server/app/api/courses.py`
- Modify: `server/app/main.py`（注册路由）
- Create: `server/tests/test_courses_roster.py`

**Interfaces:**
- Consumes: Task 3 的 `get_teacher`
- Produces: `POST /courses`；`POST /courses/{id}/roster`（CSV 文本，列：学号，姓名，小组；响应含一次性 `tokens_csv`）；`GET /courses/{id}/tokens.csv`（一次性导出当前明文——仅存于导入响应与本端点首次调用后的缓存表？不——见下）；`POST /students/{id}/reset-token`（返回新明文）

**设计决定（token 明文只出现一次）**：导入响应即唯一导出时机（`tokens_csv` 字段）；不提供事后导出端点（库里只有哈希）。重置返回新明文一次。spec"明文随 CSV 一次性导出"由此满足。

- [ ] **Step 1: 写失败测试 test_courses_roster.py**

```python
# server/tests/test_courses_roster.py
from app.db import SessionLocal
from app import models
from app.security import hash_token
from tests.test_auth import _mk_teacher


def _login(client):
    _mk_teacher()
    client.post("/login", json={"username": "admin", "password": "pw123456"})


def test_roster_import_and_tokens(client):
    _login(client)
    r = client.post("/courses", json={"name": "VC101", "term": "2026秋"})
    cid = r.json()["id"]
    csv_text = "学号,姓名,小组\n2024001,张三,第1组\n2024002,李四,第1组\n2024003,王五,第2组\n"
    r = client.post(f"/courses/{cid}/roster", json={"csv": csv_text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_students"] == 3
    assert "2024001" in body["tokens_csv"] and "vs_" in body["tokens_csv"]
    db = SessionLocal()
    students = db.query(models.Student).all()
    assert len(students) == 3
    assert db.query(models.Group).count() == 2
    # 明文不出现在库中
    assert all(len(s.submit_token_hash) == 64 for s in students)
    # 用导出的 token 能认证
    token_line = [l for l in body["tokens_csv"].splitlines() if l.startswith("2024001")][0]
    token = token_line.split(",")[2]
    assert db.query(models.Student).filter_by(submit_token_hash=hash_token(token)).count() == 1
    db.close()


def test_reset_token(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    client.post(f"/courses/{cid}/roster", json={"csv": "学号,姓名,小组\n1,甲,G\n"})
    db = SessionLocal()
    sid = db.query(models.Student).one().id
    old_hash = db.query(models.Student).one().submit_token_hash
    db.close()
    r = client.post(f"/students/{sid}/reset-token")
    assert r.status_code == 200 and r.json()["token"].startswith("vs_")
    db = SessionLocal()
    s = db.query(models.Student).one()
    assert s.submit_token_hash != old_hash
    db.close()


def test_roster_requires_teacher(client):
    assert client.post("/courses", json={"name": "C", "term": ""}).status_code == 401
```

- [ ] **Step 2: 运行确认失败** → 404

- [ ] **Step 3: 实现**

```python
# server/app/services/roster.py
import csv
import io

from sqlalchemy.orm import Session

from .. import models
from ..errors import ApiError
from ..security import hash_token, new_submit_token


def import_roster(db: Session, course_id: int, csv_text: str) -> dict:
    rows = list(csv.DictReader(io.StringIO(csv_text.strip())))
    if not rows or "学号" not in rows[0] or "姓名" not in rows[0] or "小组" not in rows[0]:
        raise ApiError(422, "BAD_ROSTER", "CSV 需含表头：学号,姓名,小组")
    groups: dict[str, models.Group] = {
        g.name: g for g in db.query(models.Group).filter_by(course_id=course_id)
    }
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["学号", "姓名", "submit_token"])
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
        token = new_submit_token()
        db.add(models.Student(course_id=course_id, group_id=groups[gname].id,
                              student_no=no, name=name,
                              submit_token_hash=hash_token(token)))
        w.writerow([no, name, token])
        created += 1
    db.commit()
    return {"created_students": created, "tokens_csv": out.getvalue()}
```

```python
# server/app/api/courses.py
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
```

main.py 注册：`from .api import auth, courses` + `app.include_router(courses.router)`。

- [ ] **Step 4: 运行确认通过**

Run: `cd server; pytest tests/test_courses_roster.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add server/
git commit -m "feat(server): 课程创建与花名册 token 管理"
```

---

### Task 5: 作业 CRUD、rubric 校验与公开 meta 端点

**Files:**
- Create: `server/app/api/assignments.py`
- Modify: `server/app/main.py`（注册路由）
- Create: `server/tests/test_assignments.py`

**Interfaces:**
- Consumes: Task 4
- Produces: `POST /courses/{id}/assignments`（rubric 权重和=100 校验；生成唯一 `code`——8 位大写字母数字）；`GET /api/assignments/{code}/meta`（公开，含 spec 全部字段）

- [ ] **Step 1: 写失败测试 test_assignments.py**

```python
# server/tests/test_assignments.py
from datetime import timedelta

from app.utils import utcnow
from tests.test_courses_roster import _login


def _course(client):
    return client.post("/courses", json={"name": "C", "term": ""}).json()["id"]


RUBRIC = [{"name": "prompt质量", "weight": 30, "description": "d"},
          {"name": "迭代策略", "weight": 25, "description": "d"},
          {"name": "调试与问题解决", "weight": 20, "description": "d"},
          {"name": "完成度", "weight": 15, "description": "d"},
          {"name": "代码质量", "weight": 10, "description": "d"}]


def test_create_assignment_and_meta(client):
    _login(client)
    cid = _course(client)
    now = utcnow()
    r = client.post(f"/courses/{cid}/assignments", json={
        "title": "作业3", "description": "做一个网页", "rubric": RUBRIC,
        "opens_at": (now - timedelta(days=1)).isoformat(),
        "deadline": (now + timedelta(days=7)).isoformat(), "max_package_mb": 50})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert len(code) == 8
    r = client.get(f"/api/assignments/{code}/meta")
    assert r.status_code == 200
    m = r.json()
    assert m["title"] == "作业3" and m["accepts"] is True and m["reason"] == ""
    assert m["min_client_version"] == "0.1.0"
    assert m["supported_manifest_versions"] == ["1"]
    assert m["max_package_mb"] == 50


def test_rubric_weight_sum(client):
    _login(client)
    cid = _course(client)
    now = utcnow().isoformat()
    r = client.post(f"/courses/{cid}/assignments", json={
        "title": "X", "description": "", "rubric": [{"name": "a", "weight": 50, "description": ""}],
        "opens_at": now, "deadline": now, "max_package_mb": 50})
    assert r.status_code == 422


def test_meta_after_deadline(client):
    _login(client)
    cid = _course(client)
    now = utcnow()
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "X", "description": "", "rubric": RUBRIC,
        "opens_at": (now - timedelta(days=9)).isoformat(),
        "deadline": (now - timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    m = client.get(f"/api/assignments/{code}/meta").json()
    assert m["accepts"] is False and "截止" in m["reason"]
```

- [ ] **Step 2: 运行确认失败** → 404

- [ ] **Step 3: 实现**

先在 `server/app/deps.py` 追加 settings 依赖：

```python
# server/app/deps.py 追加（顶部 import: from .config import Settings）
def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings
```

再写 `server/app/api/assignments.py`：

```python
# server/app/api/assignments.py
import secrets
import string
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..deps import get_settings_dep, get_teacher
from ..errors import ApiError
from ..utils import utcnow

router = APIRouter()

_ALPHABET = string.ascii_uppercase + string.digits


class RubricItem(BaseModel):
    name: str
    weight: int
    description: str = ""


class AssignmentIn(BaseModel):
    title: str
    description: str = ""
    rubric: list[RubricItem]
    opens_at: datetime
    deadline: datetime
    max_package_mb: int = 50

    @field_validator("rubric")
    @classmethod
    def weights_sum_100(cls, v):
        if not v or sum(i.weight for i in v) != 100:
            raise ValueError("rubric 权重和必须为 100")
        return v


def _new_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        if not db.query(models.Assignment).filter_by(code=code).first():
            return code


@router.post("/courses/{course_id}/assignments")
def create_assignment(course_id: int, body: AssignmentIn, db: Session = Depends(get_db),
                      t: models.Teacher = Depends(get_teacher)):
    if not db.get(models.Course, course_id):
        raise ApiError(404, "NOT_FOUND", "课程不存在")
    a = models.Assignment(
        course_id=course_id, code=_new_code(db), title=body.title,
        description=body.description,
        rubric_json=[i.model_dump() for i in body.rubric],
        opens_at=body.opens_at.replace(tzinfo=None),
        deadline=body.deadline.replace(tzinfo=None),
        max_package_mb=body.max_package_mb)
    db.add(a)
    db.commit()
    return {"id": a.id, "code": a.code}


@router.get("/api/assignments/{code}/meta")
def assignment_meta(code: str, db: Session = Depends(get_db),
                    s=Depends(get_settings_dep)):
    a = db.query(models.Assignment).filter_by(code=code).first()
    if not a:
        raise ApiError(404, "NOT_FOUND", "作业码不存在")
    now = utcnow()
    accepts, reason = True, ""
    if now < a.opens_at:
        accepts, reason = False, "作业未开放"
    elif now > a.deadline:
        accepts, reason = False, "已过截止时间"
    return {
        "title": a.title,
        "opens_at": a.opens_at.isoformat(),
        "deadline": a.deadline.isoformat(),
        "max_package_mb": a.max_package_mb,
        "accepts": accepts,
        "reason": reason,
        "min_client_version": s.min_client_version,
        "supported_manifest_versions": s.supported_manifest_versions,
    }
```

main.py 注册：`from .api import assignments` + `app.include_router(assignments.router)`。

- [ ] **Step 4: 运行确认通过**

Run: `cd server; pytest tests/test_assignments.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add server/
git commit -m "feat(server): 作业创建、rubric 校验与公开 meta 端点"
```

---

### Task 6: 学生 Bearer 认证与速率限制

**Files:**
- Modify: `server/app/deps.py`
- Create: `server/tests/test_student_auth.py`

**Interfaces:**
- Consumes: Task 3 的 `hash_token`、Task 4 的花名册
- Produces: `get_student(request, db) -> Student`（401）；`rate_limit(request)`（429，每分钟 N 次/IP）

- [ ] **Step 1: 写失败测试 test_student_auth.py**

```python
# server/tests/test_student_auth.py
from tests.test_courses_roster import _login


def _mk_student(client):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    body = client.post(f"/courses/{cid}/roster",
                       json={"csv": "学号,姓名,小组\n1,甲,G\n"}).json()
    return body["tokens_csv"].splitlines()[1].split(",")[2]


def test_bearer_auth(client):
    token = _mk_student(client)
    assert client.get("/api/student/ping").status_code == 401
    assert client.get("/api/student/ping",
                      headers={"Authorization": "Bearer vs_wrong"}).status_code == 401
    r = client.get("/api/student/ping", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["student_no"] == "1"


def test_rate_limit(client, settings):
    token = _mk_student(client)
    h = {"Authorization": f"Bearer {token}"}
    n = settings.rate_limit_per_minute
    for _ in range(n):
        assert client.get("/api/student/ping", headers=h).status_code == 200
    assert client.get("/api/student/ping", headers=h).status_code == 429
```

- [ ] **Step 2: 运行确认失败** → 404

- [ ] **Step 3: 实现（deps.py 追加 + 临时 ping 端点）**

```python
# server/app/deps.py 顶部追加 import
import time
from collections import defaultdict, deque

from fastapi import Request

from .security import hash_token


# 追加：
def get_student(request: Request, db: Session = Depends(get_db)) -> models.Student:
    rate_limit(request)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少 Bearer token")
    s = db.query(models.Student).filter_by(submit_token_hash=hash_token(auth[7:])).first()
    if not s:
        raise ApiError(401, "UNAUTHORIZED", "token 无效或已重置")
    return s


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    limit = request.app.state.settings.rate_limit_per_minute
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    dq = _hits[ip]
    while dq and dq[0] < now - 60:
        dq.popleft()
    if len(dq) >= limit:
        raise ApiError(429, "RATE_LIMITED", "请求过于频繁，请稍后重试")
    dq.append(now)
```

```python
# server/app/api/auth.py 追加（学生端自检端点，后续任务复用）
from ..deps import get_student


@router.get("/api/student/ping")
def student_ping(s: models.Student = Depends(get_student)):
    return {"student_no": s.student_no, "name": s.name}
```

注意测试隔离问题：`rate_limit` 的 `_hits` 是模块级字典，跨测试共享。在 `conftest.py` 的 `client` fixture 中加一行清理：

```python
from app import deps


@pytest.fixture()
def client(settings):
    deps._hits.clear()
    app = create_app(settings)
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server; pytest tests/test_student_auth.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add server/
git commit -m "feat(server): 学生 Bearer 认证与速率限制"
```

---

### Task 7: ZIP 安全校验模块（纯函数）

**Files:**
- Create: `server/app/services/zipcheck.py`
- Create: `server/tests/test_zipcheck.py`

**Interfaces:**
- Consumes: `Settings`
- Produces: `ZipReject(Exception)`；`validate_zip(zip_path: str, manifest_files: list[dict], s: Settings) -> None`（manifest_files = manifest["files"]，元素 `{"path","sha256"}`）；`safe_extract(zip_path: str, dest_dir: str) -> None`

- [ ] **Step 1: 写失败测试 test_zipcheck.py**

```python
# server/tests/test_zipcheck.py
import hashlib
import io
import json
import zipfile

import pytest

from app.config import Settings
from app.services.zipcheck import ZipReject, safe_extract, validate_zip

S = Settings()


def _mk_zip(tmp_path, entries: dict[str, bytes], name="p.zip", symlink=None) -> str:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        for n, b in entries.items():
            z.writestr(n, b)
        if symlink:
            info = zipfile.ZipInfo("link")
            info.external_attr = 0o120777 << 16
            z.writestr(info, symlink)
    return str(p)


def _manifest(entries: dict[str, bytes]):
    return [{"path": n, "sha256": hashlib.sha256(b).hexdigest()} for n, b in entries.items()]


GOOD = {"manifest.json": b"{}", "sessions/a.jsonl": b"hello", "code/main.py": b"print(1)"}


def test_ok(tmp_path):
    z = _mk_zip(tmp_path, GOOD)
    files = _manifest({k: v for k, v in GOOD.items() if k != "manifest.json"})
    validate_zip(z, files, S)  # 不抛异常
    dest = tmp_path / "out"
    safe_extract(z, str(dest))
    assert (dest / "code/main.py").read_bytes() == b"print(1)"


def test_traversal_rejected(tmp_path):
    z = _mk_zip(tmp_path, {"../evil.txt": b"x", "manifest.json": b"{}"})
    with pytest.raises(ZipReject):
        validate_zip(z, [], S)


def test_absolute_rejected(tmp_path):
    z = _mk_zip(tmp_path, {"/etc/passwd": b"x", "manifest.json": b"{}"})
    with pytest.raises(ZipReject):
        validate_zip(z, [], S)


def test_symlink_rejected(tmp_path):
    z = _mk_zip(tmp_path, dict(GOOD), symlink="/etc/passwd")
    files = _manifest({k: v for k, v in GOOD.items() if k != "manifest.json"})
    with pytest.raises(ZipReject):
        validate_zip(z, files, S)


def test_duplicate_rejected(tmp_path):
    p = tmp_path / "d.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("a.txt", b"1")
        z.writestr("a.txt", b"2")
    with pytest.raises(ZipReject):
        validate_zip(str(p), [], S)


def test_limits(tmp_path):
    big = b"x" * (S.max_file_mb * 1024 * 1024 + 1)
    z = _mk_zip(tmp_path, {"big.bin": big, "manifest.json": b"{}"})
    with pytest.raises(ZipReject):
        validate_zip(z, [], S)
    many = {f"f{i}.txt": b"x" for i in range(S.max_files + 1)}
    many["manifest.json"] = b"{}"
    z2 = _mk_zip(tmp_path, many, name="m.zip")
    with pytest.raises(ZipReject):
        validate_zip(z2, [], S)


def test_manifest_set_and_hash(tmp_path):
    z = _mk_zip(tmp_path, GOOD)
    with pytest.raises(ZipReject):  # 缺文件
        validate_zip(z, [], S)
    bad = _manifest({k: v for k, v in GOOD.items() if k != "manifest.json"})
    bad[0]["sha256"] = "0" * 64
    with pytest.raises(ZipReject):  # 哈希不符
        validate_zip(z, bad, S)
```

- [ ] **Step 2: 运行确认失败** → 模块不存在

- [ ] **Step 3: 实现 zipcheck.py**

```python
# server/app/services/zipcheck.py
import hashlib
import os
import zipfile

from ..config import Settings


class ZipReject(Exception):
    """上传包安全校验失败（→ 422）。"""


def _check_name(name: str, seen: set) -> str:
    n = name.replace("\\", "/")
    if n.startswith("/") or (len(n) > 1 and n[1] == ":"):
        raise ZipReject(f"绝对路径: {name}")
    parts = n.split("/")
    if ".." in parts:
        raise ZipReject(f"路径穿越: {name}")
    if n in seen:
        raise ZipReject(f"重复路径: {name}")
    seen.add(n)
    return n


def validate_zip(zip_path: str, manifest_files: list[dict], s: Settings) -> None:
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise ZipReject(f"非法 zip: {e}")
    infos = zf.infolist()
    if len(infos) > s.max_files:
        raise ZipReject(f"文件数量超限: {len(infos)}")
    seen: set = set()
    total = 0
    for info in infos:
        _check_name(info.filename, seen)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise ZipReject(f"符号链接: {info.filename}")
        if info.file_size > s.max_file_mb * 1024 * 1024:
            raise ZipReject(f"单文件超限: {info.filename}")
        total += info.file_size
        if info.compress_size > 0 and info.file_size / info.compress_size > s.max_compression_ratio:
            raise ZipReject(f"压缩比异常: {info.filename}")
    if total > s.max_uncompressed_mb * 1024 * 1024:
        raise ZipReject(f"总解压大小超限: {total}")
    # manifest 集合一致 + SHA-256 回查
    entries = {i.filename.replace("\\", "/") for i in infos}
    declared = {f["path"] for f in manifest_files}
    if "manifest.json" not in entries:
        raise ZipReject("包内缺少 manifest.json")
    if entries - {"manifest.json"} != declared:
        raise ZipReject("manifest 文件集合与包内容不一致")
    hashes = {f["path"]: f["sha256"] for f in manifest_files}
    for info in infos:
        n = info.filename.replace("\\", "/")
        if n == "manifest.json":
            continue
        digest = hashlib.sha256(zf.read(info)).hexdigest()
        if digest != hashes.get(n):
            raise ZipReject(f"SHA-256 不符: {n}")


def safe_extract(zip_path: str, dest_dir: str) -> None:
    dest = os.path.realpath(dest_dir)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            n = info.filename.replace("\\", "/")
            target = os.path.realpath(os.path.join(dest, n))
            if not target.startswith(dest + os.sep):
                raise ZipReject(f"解压路径越界: {n}")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    out.write(src.read())
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server; pytest tests/test_zipcheck.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add server/
git commit -m "feat(server): 上传包 ZIP 安全校验模块"
```

---

### Task 8: 上传端点（校验链、force/409、落盘、attempt、eval_job 入队）

**Files:**
- Create: `server/app/services/packages.py`
- Create: `server/app/services/jobs.py`
- Create: `server/app/api/submissions.py`
- Modify: `server/app/main.py`（注册路由）
- Create: `server/tests/test_submissions_upload.py`

**Interfaces:**
- Consumes: Task 3–7 全部
- Produces: `POST /api/submissions`（spec §4 契约完整实现）；`enqueue_individual(db, assignment_id, attempt_id)`；`store_package(s, assignment_id, student_id, attempt_id, tmp_zip) -> str`；manifest 解析模型 `ManifestIn`

- [ ] **Step 1: 写失败测试 test_submissions_upload.py**

```python
# server/tests/test_submissions_upload.py
import hashlib
import io
import json
import zipfile

from app.db import SessionLocal
from app import models
from tests.test_courses_roster import _login


def _setup(client, code=None):
    _login(client)
    cid = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    body = client.post(f"/courses/{cid}/roster",
                       json={"csv": "学号,姓名,小组\n1,甲,G\n"}).json()
    token = body["tokens_csv"].splitlines()[1].split(",")[2]
    from datetime import timedelta
    from app.utils import utcnow
    now = utcnow()
    code = client.post(f"/courses/{cid}/assignments", json={
        "title": "A", "description": "", "rubric": [{"name": "x", "weight": 100, "description": ""}],
        "opens_at": (now - timedelta(days=1)).isoformat(),
        "deadline": (now + timedelta(days=1)).isoformat(), "max_package_mb": 50}).json()["code"]
    return token, code


def _package(code, client_version="0.1.0", fmt="1"):
    files = {"sessions/a.jsonl": b"hello", "code/main.py": b"print(1)"}
    manifest = {
        "format_version": fmt, "assignment_code": code, "student_no": "1",
        "client_version": client_version, "submitted_at": "2026-07-19T08:00:00Z",
        "files": [{"path": n, "sha256": hashlib.sha256(b).hexdigest()} for n, b in files.items()],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for n, b in files.items():
            z.writestr(n, b)
    return manifest, buf.getvalue()


def _upload(client, token, code, force=None, **kw):
    manifest, blob = _package(code, **kw)
    data = {"manifest": json.dumps(manifest, ensure_ascii=False)}
    if force:
        data["force"] = "true"
    return client.post("/api/submissions",
                       headers={"Authorization": f"Bearer {token}"},
                       data=data, files={"file": ("p.zip", blob, "application/zip")})


def test_upload_ok_then_409_then_force(client):
    token, code = _setup(client)
    r = _upload(client, token, code)
    assert r.status_code == 201, r.text
    assert r.json()["attempt_no"] == 1
    r = _upload(client, token, code)
    assert r.status_code == 409
    r = _upload(client, token, code, force="true")
    assert r.status_code == 201 and r.json()["attempt_no"] == 2
    db = SessionLocal()
    assert db.query(models.SubmissionAttempt).count() == 2
    assert db.query(models.EvalJob).filter_by(kind="individual", status="queued").count() == 2
    sub = db.query(models.Submission).one()
    assert sub.status == "queued"
    db.close()


def test_upload_rejections(client):
    token, code = _setup(client)
    assert client.post("/api/submissions", data={}, files={}).status_code == 401
    r = _upload(client, token, code, client_version="0.0.1")
    assert r.status_code == 426 and r.json()["error"]["code"] == "CLIENT_OUTDATED"
    r = _upload(client, token, code, fmt="99")
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_MANIFEST_VERSION"
    r = client.post("/api/submissions", headers={"Authorization": f"Bearer {token}"},
                    data={"manifest": json.dumps({"format_version": "1", "assignment_code": "NOPE1234",
                                                  "student_no": "1", "client_version": "0.1.0",
                                                  "submitted_at": "x", "files": []})},
                    files={"file": ("p.zip", _package(code)[1], "application/zip")})
    assert r.status_code == 404
```

- [ ] **Step 2: 运行确认失败** → 404

- [ ] **Step 3: 实现**

```python
# server/app/services/packages.py
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
```

```python
# server/app/services/jobs.py
from sqlalchemy.orm import Session

from .. import models


def enqueue_individual(db: Session, assignment_id: int, attempt_id: int) -> models.EvalJob:
    job = models.EvalJob(assignment_id=assignment_id, kind="individual",
                         target_id=attempt_id, status="queued", attempts=0)
    db.add(job)
    return job
```

```python
# server/app/api/submissions.py
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
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


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
    a = db.query(models.Assignment).filter_by(code=m.assignment_code).first()
    if not a:
        raise ApiError(404, "NOT_FOUND", "作业码不存在")
    if a.course_id != student.course_id:
        raise ApiError(422, "WRONG_COURSE", "该作业不属于你的课程")
    if utcnow() > a.deadline:
        raise ApiError(422, "DEADLINE_PASSED", "已过截止时间")
    # 落临时文件（大小受限）
    limit = a.max_package_mb * 1024 * 1024
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=s.data_dir, suffix=".zip")
    size = 0
    try:
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
        enqueue_individual(db, a.id, att.id)
        db.commit()
        return {"submission_id": sub.id, "attempt_no": attempt_no}
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
```

main.py 注册：`from .api import submissions` + `app.include_router(submissions.router)`。

- [ ] **Step 4: 运行确认通过**

Run: `cd server; pytest tests/test_submissions_upload.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add server/
git commit -m "feat(server): 上传端点与 eval_job 入队"
```

---

### Task 9: 提交状态端点与端到端串联

**Files:**
- Modify: `server/app/api/submissions.py`
- Create: `server/tests/test_status.py`

**Interfaces:**
- Consumes: Task 8
- Produces: `GET /api/submissions/status?assignment_code=X`（Bearer；返回 spec §4 字段；`status` 枚举 `none|received|queued|evaluating|evaluated|failed`——P3 会推进 evaluating/evaluated/failed，本任务映射 received/queued）

- [ ] **Step 1: 写失败测试 test_status.py**

```python
# server/tests/test_status.py
from tests.test_submissions_upload import _setup, _upload


def test_status_flow(client):
    token, code = _setup(client)
    h = {"Authorization": f"Bearer {token}"}
    r = client.get(f"/api/submissions/status?assignment_code={code}", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "none"
    _upload(client, token, code)
    r = client.get(f"/api/submissions/status?assignment_code={code}", headers=h)
    body = r.json()
    assert body["status"] == "queued"
    assert body["assignment_code"] == code
    assert body["submission_id"] > 0 and body["size_bytes"] > 0
    assert body["submitted_at"]
    assert client.get("/api/submissions/status?assignment_code=NOPE1234",
                      headers=h).status_code == 404
```

- [ ] **Step 2: 运行确认失败** → 404

- [ ] **Step 3: 实现（submissions.py 追加）**

```python
@router.get("/api/submissions/status")
def submission_status(assignment_code: str,
                      student: models.Student = Depends(get_student),
                      db: Session = Depends(get_db)):
    a = db.query(models.Assignment).filter_by(code=assignment_code).first()
    if not a:
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
```

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `cd server; pytest -v`
Expected: 全部通过（≥19 个测试）

- [ ] **Step 5: Commit**

```bash
git add server/
git commit -m "feat(server): 提交状态端点；P2 核心完成"
```

---

## Self-Review 记录

- **spec 覆盖**：§4 全部数据表（Task 2）、学生端 API 三端点 + token 管理（Task 5/8/9/4）、ZIP 校验（Task 7）、教师认证与花名册（Task 3/4）、版本协商（Task 5/8）、错误码语义（贯穿，Task 8 测试覆盖 401/404/409/422/426/429）。eval_jobs 仅入队与模型（worker 属 P3）；教师页面、rubric 编辑器 UI、展示视图属 P4。
- **占位符扫描**：无 TBD/TODO；所有测试与实现均为完整可运行代码。
- **类型一致**：`ManifestIn`、`ZipReject`、`enqueue_individual(db, assignment_id, attempt_id)`、`get_student/get_teacher/get_settings_dep`、`Settings` 字段名跨任务一致；`status` 枚举值（none/received/queued/...）与 spec §4 一致。
