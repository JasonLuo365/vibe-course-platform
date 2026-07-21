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


def _mk_submission_with_feedback():
    db = SessionLocal()
    course = models.Course(name='Vibe Coding', term='2026')
    db.add(course)
    db.flush()
    group = models.Group(course_id=course.id, name='第三组')
    db.add(group)
    db.flush()
    student = models.Student(
        course_id=course.id,
        group_id=group.id,
        student_no='20260003',
        name='王五',
        submit_token_hash=hash_token('vs-feedback-token'),
    )
    classmate = models.Student(
        course_id=course.id,
        group_id=group.id,
        student_no='20260004',
        name='赵六',
        submit_token_hash=hash_token('vs-classmate-token'),
    )
    db.add_all([student, classmate])
    assignment = models.Assignment(
        course_id=course.id,
        code='FEEDBACK01',
        title='交互式课程项目',
        description='完成课程项目',
        rubric_json=[],
        opens_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        deadline=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    db.add(assignment)
    db.flush()
    submission = models.Submission(
        assignment_id=assignment.id,
        student_id=student.id,
        status='done',
    )
    db.add(submission)
    db.flush()
    attempt = models.SubmissionAttempt(
        submission_id=submission.id,
        attempt_no=1,
        package_path='packages/feedback.zip',
        size_bytes=1024,
        manifest_version='1.0',
        status='done',
    )
    db.add(attempt)
    db.flush()
    submission.current_attempt_id = attempt.id
    evaluation = models.Evaluation(
        attempt_id=attempt.id,
        grade='B',
        dimension_scores_json=[{'name': '完成度', 'score': 82, 'weight': 100, 'rationale': '功能完整'}],
        rationale='个人评语：交互流程清晰，建议补充异常状态。',
        feedback_json=['补充表单校验', '增加移动端测试'],
        flags_json=[],
        evidence_json=[],
        model='test',
        prompt_version='test',
    )
    db.add(evaluation)
    group_evaluation = models.GroupEvaluation(
        assignment_id=assignment.id,
        group_id=group.id,
        generation=1,
        grade='A',
        rationale='小组评语：整体方案完成度高，分工协作顺畅。',
        contribution_json={'members': []},
        evidence_json=[],
    )
    db.add(group_evaluation)
    db.commit()
    result = (student.id, classmate.id, submission.id)
    db.close()
    return result


def _login_student(client, student_no, token):
    response = client.post(
        '/student/login',
        json={'student_no': student_no, 'submit_token': token},
    )
    assert response.status_code == 200


def test_student_can_view_personal_and_group_feedback(client):
    _student_id, _classmate_id, submission_id = _mk_submission_with_feedback()
    _login_student(client, '20260003', 'vs-feedback-token')

    response = client.get(f'/student/submissions/{submission_id}')

    assert response.status_code == 200
    assert '个人评语：交互流程清晰' in response.text
    assert '补充表单校验' in response.text
    assert '小组评语：整体方案完成度高' in response.text
    assert 'A' in response.text


def test_student_cannot_view_another_students_feedback(client):
    _student_id, _classmate_id, submission_id = _mk_submission_with_feedback()
    _login_student(client, '20260004', 'vs-classmate-token')

    response = client.get(f'/student/submissions/{submission_id}')

    assert response.status_code == 404


def test_student_page_session_is_invalidated_when_session_version_changes(client):
    student_id = _mk_student('20260005', 'vs-version-token')
    _login_student(client, '20260005', 'vs-version-token')
    db = SessionLocal()
    student = db.get(models.Student, student_id)
    student.web_session_version += 1
    db.commit()
    db.close()

    response = client.get('/student', follow_redirects=False)

    assert response.status_code == 302
    assert '/login' in response.headers['location']
