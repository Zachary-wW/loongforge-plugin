"""Tests for skills.adapt.lib.idempotency — SHA256 key, footer format/parse, dedup key."""
from __future__ import annotations

import hashlib

import pytest

from skills.adapt.lib.idempotency import (
    IdempotencyFooter,
    compute_dedup_key,
    compute_idempotency_key,
    format_footer,
    parse_footer,
)


# ---------------------------------------------------------------------------
# compute_idempotency_key
# ---------------------------------------------------------------------------

def test_compute_idempotency_key_returns_64_char_hex():
    """compute_idempotency_key returns a 64-char lowercase hex string."""
    result = compute_idempotency_key("run1", 1, 0, "base-pr")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_compute_idempotency_key_deterministic():
    """Same inputs always produce the same output."""
    a = compute_idempotency_key("run1", 1, 0, "base-pr")
    b = compute_idempotency_key("run1", 1, 0, "base-pr")
    assert a == b


def test_compute_idempotency_key_different_inputs():
    """Different inputs produce different outputs."""
    a = compute_idempotency_key("run1", 1, 0, "base-pr")
    b = compute_idempotency_key("run2", 1, 0, "base-pr")
    c = compute_idempotency_key("run1", 2, 0, "base-pr")
    d = compute_idempotency_key("run1", 1, 1, "base-pr")
    e = compute_idempotency_key("run1", 1, 0, "fix-pr")
    assert a != b
    assert a != c
    assert a != d
    assert a != e


def test_compute_idempotency_key_matches_raw_sha256():
    """Verify the implementation matches the spec: sha256(f"{run_id}:{phase}:{attempt}:{action_kind}")."""
    raw = "run1:1:0:base-pr"
    expected = hashlib.sha256(raw.encode()).hexdigest()
    assert compute_idempotency_key("run1", 1, 0, "base-pr") == expected


# ---------------------------------------------------------------------------
# format_footer
# ---------------------------------------------------------------------------

def test_format_footer_contains_html_comment():
    """format_footer returns a string containing '<!-- adapt-skill:' and the key hex."""
    result = format_footer("run1", 1, 0, "base-pr")
    assert "<!-- adapt-skill:" in result


def test_format_footer_includes_metadata():
    """format_footer output includes run=run1, phase=1, attempt=0, action=base-pr."""
    result = format_footer("run1", 1, 0, "base-pr")
    assert "run=run1" in result
    assert "phase=1" in result
    assert "attempt=0" in result
    assert "action=base-pr" in result


def test_format_footer_includes_visible_key_fallback():
    """format_footer includes a visible [adapt-skill-key: ...] fallback line."""
    key = compute_idempotency_key("run1", 1, 0, "base-pr")
    result = format_footer("run1", 1, 0, "base-pr")
    assert f"[adapt-skill-key: {key}]" in result


def test_format_footer_visible_line_before_html_comment():
    """The visible fallback line appears immediately before the HTML comment."""
    result = format_footer("run1", 1, 0, "base-pr")
    lines = result.strip().split("\n")
    # Find the HTML comment line
    html_idx = None
    for i, line in enumerate(lines):
        if "<!-- adapt-skill:" in line:
            html_idx = i
            break
    assert html_idx is not None
    assert html_idx > 0  # there is a line before it
    assert "[adapt-skill-key:" in lines[html_idx - 1]


# ---------------------------------------------------------------------------
# parse_footer
# ---------------------------------------------------------------------------

def test_parse_footer_extracts_fields():
    """parse_footer on a body containing format_footer returns IdempotencyFooter with correct fields."""
    body = "Some PR body\n" + format_footer("run1", 1, 0, "base-pr")
    result = parse_footer(body)
    assert result is not None
    assert isinstance(result, IdempotencyFooter)
    assert result.run_id == "run1"
    assert result.phase == 1
    assert result.attempt == 0
    assert result.action == "base-pr"
    assert len(result.key) == 64


def test_parse_footer_no_footer_returns_none():
    """parse_footer on a body with no footer returns None."""
    assert parse_footer("Just a regular body with no footer") is None


def test_parse_footer_multiple_footers_returns_first():
    """parse_footer on a body with multiple footers returns the first one."""
    footer1 = format_footer("run1", 1, 0, "base-pr")
    footer2 = format_footer("run2", 2, 1, "fix-pr")
    body = footer1 + "\nSome text\n" + footer2
    result = parse_footer(body)
    assert result is not None
    assert result.run_id == "run1"
    assert result.phase == 1


# ---------------------------------------------------------------------------
# Round-trip: compute_idempotency_key ↔ format_footer ↔ parse_footer
# ---------------------------------------------------------------------------

def test_round_trip_key_matches():
    """Key from compute_idempotency_key matches key parsed from format_footer output."""
    expected_key = compute_idempotency_key("run-abc", 3, 2, "fix-pr")
    body = format_footer("run-abc", 3, 2, "fix-pr")
    parsed = parse_footer(body)
    assert parsed is not None
    assert parsed.key == expected_key


# ---------------------------------------------------------------------------
# compute_dedup_key
# ---------------------------------------------------------------------------

def test_compute_dedup_key_returns_64_char_hex():
    """compute_dedup_key returns a 64-char lowercase hex string."""
    result = compute_dedup_key(2, "loss-diff", {"kind": "numerical_mismatch", "location": "model.py:L42"})
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_compute_dedup_key_deterministic():
    """Same (phase, validator, kind, location) always produces same key."""
    sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
    a = compute_dedup_key(2, "loss-diff", sig)
    b = compute_dedup_key(2, "loss-diff", sig)
    assert a == b


def test_compute_dedup_key_different_signatures():
    """Different (kind, location) pairs produce different keys even with same phase and validator."""
    sig1 = {"kind": "numerical_mismatch", "location": "model.py:L42"}
    sig2 = {"kind": "shape_mismatch", "location": "model.py:L42"}
    sig3 = {"kind": "numerical_mismatch", "location": "model.py:L99"}
    a = compute_dedup_key(2, "loss-diff", sig1)
    b = compute_dedup_key(2, "loss-diff", sig2)
    c = compute_dedup_key(2, "loss-diff", sig3)
    assert a != b
    assert a != c
    assert b != c


def test_compute_dedup_key_empty_signature():
    """compute_dedup_key with empty failure_signature values still returns a valid 64-char hex."""
    result = compute_dedup_key(1, "phase1-verify", {})
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_compute_dedup_key_empty_strings():
    """compute_dedup_key with kind='' and location='' still returns valid hex."""
    result = compute_dedup_key(1, "phase1-verify", {"kind": "", "location": ""})
    assert len(result) == 64


def test_compute_dedup_key_different_from_idempotency_key():
    """Dedup key and idempotency key serve different purposes and produce different outputs."""
    dedup = compute_dedup_key(2, "loss-diff", {"kind": "numerical_mismatch", "location": "model.py:L42"})
    idempotency = compute_idempotency_key("run1", 2, 0, "issue")
    assert dedup != idempotency


def test_compute_dedup_key_matches_spec():
    """Verify compute_dedup_key matches spec: sha256(f"{phase}:{validator}:{kind}:{location}")."""
    phase = 2
    validator = "loss-diff"
    sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
    raw = f"{phase}:{validator}:{sig.get('kind', '')}:{sig.get('location', '')}"
    expected = hashlib.sha256(raw.encode()).hexdigest()
    assert compute_dedup_key(phase, validator, sig) == expected
