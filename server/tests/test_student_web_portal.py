from app import models
from app import db as database
from app.db import SessionLocal
from app.security import hash_token
from sqlalchemy import create_engine, inspect, text
from datetime import datetime, timezone


def _mk_student(student_no='20260001', token='vs-student-token'):
    db = SessionLocal()
    course = models.Course(name='Vibe Coding', term='2026')
    db.add(course)
    db.flush()
    group = models.Group(course_id=course.id, name='第一组')
    db.add(group)
    db.flush()
    student = models.Student(
        course_id=course.id,
        group_id=group.id,
        student_no=student_no,
        name='张三',
        submit_token_hash=hash_token(token),
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    student_id = student.id
    db.close()
    return student_id


def test_login_page_exposes_teacher_and_student_roles(client):
    response = client.get('/login')

    assert response.status_code == 200
    assert 'teacher-login-panel' in response.text
    assert 'student-login-panel' in response.text
    assert 'student_no' in response.text
    assert 'submit_token' in response.text
    assert '/student/login' in response.text


def test_student_login_accepts_student_number_and_token(client):
    _mk_student()

    response = client.post(
        '/student/login',
        json={'student_no': '20260001', 'submit_token': 'vs-student-token'},
    )

    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert 'session=' in response.headers.get('set-cookie', '')


def test_student_login_rejects_invalid_credentials(client):
    _mk_student()

    response = client.post(
        '/student/login',
        json={'student_no': '20260001', 'submit_token': 'wrong-token'},
    )

    assert response.status_code == 401
    assert response.json()['error']['code'] == 'UNAUTHORIZED'


def test_student_logout_clears_student_session(client):
    _mk_student()
    client.post(
        '/student/login',
        json={'student_no': '20260001', 'submit_token': 'vs-student-token'},
    )

    response = client.post('/student/logout')

    assert response.status_code == 200
    assert response.json() == {'ok': True}


def test_existing_sqlite_database_gets_student_session_version_once(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE students ("
                "id INTEGER PRIMARY KEY, "
                "student_no TEXT NOT NULL, "
                "submit_token_hash TEXT NOT NULL)"
            )
        )
    monkeypatch.setattr(database, '_engine', engine)

    database._upgrade_existing_schema()
    database._upgrade_existing_schema()

    columns = [column['name'] for column in inspect(engine).get_columns('students')]
    assert columns.count('web_session_version') == 1
    with engine.connect() as connection:
        value = connection.execute(
            text('SELECT web_session_version FROM students')
        ).fetchone()
    assert value is None


def _mk_student_with_assignment(student_no='20260002', token='vs-dashboard-token'):
    db = SessionLocal()
    course = models.Course(name='Vibe Coding', term='2026')
    db.add(course)
    db.flush()
    group = models.Group(course_id=course.id, name='第二组')
    db.add(group)
    db.flush()
    student = models.Student(
        course_id=course.id,
        group_id=group.id,
        student_no=student_no,
        name='李四',
        submit_token_hash=hash_token(token),
    )
    db.add(student)
    assignment = models.Assignment(
        course_id=course.id,
        code='DASHBOARD01',
        title='响应式网页设计',
        description='完成课程作业',
        rubric_json=[],
        opens_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        deadline=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    db.add(assignment)
    db.commit()
    student_id = student.id
    db.close()
    return student_id


def test_student_dashboard_shows_identity_group_assignment_and_status(client):
    _mk_student_with_assignment()
    client.post(
        '/student/login',
        json={'student_no': '20260002', 'submit_token': 'vs-dashboard-token'},
    )

    response = client.get('/student')

    assert response.status_code == 200
    assert '李四' in response.text
    assert '20260002' in response.text
    assert '第二组' in response.text
    assert '响应式网页设计' in response.text
    assert '尚未提交' in response.text


def test_student_dashboard_requires_student_session(client):
    response = client.get('/student', follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.headers['location']
