def test_login_page_exposes_teacher_and_student_roles(client):
    response = client.get('/login')

    assert response.status_code == 200
    assert 'teacher-login-panel' in response.text
    assert 'student-login-panel' in response.text
    assert 'student_no' in response.text
    assert 'submit_token' in response.text
    assert '/student/login' in response.text
