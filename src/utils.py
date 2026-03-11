from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".sql": "sql",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}


def iter_files(repo_root: Path) -> Iterable[Path]:
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if any(part.startswith(".") and part not in (".", "..") for part in p.parts):
            # skip hidden dirs/files broadly (.git, .venv, .cartography, etc.)
            if ".cartography" in p.parts:
                continue
            if ".git" in p.parts:
                continue
        if p.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield p


def relpath_posix(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def guess_language(path: Path) -> str:
    return SUPPORTED_EXTENSIONS.get(path.suffix.lower(), "unknown")


def file_mtime(path: Path):
    return path.stat().st_mtime


def is_probably_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(2048)
        return b"\x00" in chunk
    except OSError:
        return True

