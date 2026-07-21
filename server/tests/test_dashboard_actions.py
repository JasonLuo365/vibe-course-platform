from datetime import timedelta

from app.utils import utcnow
from tests.test_auth import _mk_teacher


def _login(client):
    _mk_teacher()
    assert client.post("/login", json={"username": "admin", "password": "pw123456"}).status_code == 200


def test_dashboard_only_offers_evaluation_prompt(client):
    _login(client)
    course_id = client.post("/courses", json={"name": "C", "term": ""}).json()["id"]
    now = utcnow()
    assignment = client.post(
        f"/courses/{course_id}/assignments",
        json={
            "title": "A",
            "description": "",
            "rubric": [{"name": "完成度", "weight": 100, "description": ""}],
            "opens_at": (now - timedelta(days=1)).isoformat(),
            "deadline": (now + timedelta(days=1)).isoformat(),
        },
    ).json()

    page = client.get("/")
    assert "评估提示词" in page.text
    assert "更多操作" not in page.text
    assert "课堂作品展示" not in page.text
    assert "评价展示" not in page.text
    assert "下载 CSV" not in page.text

    board = client.get(f"/assignments/{assignment['id']}/board")
    assert "topbar-back" not in board.text
    assert "作品展示" not in board.text
    assert "评价展示" not in board.text

    assert client.get(f"/assignments/{assignment['id']}/present").status_code == 404
    assert client.get(f"/assignments/{assignment['id']}/review-present").status_code == 404
    assert client.get(f"/assignments/{assignment['id']}/export.csv").status_code == 404
