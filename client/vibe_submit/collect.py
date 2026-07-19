"""Project file collection."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import CollectError

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES = 5000
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50 MB

# Denylist patterns for file names.
_FILE_DENYLIST = [
    ".env*",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.ppk",
    "id_rsa*",
    ".netrc",
    ".git-credentials",
    "*.kubeconfig",
    "*credentials*",
    "*secret*",
]

# Denylist patterns for directory names.
_DIR_DENYLIST = [
    ".ssh",
    ".aws",
    ".azure",
    ".gnupg",
    ".kube",
    "*credentials*",
    "*secret*",
]

# Directories excluded entirely (not recorded in skipped).
_EXCLUDE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


@dataclass(frozen=True)
class FileEntry:
    relpath: str  # POSIX relative path inside project root
    abspath: Path
    size: int


def _matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def collect_project(root: Path) -> tuple[list[FileEntry], list[str]]:
    """Collect project files, applying denylist and size/count limits.

    Returns ``(files, skipped)`` where ``skipped`` contains POSIX relative paths
    of denylisted files and directories.

    Raises ``CollectError`` if a single file exceeds ``MAX_FILE_SIZE``, or if
    the project exceeds ``MAX_FILES`` or ``MAX_TOTAL_SIZE``.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise CollectError(f"project root is not a directory: {root}")

    files: list[FileEntry] = []
    skipped: list[str] = []
    total_bytes = 0
    file_count = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirpath_obj = Path(dirpath)
        rel_dir = dirpath_obj.relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""

        # Filter directories first so we do not descend into excluded/denylisted ones.
        for dirname in sorted(list(dirnames)):
            child = dirpath_obj / dirname
            if os.path.islink(child):
                dirnames.remove(dirname)
                continue
            if dirname in _EXCLUDE_DIRS:
                dirnames.remove(dirname)
                continue
            if _matches(dirname, _DIR_DENYLIST):
                skipped.append(f"{rel_dir}/{dirname}" if rel_dir else dirname)
                dirnames.remove(dirname)

        for filename in sorted(filenames):
            child = dirpath_obj / filename
            if os.path.islink(child):
                # Symbolic links are never followed/copied.
                continue

            relpath = f"{rel_dir}/{filename}" if rel_dir else filename

            if _matches(filename, _FILE_DENYLIST):
                skipped.append(relpath)
                continue

            size = child.stat().st_size
            if size > MAX_FILE_SIZE:
                raise CollectError(
                    f"file exceeds 10MB limit: {relpath} ({size} bytes)"
                )

            file_count += 1
            if file_count > MAX_FILES:
                raise CollectError(f"project exceeds {MAX_FILES} file limit")

            total_bytes += size
            if total_bytes > MAX_TOTAL_SIZE:
                raise CollectError(
                    f"project exceeds 50MB total limit ({total_bytes} bytes)"
                )

            files.append(FileEntry(relpath=relpath, abspath=child, size=size))

    return files, skipped
