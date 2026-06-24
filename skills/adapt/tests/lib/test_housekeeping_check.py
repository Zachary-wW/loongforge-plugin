"""Tests for housekeeping_check.py — bot artifact label + stranded issue verification (ROADMAP criterion 4)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml
import pytest

from skills.adapt.lib.housekeeping_check import check_artifact_labels, run_housekeeping_check


# ---------------------------------------------------------------------------
# check_artifact_labels pure function tests
# ---------------------------------------------------------------------------

def test_all_required_labels_present():
    assert check_artifact_labels(["loongforge-adapt", "run-abc123", "phase-1"], ["loongforge-adapt"]) == []


def test_missing_loongforge_adapt_label():
    assert check_artifact_labels(["run-abc123", "phase-1"], ["loongforge-adapt"]) == ["loongforge-adapt"]


def test_missing_run_label():
    assert check_artifact_labels(["loongforge-adapt"], ["loongforge-adapt", "run-abc123"]) == ["run-abc123"]


def test_empty_actual_labels():
    assert check_artifact_labels([], ["loongforge-adapt", "run-abc123"]) == ["loongforge-adapt", "run-abc123"]


# ---------------------------------------------------------------------------
# run_housekeeping_check tests
# ---------------------------------------------------------------------------

def test_dry_run_returns_true_no_subprocess(tmp_path: Path):
    """dry_run=True returns (True, []) without any subprocess calls."""
    run_dir = tmp_path / "adaptation_run_test"
    for i in range(7):
        (run_dir / "phases" / f"phase{i}").mkdir(parents=True, exist_ok=True)
    # Write a loop_state.yml with fake data
    phase1_dir = run_dir / "phases" / "phase1"
    data = {
        "phase": 1, "attempt": 1, "current_state": "exit",
        "exit_reason": "validator_passed", "pr_number": 99,
        "issue_number": 42, "run_start_time": "2026-06-23T00:00:00+00:00",
        "total_attempts_used": 1,
    }
    (phase1_dir / "loop_state.yml").write_text(yaml.dump(data, default_flow_style=False))

    with patch("skills.adapt.lib.housekeeping_check.subprocess.run") as mock_run:
        ok, errs = run_housekeeping_check(run_dir, "owner/repo", dry_run=True)
        assert ok is True
        assert errs == []
        mock_run.assert_not_called()


def test_run_housekeeping_check_pass(tmp_path: Path):
    """Live check with all labels present and issues closed."""
    run_dir = tmp_path / "adaptation_run_test"
    phase1_dir = run_dir / "phases" / "phase1"
    phase1_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "phase": 1, "attempt": 1, "current_state": "exit",
        "exit_reason": "validator_passed", "pr_number": 10,
        "issue_number": 20, "run_start_time": "2026-06-23T00:00:00+00:00",
        "total_attempts_used": 1,
    }
    (phase1_dir / "loop_state.yml").write_text(yaml.dump(data, default_flow_style=False))

    mock_pr_view = MagicMock(returncode=0, stdout='{"labels":[{"name":"loongforge-adapt"},{"name":"run-adaptation_run_test"},{"name":"phase-1"}],"state":"MERGED"}')
    mock_issue_view = MagicMock(returncode=0, stdout='{"labels":[{"name":"loongforge-adapt"},{"name":"run-adaptation_run_test"},{"name":"phase-1"}],"state":"CLOSED"}')

    def fake_run(cmd, **kwargs):
        if "pr" in cmd[:3] and "view" in cmd:
            return mock_pr_view
        return mock_issue_view

    with patch("skills.adapt.lib.housekeeping_check.subprocess.run", side_effect=fake_run):
        ok, errs = run_housekeeping_check(run_dir, "owner/repo", dry_run=False)
        assert ok is True
        assert errs == []


def test_run_housekeeping_check_fail_missing_label(tmp_path: Path):
    """Live check with missing label should fail."""
    run_dir = tmp_path / "adaptation_run_test"
    phase1_dir = run_dir / "phases" / "phase1"
    phase1_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "phase": 1, "attempt": 1, "current_state": "exit",
        "exit_reason": "validator_passed", "pr_number": 10,
        "issue_number": 20, "run_start_time": "2026-06-23T00:00:00+00:00",
        "total_attempts_used": 1,
    }
    (phase1_dir / "loop_state.yml").write_text(yaml.dump(data, default_flow_style=False))

    # PR missing "loongforge-adapt" label
    mock_pr_view = MagicMock(returncode=0, stdout='{"labels":[{"name":"run-adaptation_run_test"},{"name":"phase-1"}],"state":"MERGED"}')
    mock_issue_view = MagicMock(returncode=0, stdout='{"labels":[{"name":"loongforge-adapt"}],"state":"CLOSED"}')

    def fake_run(cmd, **kwargs):
        if "pr" in cmd[:3] and "view" in cmd:
            return mock_pr_view
        return mock_issue_view

    with patch("skills.adapt.lib.housekeeping_check.subprocess.run", side_effect=fake_run):
        ok, errs = run_housekeeping_check(run_dir, "owner/repo", dry_run=False)
        assert ok is False
        assert len(errs) > 0


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

def test_cli_dry_run():
    """CLI --dry-run exits 0 and prints SKIP."""
    result = subprocess.run(
        [sys.executable, "-m", "skills.adapt.lib.housekeeping_check",
         "--run-dir", "/tmp/fake", "--repo", "owner/repo", "--dry-run"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "SKIP" in result.stdout or "dry-run" in result.stdout.lower()
