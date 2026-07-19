import pytest
from pathlib import Path

from vibe_submit.collect import CollectError, collect_project


def test_collect_includes_regular_files(make_project):
    root = make_project(files={"src/main.py": "hi", "README.md": "hello"})
    files, skipped = collect_project(root)
    rels = {f.relpath for f in files}
    assert rels == {"README.md", "src/main.py"}
    assert skipped == []


def test_collect_skips_denylist_and_records(make_project):
    root = make_project(
        files={".env": "SECRET", "config.key": "k", "src/main.py": "x"}
    )
    files, skipped = collect_project(root)
    rels = {f.relpath for f in files}
    assert rels == {"src/main.py"}
    assert ".env" in skipped
    assert "config.key" in skipped


def test_collect_skips_denylist_case_insensitively_on_windows_style_projects(make_project):
    root = make_project(files={".ENV": "SECRET", "SECRET.KEY": "k", "src/main.py": "x"})
    files, skipped = collect_project(root)
    assert {f.relpath for f in files} == {"src/main.py"}
    assert ".ENV" in skipped
    assert "SECRET.KEY" in skipped


def test_collect_excludes_dirs(make_project):
    root = make_project(
        files={
            "src/main.py": "x",
            ".git/config": "g",
            ".pytest_tmp/oversized-test-fixture.bin": b"x" * (10 * 1024 * 1024 + 1),
            ".pytest_tmp_ops/oversized-test-fixture.bin": b"x" * (10 * 1024 * 1024 + 1),
            "node_modules/x/y.js": "y",
            "dist/app.js": "d",
        }
    )
    files, skipped = collect_project(root)
    rels = {f.relpath for f in files}
    assert rels == {"src/main.py"}
    assert ".git/config" not in rels
    assert ".pytest_tmp/oversized-test-fixture.bin" not in rels
    assert ".pytest_tmp_ops/oversized-test-fixture.bin" not in rels
    assert "node_modules/x/y.js" not in rels
    assert "dist/app.js" not in rels


def test_collect_excludes_directory_case_insensitively(make_project):
    root = make_project(files={".GIT/config": "g", "SRC/main.py": "x"})
    files, _ = collect_project(root)
    assert {f.relpath for f in files} == {"SRC/main.py"}


def test_collect_symlink_skipped(make_project):
    root = make_project(files={"real.txt": "data"}, symlink=("real.txt", "link.txt"))
    files, skipped = collect_project(root)
    assert not any(f.relpath == "link.txt" for f in files)


def test_collect_junction_like_directory_skipped(make_project, monkeypatch):
    root = make_project(files={"junction/secret.txt": "do not collect", "main.py": "ok"})
    import vibe_submit.collect as collect

    monkeypatch.setattr(
        collect.os.path,
        "isjunction",
        lambda path: Path(path).name == "junction",
        raising=False,
    )
    files, _ = collect_project(root)
    assert {f.relpath for f in files} == {"main.py"}


def test_collect_file_too_large(make_project):
    root = make_project(files={"big.bin": b"0" * (10 * 1024 * 1024 + 1)})
    with pytest.raises(CollectError, match="10MB"):
        collect_project(root)


def test_collect_too_many_files(make_project):
    files = {f"{i}.txt": "x" for i in range(5001)}
    root = make_project(files=files)
    with pytest.raises(CollectError, match="5000"):
        collect_project(root)


def test_collect_total_too_large(make_project):
    files = {f"{i}.bin": b"x" * (9 * 1024 * 1024) for i in range(6)}
    root = make_project(files=files)
    with pytest.raises(CollectError, match="50MB"):
        collect_project(root)

