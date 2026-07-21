import hashlib
import os
import zipfile

from ..config import Settings


class ZipReject(Exception):
    """上传包安全校验失败（→ 422）。"""


def _check_name(name: str, seen: set) -> str:
    n = name.replace("\\", "/")
    if n.startswith("/") or (len(n) > 1 and n[1] == ":"):
        raise ZipReject(f"绝对路径: {name}")
    parts = n.split("/")
    if ".." in parts:
        raise ZipReject(f"路径穿越: {name}")
    if n in seen:
        raise ZipReject(f"重复路径: {name}")
    seen.add(n)
    return n


def validate_zip(zip_path: str, manifest_files: list[dict], s: Settings) -> None:
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
            if len(infos) > s.max_files:
                raise ZipReject(f"文件数量超限: {len(infos)}")
            seen: set = set()
            total = 0
            for info in infos:
                _check_name(info.filename, seen)
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ZipReject(f"符号链接: {info.filename}")
                if info.file_size > s.max_file_mb * 1024 * 1024:
                    raise ZipReject(f"单文件超限: {info.filename}")
                total += info.file_size
                if info.compress_size > 0 and info.file_size / info.compress_size > s.max_compression_ratio:
                    raise ZipReject(f"压缩比异常: {info.filename}")
            if total > s.max_uncompressed_mb * 1024 * 1024:
                raise ZipReject(f"总解压大小超限: {total}")
            # manifest 集合一致 + SHA-256 回查
            entries = {i.filename.replace("\\", "/") for i in infos}
            declared = {f["path"] for f in manifest_files}
            if "manifest.json" not in entries:
                raise ZipReject("包内缺少 manifest.json")
            if entries - {"manifest.json"} != declared:
                raise ZipReject("manifest 文件集合与包内容不一致")
            hashes = {f["path"]: f["sha256"] for f in manifest_files}
            for info in infos:
                n = info.filename.replace("\\", "/")
                if n == "manifest.json":
                    continue
                digest = hashlib.sha256(zf.read(info)).hexdigest()
                if digest != hashes.get(n):
                    raise ZipReject(f"SHA-256 不符: {n}")
    except zipfile.BadZipFile as e:
        raise ZipReject(f"非法 zip: {e}")


def safe_extract(zip_path: str, dest_dir: str) -> None:
    dest = os.path.realpath(dest_dir)
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            n = info.filename.replace("\\", "/")
            target = os.path.realpath(os.path.join(dest, n))
            if not target.startswith(dest + os.sep):
                raise ZipReject(f"解压路径越界: {n}")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    out.write(src.read())
