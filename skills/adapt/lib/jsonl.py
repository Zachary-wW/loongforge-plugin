"""Append-only JSONL writer for attempts.jsonl.

Uses O_APPEND + fsync for atomic line writes. Single-writer design (sequential
loop controller) — no file-level locking needed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def append_attempt(path: str | Path, record: dict[str, Any]) -> None:
    """Atomically append one JSON line. O_APPEND prevents truncation races."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def assert_append_only(path: str | Path, expected_min_lines: int) -> None:
    """Test helper: assert file has at least N lines and last byte is newline."""
    p = Path(path)
    if not p.exists():
        raise AssertionError(f"{p} does not exist")
    data = p.read_bytes()
    if expected_min_lines > 0 and not data.endswith(b"\n"):
        raise AssertionError(f"{p} does not end with newline (partial write?)")
    n_lines = data.count(b"\n")
    if n_lines < expected_min_lines:
        raise AssertionError(f"{p} has {n_lines} lines, expected >= {expected_min_lines}")
