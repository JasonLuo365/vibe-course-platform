import hashlib
import json
import zipfile
from datetime import datetime, timezone

from vibe_submit.collect import FileEntry
from vibe_submit.package import build_package
from vibe_submit.sessions import SessionInfo


def test_package_zip_structure_and_manifest(make_session, make_project, tmp_path):
    project = make_project(files={"main.py": "print('hi')", "screenshot.png": "png"})
    session_path = make_session(
        session_id="sess-1", cwd=str(project), timestamp="2026-07-19T10:00:00Z"
    )
    session = SessionInfo(
        path=session_path,
        session_id="sess-1",
        cwd=str(project),
        started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
    )
    code = [FileEntry("main.py", project / "main.py", (project / "main.py").stat().st_size)]
    shots = [
        FileEntry(
            "screenshot.png",
            project / "screenshot.png",
            (project / "screenshot.png").stat().st_size,
        )
    ]
    meta = {"assignment_code": "HW01", "student_no": "2026001"}
    zip_path, manifest, stats = build_package(
        project, [session], code, shots, meta, tmp_path / "dest"
    )

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert names >= {
            "manifest.json",
            "sessions/sess-1.jsonl",
            "sessions_index.json",
            "code/main.py",
            "screenshots/screenshot.png",
        }
        for item in manifest["files"]:
            data = zf.read(item["path"])
            assert hashlib.sha256(data).hexdigest() == item["sha256"]

    assert manifest["format_version"] == "1"
    assert manifest["assignment_code"] == "HW01"
    assert manifest["student_no"] == "2026001"
    assert manifest["client_version"] == "0.1.0"
    assert stats["sessions"] == 1
    assert stats["files"] == 2
    assert stats["bytes"] == sum(e.size for e in code + shots)


def test_package_sessions_index_content(make_session, make_project, tmp_path):
    project = make_project(files={"main.py": "x"})
    lines = [
        {
            "type": "response_item",
            "payload": {
                "role": "user",
                "content": "hi",
                "timestamp": "2026-07-19T10:05:00Z",
            },
        }
    ]
    session_path = make_session(
        session_id="sess-2", cwd=str(project), timestamp="2026-07-19T10:00:00Z", lines=lines
    )
    session = SessionInfo(
        path=session_path,
        session_id="sess-2",
        cwd=str(project),
        started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
    )
    zip_path, manifest, _stats = build_package(
        project, [session], [], [], {"assignment_code": "HW02", "student_no": "2026002"}, tmp_path / "dest"
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        index = json.loads(zf.read("sessions_index.json").decode("utf-8"))
    assert index["sess-2"]["message_count"] == 1
    assert index["sess-2"]["ended_at"] == "2026-07-19T10:05:00Z"
