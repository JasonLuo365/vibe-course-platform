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
