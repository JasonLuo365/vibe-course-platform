def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "environment": "development",
        "worker_enabled": False,
    }

