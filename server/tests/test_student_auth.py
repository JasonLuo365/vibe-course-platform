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


def test_rate_limit_uses_forwarded_ip_only_when_enabled(client, settings):
    settings.trust_proxy_headers = True
    settings.rate_limit_per_minute = 1
    token = _mk_student(client)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/student/ping", headers={**h, "X-Forwarded-For": "203.0.113.10"}).status_code == 200
    assert client.get("/api/student/ping", headers={**h, "X-Forwarded-For": "203.0.113.11"}).status_code == 200

