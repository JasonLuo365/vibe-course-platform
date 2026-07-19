import hashlib
import io
import json
import zipfile

import pytest

from app.config import Settings
from app.services.zipcheck import ZipReject, safe_extract, validate_zip

S = Settings()


def _mk_zip(tmp_path, entries: dict[str, bytes], name="p.zip", symlink=None) -> str:
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        for n, b in entries.items():
            z.writestr(n, b)
        if symlink:
            info = zipfile.ZipInfo("link")
            info.external_attr = 0o120777 << 16
            z.writestr(info, symlink)
    return str(p)


def _manifest(entries: dict[str, bytes]):
    return [{"path": n, "sha256": hashlib.sha256(b).hexdigest()} for n, b in entries.items()]


GOOD = {"manifest.json": b"{}", "sessions/a.jsonl": b"hello", "code/main.py": b"print(1)"}


def test_ok(tmp_path):
    z = _mk_zip(tmp_path, GOOD)
    files = _manifest({k: v for k, v in GOOD.items() if k != "manifest.json"})
    validate_zip(z, files, S)  # 不抛异常
    dest = tmp_path / "out"
    safe_extract(z, str(dest))
    assert (dest / "code/main.py").read_bytes() == b"print(1)"


def test_traversal_rejected(tmp_path):
    z = _mk_zip(tmp_path, {"../evil.txt": b"x", "manifest.json": b"{}"})
    with pytest.raises(ZipReject):
        validate_zip(z, [], S)


def test_absolute_rejected(tmp_path):
    z = _mk_zip(tmp_path, {"/etc/passwd": b"x", "manifest.json": b"{}"})
    with pytest.raises(ZipReject):
        validate_zip(z, [], S)


def test_symlink_rejected(tmp_path):
    z = _mk_zip(tmp_path, dict(GOOD), symlink="/etc/passwd")
    files = _manifest({k: v for k, v in GOOD.items() if k != "manifest.json"})
    with pytest.raises(ZipReject):
        validate_zip(z, files, S)


def test_duplicate_rejected(tmp_path):
    p = tmp_path / "d.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("a.txt", b"1")
        z.writestr("a.txt", b"2")
    with pytest.raises(ZipReject):
        validate_zip(str(p), [], S)


def test_limits(tmp_path):
    big = b"x" * (S.max_file_mb * 1024 * 1024 + 1)
    z = _mk_zip(tmp_path, {"big.bin": big, "manifest.json": b"{}"})
    with pytest.raises(ZipReject):
        validate_zip(z, [], S)
    many = {f"f{i}.txt": b"x" for i in range(S.max_files + 1)}
    many["manifest.json"] = b"{}"
    z2 = _mk_zip(tmp_path, many, name="m.zip")
    with pytest.raises(ZipReject):
        validate_zip(z2, [], S)


def test_manifest_set_and_hash(tmp_path):
    z = _mk_zip(tmp_path, GOOD)
    with pytest.raises(ZipReject):  # 缺文件
        validate_zip(z, [], S)
    bad = _manifest({k: v for k, v in GOOD.items() if k != "manifest.json"})
    bad[0]["sha256"] = "0" * 64
    with pytest.raises(ZipReject):  # 哈希不符
        validate_zip(z, bad, S)
