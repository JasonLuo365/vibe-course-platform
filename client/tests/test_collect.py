import pytest
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


def test_collect_excludes_dirs(make_project):
    root = make_project(
        files={
            "src/main.py": "x",
            ".git/config": "g",
            "node_modules/x/y.js": "y",
            "dist/app.js": "d",
        }
    )
    files, skipped = collect_project(root)
    rels = {f.relpath for f in files}
    assert rels == {"src/main.py"}
    assert ".git/config" not in rels
    assert "node_modules/x/y.js" not in rels
    assert "dist/app.js" not in rels


def test_collect_symlink_skipped(make_project):
    root = make_project(files={"real.txt": "data"}, symlink=("real.txt", "link.txt"))
    files, skipped = collect_project(root)
    assert not any(f.relpath == "link.txt" for f in files)


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
