"""Tests for skills.adapt.lib.jsonl — append-only JSONL writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from skills.adapt.lib.jsonl import append_attempt, assert_append_only


def test_append_attempt_creates_file_with_newline(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    append_attempt(path, {"k": "v"})
    data = path.read_bytes()
    assert data.endswith(b"\n")


def test_append_attempt_three_records(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    append_attempt(path, {"attempt": 1})
    append_attempt(path, {"attempt": 2})
    append_attempt(path, {"attempt": 3})
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 3


def test_assert_append_only_succeeds_for_correct_count(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    for i in range(3):
        append_attempt(path, {"i": i})
    # Should NOT raise
    assert_append_only(path, expected_min_lines=3)


def test_assert_append_only_raises_for_excessive_count(tmp_path: Path):
    path = tmp_path / "a.jsonl"
    for i in range(3):
        append_attempt(path, {"i": i})
    with pytest.raises(AssertionError):
        assert_append_only(path, expected_min_lines=4)


def test_assert_append_only_raises_for_missing_file(tmp_path: Path):
    path = tmp_path / "nonexistent.jsonl"
    with pytest.raises(AssertionError):
        assert_append_only(path, expected_min_lines=1)


def test_o_append_survives_external_truncation(tmp_path: Path):
    """After truncation, the next append_attempt still produces a valid line."""
    path = tmp_path / "a.jsonl"
    append_attempt(path, {"before": "truncate"})
    # Truncate externally
    path.write_bytes(b"")
    append_attempt(path, {"after": "truncate"})
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1
    assert path.read_bytes().endswith(b"\n")
