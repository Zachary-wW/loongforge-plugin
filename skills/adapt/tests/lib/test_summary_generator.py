"""Tests for summary_generator.py — comprehension and per-phase summary generators (DOC-04)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """Create a synthetic run directory with phase subdirectories."""
    rd = tmp_path / "adaptation_run_20260623"
    for i in range(6):
        (rd / "phases" / f"phase{i}").mkdir(parents=True, exist_ok=True)
    return rd


def _write_loop_state(
    phase_dir: Path,
    attempt: int = 1,
    exit_reason: str = "validator_passed",
    merge_commit_sha: str | None = None,
    last_validator_summary: dict | None = None,
) -> None:
    """Write a synthetic loop_state.yml."""
    data = {
        "phase": int(phase_dir.name.replace("phase", "")),
        "attempt": attempt,
        "current_state": "exit",
        "exit_reason": exit_reason,
        "run_start_time": "2026-06-23T00:00:00+00:00",
        "total_attempts_used": attempt,
        "pr_number": 1,
        "fix_pr_number": None,
        "issue_number": None,
        "validator_hash": None,
        "loong_megatron_sha": None,
        "last_validator_summary": last_validator_summary,
        "issues_opened": [],
        "issues_closed": [],
        "merge_commit_sha": merge_commit_sha,
        "head_sha": None,
    }
    (phase_dir / "loop_state.yml").write_text(
        yaml.dump(data, sort_keys=False, default_flow_style=False)
    )


def _write_attempts_jsonl(
    phase_dir: Path,
    kinds: list[str],
    attempt: int = 1,
) -> None:
    """Write a synthetic attempts.jsonl."""
    lines = []
    for i, kind in enumerate(kinds):
        row = {
            "ts": f"2026-06-23T00:{i:02d}:00+00:00",
            "attempt": attempt,
            "kind": kind,
            "pr_url": "",
            "issue_url": "",
            "validator": "",
            "verdict": "passed" if kind == "validate" and i == len(kinds) - 1 else "",
            "exit_reason": "",
            "event_id": f"fake-event-{i}",
        }
        lines.append(json.dumps(row))
    (phase_dir / "attempts.jsonl").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Test 1: Phase summary with full loop data + merge_commit_sha
# ---------------------------------------------------------------------------

def test_generate_phase_summary_with_loop_data(run_dir: Path):
    from skills.adapt.lib.summary_generator import generate_phase_summary

    phase_dir = run_dir / "phases" / "phase1"
    _write_loop_state(
        phase_dir,
        attempt=3,
        exit_reason="validator_passed_after_fix",
        merge_commit_sha="abc1234",
        last_validator_summary={"name": "phase1-verify", "status": "passed"},
    )
    _write_attempts_jsonl(
        phase_dir,
        kinds=["probe", "edit", "validate", "diagnose", "fix_pr", "validate"],
        attempt=3,
    )

    result = generate_phase_summary(run_dir, 1)
    assert "Phase 1" in result
    assert "validator_passed_after_fix" in result
    assert "3 attempts" in result
    assert "phase1-verify" in result
    assert "abc1234" in result


# ---------------------------------------------------------------------------
# Test 2: Phase summary without loop_state.yml (legacy mode)
# ---------------------------------------------------------------------------

def test_generate_phase_summary_no_loop_data(run_dir: Path):
    from skills.adapt.lib.summary_generator import generate_phase_summary

    result = generate_phase_summary(run_dir, 1)
    assert "no loop data" in result or "legacy" in result.lower() or "not yet" in result.lower()


# ---------------------------------------------------------------------------
# Test 3: Phase summary with merge_commit_sha = None (base_only exit)
# ---------------------------------------------------------------------------

def test_generate_phase_summary_no_merge_sha(run_dir: Path):
    from skills.adapt.lib.summary_generator import generate_phase_summary

    phase_dir = run_dir / "phases" / "phase1"
    _write_loop_state(
        phase_dir,
        attempt=1,
        exit_reason="base_only",
        merge_commit_sha=None,
    )
    _write_attempts_jsonl(phase_dir, kinds=["probe", "edit", "pr", "merge_base", "validate"], attempt=1)

    result = generate_phase_summary(run_dir, 1)
    assert "N/A" in result or "(none)" in result.lower()


# ---------------------------------------------------------------------------
# Test 4: Comprehension summary with 2 phases + merge_commit_sha
# ---------------------------------------------------------------------------

def test_generate_comprehension_summary_multi_phase(run_dir: Path):
    from skills.adapt.lib.summary_generator import generate_comprehension_summary

    # Phase 1: passed on attempt 1
    p1_dir = run_dir / "phases" / "phase1"
    _write_loop_state(
        p1_dir,
        attempt=1,
        exit_reason="validator_passed",
        merge_commit_sha="sha1",
        last_validator_summary={"name": "phase1-verify", "status": "passed"},
    )
    _write_attempts_jsonl(p1_dir, kinds=["probe", "edit", "pr", "merge_base", "validate"], attempt=1)

    # Phase 3: passed after fix on attempt 4
    p3_dir = run_dir / "phases" / "phase3"
    _write_loop_state(
        p3_dir,
        attempt=4,
        exit_reason="validator_passed_after_fix",
        merge_commit_sha="sha2",
        last_validator_summary={"name": "loss-diff", "status": "passed"},
    )
    _write_attempts_jsonl(
        p3_dir,
        kinds=["probe", "edit", "validate", "diagnose", "issue", "fix_pr", "review", "merge_fix", "rerun"],
        attempt=4,
    )

    result = generate_comprehension_summary(run_dir)
    # Must contain a table or list of phases
    assert "Phase 1" in result
    assert "Phase 3" in result
    assert "sha1" in result
    assert "sha2" in result
    # Total attempts: 1 + 4 = 5
    assert "5" in result


# ---------------------------------------------------------------------------
# Test 5: Comprehension summary with empty run_dir (no phases executed)
# ---------------------------------------------------------------------------

def test_generate_comprehension_summary_empty(run_dir: Path):
    from skills.adapt.lib.summary_generator import generate_comprehension_summary

    result = generate_comprehension_summary(run_dir)
    assert "no phases" in result.lower() or "0" in result


# ---------------------------------------------------------------------------
# Test 6: Phase summary includes decision_log.md content
# ---------------------------------------------------------------------------

def test_generate_phase_summary_with_decision_log(run_dir: Path):
    from skills.adapt.lib.summary_generator import generate_phase_summary

    phase_dir = run_dir / "phases" / "phase1"
    _write_loop_state(
        phase_dir,
        attempt=1,
        exit_reason="validator_passed",
        merge_commit_sha="sha1",
        last_validator_summary={"name": "phase1-verify", "status": "passed"},
    )
    _write_attempts_jsonl(phase_dir, kinds=["probe", "edit", "validate"], attempt=1)

    # Write a decision_log.md
    decision_content = "- Chose approach A over B due to performance\n- Used squash merge for cleaner history"
    (phase_dir / "decision_log.md").write_text(decision_content)

    result = generate_phase_summary(run_dir, 1)
    assert "Decisions" in result
    assert "approach A" in result


# ---------------------------------------------------------------------------
# Test 7: CLI invocation writes summaries to disk
# ---------------------------------------------------------------------------

def test_cli_invocation(run_dir: Path):
    from skills.adapt.lib.summary_generator import generate_comprehension_summary

    # Write loop data for at least one phase so the CLI has something to do
    p1_dir = run_dir / "phases" / "phase1"
    _write_loop_state(
        p1_dir,
        attempt=1,
        exit_reason="validator_passed",
        merge_commit_sha="sha1",
        last_validator_summary={"name": "phase1-verify", "status": "passed"},
    )
    _write_attempts_jsonl(p1_dir, kinds=["probe", "edit", "validate"], attempt=1)

    # Use write_summaries directly then verify files
    from skills.adapt.lib.summary_generator import write_summaries
    write_summaries(run_dir)

    assert (run_dir / "comprehension_summary.md").exists()
    assert (run_dir / "phases" / "phase1" / "phase1_summary.md").exists()

    # Verify content has the merge_commit_sha
    comp = (run_dir / "comprehension_summary.md").read_text()
    assert "sha1" in comp

    phase_sum = (run_dir / "phases" / "phase1" / "phase1_summary.md").read_text()
    assert "sha1" in phase_sum
