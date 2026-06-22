"""Tests for skills.adapt.lib.templates — PR/issue/comment templates with dedup key embedding."""
from __future__ import annotations

import pytest

from skills.adapt.lib.idempotency import compute_dedup_key, format_footer, parse_footer
from skills.adapt.lib.templates import (
    REQUIRED_LABELS,
    agent_resume_comment,
    closing_summary,
    dedup_comment,
    issue_body,
    issue_title,
    pr_body,
    pr_title,
)


# ---------------------------------------------------------------------------
# pr_title
# ---------------------------------------------------------------------------

def test_pr_title_contains_metadata():
    """pr_title returns a string containing run_id, phase, attempt, validator."""
    result = pr_title("run-abc", 2, 1, "phase2-conversion", "base")
    assert "run-abc" in result
    assert "phase-2" in result
    assert "attempt-1" in result
    assert "phase2-conversion" in result


def test_pr_title_kind_fix():
    """pr_title with kind='fix' includes 'fix' in the title."""
    result = pr_title("run-abc", 2, 1, "phase2-conversion", "fix")
    assert "fix" in result


def test_pr_title_no_validator():
    """pr_title without validator does not include empty parens."""
    result = pr_title("run-abc", 2, 1, "", "base")
    assert "()" not in result


# ---------------------------------------------------------------------------
# pr_body
# ---------------------------------------------------------------------------

def test_pr_body_fixes_issue():
    """pr_body with fixes_issue=5 contains 'Fixes #5' (exact GitHub-recognized syntax)."""
    result = pr_body("run1", 2, 0, "fix", "loss-diff", "changed X", fixes_issue=5)
    assert "Fixes #5" in result


def test_pr_body_without_fixes_issue():
    """pr_body without fixes_issue does NOT contain 'Fixes'."""
    result = pr_body("run1", 2, 0, "base", "", "")
    assert "Fixes #" not in result


def test_pr_body_includes_idempotency_footer():
    """pr_body includes idempotency footer via format_footer."""
    result = pr_body("run1", 2, 0, "base", "", "")
    parsed = parse_footer(result)
    assert parsed is not None
    assert parsed.run_id == "run1"
    assert parsed.phase == 2
    assert parsed.attempt == 0


def test_pr_body_sections():
    """pr_body contains Summary, Validator, Diff Summary, Linked Issue sections."""
    result = pr_body("run1", 2, 0, "fix", "loss-diff", "changed X", fixes_issue=5)
    assert "## Summary" in result
    assert "## Validator" in result
    assert "## Diff Summary" in result
    assert "## Linked Issue" in result


# ---------------------------------------------------------------------------
# issue_title
# ---------------------------------------------------------------------------

def test_issue_title_format():
    """issue_title returns a string containing phase, validator_name, failure_kind."""
    result = issue_title(2, "loss-diff", "numerical_mismatch")
    assert "phase-2" in result
    assert "loss-diff" in result
    assert "numerical_mismatch" in result


# ---------------------------------------------------------------------------
# issue_body
# ---------------------------------------------------------------------------

def test_issue_body_contains_failure_signature():
    """issue_body contains structured '## Failure Signature' section."""
    sig = {"kind": "numerical_mismatch", "location": "model.py:L42", "expected": "0.01", "actual": "0.5"}
    result = issue_body(2, "loss-diff", sig, "error log", "http://example/attempts.jsonl", "python test.py")
    assert "## Failure Signature" in result
    assert "numerical_mismatch" in result
    assert "model.py:L42" in result
    assert "0.01" in result
    assert "0.5" in result


def test_issue_body_contains_required_sections():
    """issue_body contains Log Excerpt, Attempts Log, Reproduction sections."""
    sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
    result = issue_body(2, "loss-diff", sig, "error log", "http://example/attempts.jsonl", "python test.py")
    assert "## Log Excerpt" in result
    assert "## Attempts Log" in result
    assert "## Reproduction" in result
    assert "http://example/attempts.jsonl" in result
    assert "python test.py" in result


def test_issue_body_with_nonempty_failure_signature_has_dedup_key():
    """issue_body with non-empty failure_signature contains '[dedup-key: ' followed by 64-char hex."""
    sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
    result = issue_body(2, "loss-diff", sig, "error log", "http://example/attempts.jsonl", "python test.py")
    assert "[dedup-key: " in result
    # Extract the hex after "[dedup-key: "
    import re
    match = re.search(r"\[dedup-key: ([a-f0-9]{64})\]", result)
    assert match is not None, "dedup key hex not found in issue body"
    # Verify it matches compute_dedup_key
    expected = compute_dedup_key(2, "loss-diff", sig)
    assert match.group(1) == expected


def test_issue_body_empty_failure_signature_no_dedup_key():
    """issue_body with empty failure_signature dict does NOT contain '[dedup-key:'."""
    result = issue_body(2, "loss-diff", {}, "error log", "http://example/attempts.jsonl", "python test.py")
    assert "[dedup-key:" not in result


def test_issue_body_includes_idempotency_footer():
    """issue_body includes idempotency footer via format_footer."""
    sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
    result = issue_body(2, "loss-diff", sig, "error log", "http://example/attempts.jsonl", "python test.py",
                        run_id="run1", attempt=3)
    parsed = parse_footer(result)
    assert parsed is not None
    assert parsed.run_id == "run1"
    assert parsed.phase == 2
    assert parsed.attempt == 3
    assert parsed.action == "issue"


# ---------------------------------------------------------------------------
# dedup_comment
# ---------------------------------------------------------------------------

def test_dedup_comment_format():
    """dedup_comment returns a string containing attempt number, log excerpt, timestamp."""
    result = dedup_comment(3, "last 10 lines...", "2026-06-22T10:00:00Z")
    assert "attempt-3" in result or "Attempt 3" in result
    assert "last 10 lines..." in result
    assert "2026-06-22T10:00:00Z" in result


# ---------------------------------------------------------------------------
# agent_resume_comment
# ---------------------------------------------------------------------------

def test_agent_resume_comment_format():
    """agent_resume_comment returns a string containing '/agent-resume' and run_id and phase."""
    result = agent_resume_comment("run-abc", 2)
    assert "/agent-resume" in result
    assert "run-abc" in result
    assert "2" in result


# ---------------------------------------------------------------------------
# closing_summary
# ---------------------------------------------------------------------------

def test_closing_summary_format():
    """closing_summary returns a string containing run_id, phase, outcome."""
    result = closing_summary("run-abc", 2, "validator_passed")
    assert "run-abc" in result
    assert "phase-2" in result or "2" in result
    assert "validator_passed" in result


# ---------------------------------------------------------------------------
# REQUIRED_LABELS
# ---------------------------------------------------------------------------

def test_required_labels():
    """REQUIRED_LABELS is a list containing 'loongforge-adapt'."""
    assert isinstance(REQUIRED_LABELS, list)
    assert "loongforge-adapt" in REQUIRED_LABELS
