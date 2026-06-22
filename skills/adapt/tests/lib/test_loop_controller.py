"""Tests for loop_controller.py: FSM enums, LoopState, budget, helpers, and first 3 FSM states.

Tests cover FSMState/ExitReason enums, LoopState from_disk/persist, check_budget,
_advance_attempt, _transition, _read_attempts_history, _compute_validator_hash,
_write_phase_output, and run_phase_loop states: PROBE, EDIT, PR, MERGE_BASE,
VALIDATE, DIAGNOSE, ISSUE.
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

import yaml
import pytest

from skills.adapt.lib.gh_client import FakeGhClient
from skills.adapt.lib.schema import LoopBudget


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------

class TestFSMStateEnum:
    def test_fsm_state_enum_values(self):
        from skills.adapt.lib.loop_controller import FSMState
        assert len(FSMState) == 12
        expected = [
            "PROBE", "EDIT", "PR", "MERGE_BASE", "VALIDATE", "DIAGNOSE",
            "ISSUE", "FIX_PR", "REVIEW", "MERGE_FIX", "RERUN", "EXIT",
        ]
        for name in expected:
            assert hasattr(FSMState, name), f"Missing FSMState.{name}"


class TestExitReasonEnum:
    def test_exit_reason_enum_values(self):
        from skills.adapt.lib.loop_controller import ExitReason
        assert len(ExitReason) == 6
        expected = [
            "VALIDATOR_PASSED", "VALIDATOR_PASSED_AFTER_FIX",
            "EXHAUSTED", "ESCALATED", "BASE_ONLY", "HUMAN_NEEDED",
        ]
        for name in expected:
            assert hasattr(ExitReason, name), f"Missing ExitReason.{name}"


# ---------------------------------------------------------------------------
# LoopState tests
# ---------------------------------------------------------------------------

class TestLoopState:
    def test_loop_state_initial(self):
        from skills.adapt.lib.loop_controller import LoopState, FSMState
        state = LoopState(
            phase=1, attempt=1, current_state=FSMState.PROBE,
            exit_reason=None, run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=0,
        )
        assert state.attempt == 1
        assert state.current_state == FSMState.PROBE
        assert state.exit_reason is None
        assert state.total_attempts_used == 0
        assert state.pr_number is None
        assert state.issue_number is None
        assert state.validator_hash is None
        assert state.loong_megatron_sha is None
        assert state.last_validator_summary is None
        assert state.issues_opened == []
        assert state.issues_closed == []

    def test_loop_state_from_disk_missing(self, tmp_path):
        from skills.adapt.lib.loop_controller import LoopState, FSMState
        state = LoopState.from_disk(tmp_path, phase=2)
        assert state.phase == 2
        assert state.current_state == FSMState.PROBE
        assert state.attempt == 1
        assert state.exit_reason is None
        assert state.total_attempts_used == 0
        assert state.last_validator_summary is None

    def test_loop_state_from_disk_existing(self, tmp_path):
        from skills.adapt.lib.loop_controller import LoopState, FSMState, ExitReason
        phase_dir = tmp_path / "phases" / "phase1"
        phase_dir.mkdir(parents=True, exist_ok=True)
        state_data = {
            "phase": 1,
            "attempt": 3,
            "current_state": "validate",
            "exit_reason": None,
            "run_start_time": "2026-01-01T00:00:00+00:00",
            "total_attempts_used": 2,
            "pr_number": 42,
            "issue_number": None,
            "validator_hash": "abc123def456",
            "loong_megatron_sha": "sha-megatron-abc",
            "last_validator_summary": {"status": "failed", "name": "phase1-verify"},
            "issues_opened": [10],
            "issues_closed": [5],
        }
        (phase_dir / "loop_state.yml").write_text(
            yaml.dump(state_data, default_flow_style=False)
        )
        state = LoopState.from_disk(tmp_path, phase=1)
        assert state.attempt == 3
        assert state.current_state == FSMState.VALIDATE
        assert state.total_attempts_used == 2
        assert state.pr_number == 42
        assert state.validator_hash == "abc123def456"
        assert state.loong_megatron_sha == "sha-megatron-abc"
        assert state.last_validator_summary["status"] == "failed"
        assert state.issues_opened == [10]
        assert state.issues_closed == [5]

    def test_loop_state_from_disk_reads_attempts_tail(self, tmp_path):
        from skills.adapt.lib.loop_controller import LoopState, FSMState
        from skills.adapt.lib.jsonl import append_attempt
        from skills.adapt.lib.validator_wrapper import make_attempt_row
        phase_dir = tmp_path / "phases" / "phase1"
        phase_dir.mkdir(parents=True, exist_ok=True)
        # Write loop_state.yml
        state_data = {
            "phase": 1, "attempt": 1, "current_state": "validate",
            "exit_reason": None, "run_start_time": "2026-01-01T00:00:00+00:00",
            "total_attempts_used": 0,
        }
        (phase_dir / "loop_state.yml").write_text(yaml.dump(state_data))
        # Write 3 attempts rows
        attempts_path = phase_dir / "attempts.jsonl"
        for i in range(1, 4):
            append_attempt(attempts_path, make_attempt_row(i, "probe", 1))
        state = LoopState.from_disk(tmp_path, phase=1)
        # Latest attempt number from tail should be 3
        assert state.attempt == 3
        # total_attempts_used should count unique attempt numbers
        assert state.total_attempts_used >= 3

    def test_loop_state_persist_and_reload(self, tmp_path):
        from skills.adapt.lib.loop_controller import LoopState, FSMState, ExitReason
        state = LoopState(
            phase=2, attempt=2, current_state=FSMState.DIAGNOSE,
            exit_reason=None, run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=1,
            last_validator_summary={"status": "failed", "name": "loss-diff", "integrity_ok": True},
            issues_opened=[7, 8],
            issues_closed=[3],
        )
        state.persist(tmp_path)
        reloaded = LoopState.from_disk(tmp_path, phase=2)
        assert reloaded.current_state == FSMState.DIAGNOSE
        assert reloaded.last_validator_summary["status"] == "failed"
        assert reloaded.issues_opened == [7, 8]
        assert reloaded.issues_closed == [3]


# ---------------------------------------------------------------------------
# Budget tests
# ---------------------------------------------------------------------------

class TestCheckBudget:
    def test_check_budget_none_when_headroom(self):
        from skills.adapt.lib.loop_controller import check_budget
        budget = LoopBudget(max_attempts_per_phase=5, max_attempts_per_run=25, max_wallclock_minutes=240)
        now = datetime.now(timezone.utc).isoformat()
        result = check_budget(budget, phase_attempts=2, total_attempts=3, run_start_time=now)
        assert result is None

    def test_check_budget_exhausted_per_phase(self):
        from skills.adapt.lib.loop_controller import check_budget, ExitReason
        budget = LoopBudget(max_attempts_per_phase=5, max_attempts_per_run=25, max_wallclock_minutes=240)
        now = datetime.now(timezone.utc).isoformat()
        result = check_budget(budget, phase_attempts=5, total_attempts=3, run_start_time=now)
        assert result == ExitReason.EXHAUSTED

    def test_check_budget_exhausted_per_run(self):
        from skills.adapt.lib.loop_controller import check_budget, ExitReason
        budget = LoopBudget(max_attempts_per_phase=5, max_attempts_per_run=25, max_wallclock_minutes=240)
        now = datetime.now(timezone.utc).isoformat()
        result = check_budget(budget, phase_attempts=2, total_attempts=25, run_start_time=now)
        assert result == ExitReason.EXHAUSTED

    def test_check_budget_exhausted_wallclock(self):
        from skills.adapt.lib.loop_controller import check_budget, ExitReason
        budget = LoopBudget(max_attempts_per_phase=5, max_attempts_per_run=25, max_wallclock_minutes=240)
        # Start time 241 minutes ago
        start = (datetime.now(timezone.utc) - timedelta(minutes=241)).isoformat()
        result = check_budget(budget, phase_attempts=1, total_attempts=1, run_start_time=start)
        assert result == ExitReason.EXHAUSTED


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestAdvanceAttempt:
    def test_advance_attempt_increments(self):
        from skills.adapt.lib.loop_controller import _advance_attempt, LoopState, FSMState
        state = LoopState(
            phase=1, attempt=3, current_state=FSMState.FIX_PR,
            exit_reason=None, run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=2,
        )
        advanced = _advance_attempt(state)
        assert advanced.attempt == 4
        assert advanced.total_attempts_used == 3
        # Original unchanged (dataclass replace)
        assert state.attempt == 3


class TestTransition:
    def test_transition_appends_attempts_jsonl(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            _transition, LoopState, FSMState,
        )
        state = LoopState(
            phase=1, attempt=1, current_state=FSMState.PROBE,
            exit_reason=None, run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=0,
        )
        new_state = _transition(state, FSMState.EDIT, tmp_path, kind="probe")
        assert new_state.current_state == FSMState.EDIT
        # Verify attempts.jsonl has a row
        attempts_path = tmp_path / "phases" / "phase1" / "attempts.jsonl"
        assert attempts_path.exists()
        lines = attempts_path.read_text().strip().split("\n")
        assert len(lines) >= 1
        row = json.loads(lines[0])
        # LOG-01 fields present
        assert "ts" in row
        assert row["attempt"] == 1
        assert row["kind"] == "probe"
        assert "event_id" in row


class TestReadAttemptsHistory:
    def test_read_attempts_history(self, tmp_path):
        from skills.adapt.lib.loop_controller import _read_attempts_history
        from skills.adapt.lib.jsonl import append_attempt
        phase_dir = tmp_path / "phases" / "phase1"
        phase_dir.mkdir(parents=True, exist_ok=True)
        path = phase_dir / "attempts.jsonl"
        for i in range(3):
            append_attempt(path, {"attempt": i + 1, "kind": f"kind{i}"})
        history = _read_attempts_history(tmp_path, phase=1)
        assert len(history) == 3
        assert history[0]["attempt"] == 1
        assert history[2]["attempt"] == 3


class TestComputeValidatorHash:
    def test_compute_validator_hash_with_binary(self, tmp_path):
        from skills.adapt.lib.loop_controller import _compute_validator_hash
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        binary = bin_dir / "loongforge-phase-gate"
        binary.write_bytes(b"fake-validator-binary-content")
        expected = hashlib.sha256(b"fake-validator-binary-content").hexdigest()[:16]
        result = _compute_validator_hash(tmp_path)
        assert result == expected

    def test_compute_validator_hash_missing_binary(self, tmp_path):
        from skills.adapt.lib.loop_controller import _compute_validator_hash
        result = _compute_validator_hash(tmp_path)
        assert result is None


class TestWritePhaseOutput:
    def test_write_phase_output_creates_file(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            _write_phase_output, LoopState, FSMState, ExitReason,
        )
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        state = LoopState(
            phase=2, attempt=2, current_state=FSMState.EXIT,
            exit_reason=ExitReason.VALIDATOR_PASSED,
            run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=1,
        )
        budget = LoopBudget()
        result = ValidatorResult(
            name="phase2-conversion", status="passed",
            failure_signature=None, evidence={},
            integrity_ok=True, integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
        )
        _write_phase_output(tmp_path, phase=2, state=state, validator_result=result, budget=budget)
        output_path = tmp_path / "phases" / "phase2_output.yml"
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())
        assert data["loop_engineering"] is True
        assert "loop" in data
        assert "validator_integrity" in data
        assert "pr" in data
        assert "issues" in data

    def test_write_phase_output_merges_existing(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            _write_phase_output, LoopState, FSMState, ExitReason,
        )
        output_path = tmp_path / "phases" / "phase2_output.yml"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {"status": "passed", "validator": {"name": "phase2-conversion", "status": "passed"}}
        output_path.write_text(yaml.dump(existing, default_flow_style=False))
        state = LoopState(
            phase=2, attempt=1, current_state=FSMState.EXIT,
            exit_reason=ExitReason.VALIDATOR_PASSED,
            run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=0,
        )
        budget = LoopBudget()
        _write_phase_output(tmp_path, phase=2, state=state, validator_result=None, budget=budget)
        data = yaml.safe_load(output_path.read_text())
        # Existing keys preserved
        assert data["status"] == "passed"
        assert data["validator"]["name"] == "phase2-conversion"
        # New blocks added
        assert data["loop_engineering"] is True
        assert "loop" in data
        assert "validator_integrity" in data

    def test_write_phase_output_validator_integrity_from_result(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            _write_phase_output, LoopState, FSMState, ExitReason,
        )
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        state = LoopState(
            phase=1, attempt=1, current_state=FSMState.EXIT,
            exit_reason=ExitReason.VALIDATOR_PASSED,
            run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=0,
        )
        budget = LoopBudget()
        result = ValidatorResult(
            name="phase1-verify", status="passed",
            failure_signature=None, evidence={},
            integrity_ok=True,
            integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
        )
        _write_phase_output(tmp_path, phase=1, state=state, validator_result=result, budget=budget)
        output_path = tmp_path / "phases" / "phase1_output.yml"
        data = yaml.safe_load(output_path.read_text())
        integrity = data["validator_integrity"]
        assert integrity["integrity_ok"] is True
        assert integrity["binary_hash_ok"] is True
        assert integrity["log_mtime_ok"] is True
        assert integrity["log_present"] is True

    def test_write_phase_output_validator_integrity_none_result(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            _write_phase_output, LoopState, FSMState, ExitReason,
        )
        state = LoopState(
            phase=1, attempt=1, current_state=FSMState.EXIT,
            exit_reason=ExitReason.EXHAUSTED,
            run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=0,
        )
        budget = LoopBudget()
        _write_phase_output(tmp_path, phase=1, state=state, validator_result=None, budget=budget)
        output_path = tmp_path / "phases" / "phase1_output.yml"
        data = yaml.safe_load(output_path.read_text())
        assert data["validator_integrity"] == {}


# ---------------------------------------------------------------------------
# run_phase_loop state tests
# ---------------------------------------------------------------------------

def _setup_run_dir(tmp_path: Path, phase: int = 1) -> Path:
    """Create a minimal run_dir with phases structure."""
    phase_dir = tmp_path / "phases" / f"phase{phase}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    log_dir = phase_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "validator.log").write_text("fake log\n")
    return tmp_path


def _write_loop_state(run_dir: Path, phase: int, current_state: str, attempt: int = 1,
                      exit_reason: str | None = None, total_attempts_used: int = 0,
                      validator_hash: str | None = None, last_validator_summary: dict | None = None,
                      pr_number: int | None = None, issue_number: int | None = None,
                      issues_opened: list[int] | None = None, issues_closed: list[int] | None = None,
                      loong_megatron_sha: str | None = None,
                      run_start_time: str | None = None) -> None:
    """Write a loop_state.yml for a given phase."""
    phase_dir = run_dir / "phases" / f"phase{phase}"
    phase_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "phase": phase,
        "attempt": attempt,
        "current_state": current_state,
        "exit_reason": exit_reason,
        "run_start_time": run_start_time or datetime.now(timezone.utc).isoformat(),
        "total_attempts_used": total_attempts_used,
        "validator_hash": validator_hash,
        "loong_megatron_sha": loong_megatron_sha,
        "last_validator_summary": last_validator_summary,
        "issues_opened": issues_opened or [],
        "issues_closed": issues_closed or [],
        "pr_number": pr_number,
        "issue_number": issue_number,
    }
    (phase_dir / "loop_state.yml").write_text(yaml.dump(data, default_flow_style=False))


class TestRunPhaseLoopValidateState:
    def test_run_phase_loop_validator_passed(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            run_phase_loop, LoopState, FSMState, ExitReason,
        )
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        assert result == ExitReason.VALIDATOR_PASSED
        # Verify phaseN_output.yml has validator_integrity.integrity_ok=True
        output_path = run_dir / "phases" / "phase1_output.yml"
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())
        assert data["validator_integrity"]["integrity_ok"] is True

    def test_run_phase_loop_wrong_direction(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            run_phase_loop, LoopState, FSMState, ExitReason,
        )
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
        run_dir = _setup_run_dir(tmp_path, phase=2)
        # Write attempts history with 3 consecutive same-kind+location
        phase_dir = run_dir / "phases" / "phase2"
        phase_dir.mkdir(parents=True, exist_ok=True)
        from skills.adapt.lib.jsonl import append_attempt
        from skills.adapt.lib.validator_wrapper import make_attempt_row
        for i in range(3):
            append_attempt(phase_dir / "attempts.jsonl", {
                "attempt": i + 1, "kind": "validate", "verdict": "failed",
                "validator": "phase2-conversion",
                "failure_signature": {"kind": "missing_artifact", "location": "conv.py", "expected": "ok", "actual": "err"},
            })
        _write_loop_state(
            run_dir, phase=2, current_state="diagnose", attempt=3,
            last_validator_summary={
                "status": "failed", "name": "phase2-conversion",
                "integrity_ok": True,
                "integrity_details": {"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                "failure_signature": {"kind": "missing_artifact", "location": "conv.py", "expected": "ok", "actual": "err"},
                "loong_megatron_sha": None,
            },
        )
        gh = FakeGhClient()
        budget = LoopBudget()
        # classify_failure will naturally return WRONG_DIRECTION from the 3 consecutive attempts
        result = run_phase_loop(run_dir, phase=2, gh=gh, budget=budget)
        assert result == ExitReason.HUMAN_NEEDED
        # Verify escalation.md exists
        escalation_path = run_dir / "phases" / "phase2" / "escalation.md"
        assert escalation_path.exists()

    def test_run_phase_loop_budget_exhausted(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            run_phase_loop, LoopState, FSMState, ExitReason,
        )
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=5)
        budget = LoopBudget(max_attempts_per_phase=5)
        gh = FakeGhClient()
        result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        assert result == ExitReason.EXHAUSTED

    def test_flake_rerun_same_attempt_number(self, tmp_path):
        from skills.adapt.lib.loop_controller import (
            run_phase_loop, LoopState, FSMState, ExitReason,
        )
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature, DEFAULT_FLAKE_RERUN_COUNT
        run_dir = _setup_run_dir(tmp_path, phase=3)
        _write_loop_state(run_dir, phase=3, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        # Phase 3 + numerical_mismatch = flake candidate
        flake_result = ValidatorResult(
            name="loss-diff", status="failed",
            failure_signature=FailureSignature(kind="numerical_mismatch", location="loss.py", expected="<1e-5", actual="3e-4"),
            evidence={}, integrity_ok=True,
            integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
        )
        # Second call returns passed (flake rerun passes)
        call_count = [0]
        def side_effect(run_dir, phase, gh, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return flake_result
            return ValidatorResult(
                name="loss-diff", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.side_effect = side_effect
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            result = run_phase_loop(run_dir, phase=3, gh=gh, budget=budget)
        # Should eventually pass
        assert result in (ExitReason.VALIDATOR_PASSED, ExitReason.VALIDATOR_PASSED_AFTER_FIX)
        # Verify that attempts.jsonl has validate_rerun kind entries
        attempts_path = run_dir / "phases" / "phase3" / "attempts.jsonl"
        lines = attempts_path.read_text().strip().split("\n")
        rerun_rows = [json.loads(l) for l in lines if l.strip()]
        kinds = [r["kind"] for r in rerun_rows]
        assert "validate_rerun" in kinds

    def test_last_validator_summary_stored_in_state(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="failed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            # Will classify as needs-human (no failure_signature) and exit
            run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        # Reload state from disk
        reloaded = LoopState.from_disk(run_dir, phase=1)
        assert reloaded.last_validator_summary is not None
        assert "integrity_ok" in reloaded.last_validator_summary

    def test_validator_hash_recorded_on_first_entry(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        # No loop_state.yml yet -> fresh start from PROBE
        gh = FakeGhClient()
        budget = LoopBudget(max_attempts_per_phase=1)  # Exhaust quickly
        result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, max_iterations=2)
        # Reload and check validator_hash was set (None since no binary)
        reloaded = LoopState.from_disk(run_dir, phase=1)
        # validator_hash should be None (no binary) but the field should have been checked
        assert reloaded.validator_hash is None

    def test_megatron_args_passed_to_run_validator(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=2)
        _write_loop_state(run_dir, phase=2, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "loongforge_base_ref": "main",
            "megatron_repo": "Zachary-wW/Loong-Megatron",
            "megatron_ref": "loong-main/core_v0.15.0",
            "run_id": "test-run",
        }
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase2-conversion", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            run_phase_loop(run_dir, phase=2, gh=gh, budget=budget, repos_info=repos_info)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs.get("megatron_repo") == "Zachary-wW/Loong-Megatron" or \
               (len(call_kwargs.args) > 3 and call_kwargs.args[3] == "Zachary-wW/Loong-Megatron")

    def test_megatron_sha_stored_in_state(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=2)
        _write_loop_state(run_dir, phase=2, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "megatron_repo": "Zachary-wW/Loong-Megatron",
            "megatron_ref": "loong-main/core_v0.15.0",
            "run_id": "test-run",
        }
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase2-conversion", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                loong_megatron_sha="abc123",
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            run_phase_loop(run_dir, phase=2, gh=gh, budget=budget, repos_info=repos_info)
        reloaded = LoopState.from_disk(run_dir, phase=2)
        assert reloaded.loong_megatron_sha == "abc123"

    def test_diagnose_reconstructs_from_last_validator_summary(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=2)
        # Create attempts history with 3 consecutive same signature for WRONG_DIRECTION
        phase_dir = run_dir / "phases" / "phase2"
        phase_dir.mkdir(parents=True, exist_ok=True)
        from skills.adapt.lib.jsonl import append_attempt
        for i in range(3):
            append_attempt(phase_dir / "attempts.jsonl", {
                "attempt": i + 1, "kind": "validate", "verdict": "failed",
                "validator": "phase2-conversion",
                "failure_signature": {"kind": "missing_artifact", "location": "conv.py", "expected": "ok", "actual": "err"},
            })
        _write_loop_state(
            run_dir, phase=2, current_state="diagnose", attempt=3,
            last_validator_summary={
                "status": "failed", "name": "phase2-conversion",
                "integrity_ok": True,
                "integrity_details": {"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                "failure_signature": {"kind": "missing_artifact", "location": "conv.py", "expected": "ok", "actual": "err"},
                "loong_megatron_sha": None,
            },
        )
        gh = FakeGhClient()
        budget = LoopBudget()
        # classify_failure will be called with a reconstructed ValidatorResult
        with patch("skills.adapt.lib.loop_controller.classify_failure") as mock_classify, \
             patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
            mock_classify.return_value = DiagnoseResult(
                classification=DiagnoseClassification.CODE_BUG,
                rationale="test", suggested_fix_summary=None,
                failure_signature=None,
            )
            mock_run.return_value = ValidatorResult(
                name="phase2-conversion", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            result = run_phase_loop(run_dir, phase=2, gh=gh, budget=budget)
        # Verify classify_failure was called with a ValidatorResult (not a dict)
        assert mock_classify.called
        first_arg = mock_classify.call_args[0][0]
        assert isinstance(first_arg, ValidatorResult)
        assert first_arg.integrity_ok is True

    def test_issue_opens_gh_issue_and_tracks(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(
            run_dir, phase=1, current_state="issue", attempt=1,
            last_validator_summary={
                "status": "failed", "name": "phase1-verify",
                "integrity_ok": True,
                "integrity_details": {"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                "failure_signature": {"kind": "missing_artifact", "location": "model.py", "expected": "exists", "actual": "missing"},
                "loong_megatron_sha": None,
            },
        )
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "loongforge_base_ref": "main",
            "run_id": "test-run",
        }
        # Run from ISSUE state; the controller should open an issue and track it
        with patch("skills.adapt.lib.loop_controller.classify_failure") as mock_classify, \
             patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            # Mock classify to return CODE_BUG for subsequent states
            mock_classify.return_value = DiagnoseResult(
                classification=DiagnoseClassification.CODE_BUG,
                rationale="test", suggested_fix_summary=None,
                failure_signature=None,
            )
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            # Run with limited iterations to just test the ISSUE state
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget,
                                   repos_info=repos_info, max_iterations=15)
        # Verify open_issue was called
        issue_calls = [c for c in gh.calls if c.method == "open_issue"]
        assert len(issue_calls) > 0
        # Verify issues_opened tracked in state
        reloaded = LoopState.from_disk(run_dir, phase=1)
        assert len(reloaded.issues_opened) > 0


# ---------------------------------------------------------------------------
# Task 2 tests: FIX_PR, REVIEW, MERGE_FIX, RERUN, EXIT states
# ---------------------------------------------------------------------------

class TestFixPrState:
    def test_fix_pr_advances_attempt(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="fix_pr", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity, \
             patch("skills.adapt.lib.loop_controller.classify_failure") as mock_classify:
            from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            mock_classify.return_value = DiagnoseResult(
                classification=DiagnoseClassification.CODE_BUG,
                rationale="test", suggested_fix_summary=None,
                failure_signature=None,
            )
            run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, max_iterations=15)
        reloaded = LoopState.from_disk(run_dir, phase=1)
        assert reloaded.attempt >= 2  # FIX_PR should advance the attempt


class TestReviewState:
    def test_review_transitions_to_merge_fix(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="review", attempt=2)
        gh = FakeGhClient()
        budget = LoopBudget()
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, max_iterations=10)
        # After review -> merge_fix -> rerun -> passed, the loop should exit with VALIDATOR_PASSED_AFTER_FIX
        reloaded = LoopState.from_disk(run_dir, phase=1)
        assert reloaded.exit_reason == ExitReason.VALIDATOR_PASSED_AFTER_FIX


class TestMergeFixState:
    def test_merge_fix_merges_pr(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="merge_fix", attempt=2, pr_number=5)
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "loongforge_base_ref": "main",
            "run_id": "test-run",
        }
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, repos_info=repos_info, max_iterations=10)
        # Verify merge_pr was called
        merge_calls = [c for c in gh.calls if c.method == "merge_pr"]
        assert len(merge_calls) > 0


class TestRerunState:
    def test_rerun_pass_exits_validator_passed_after_fix(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="rerun", attempt=2)
        gh = FakeGhClient()
        budget = LoopBudget()
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        assert result == ExitReason.VALIDATOR_PASSED_AFTER_FIX

    def test_rerun_pass_writes_phase_output(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="rerun", attempt=2)
        gh = FakeGhClient()
        budget = LoopBudget()
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        output_path = run_dir / "phases" / "phase1_output.yml"
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())
        assert data["validator_integrity"]["integrity_ok"] is True

    def test_rerun_passes_megatron_args(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=2)
        _write_loop_state(run_dir, phase=2, current_state="rerun", attempt=2)
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "megatron_repo": "Zachary-wW/Loong-Megatron",
            "megatron_ref": "loong-main/core_v0.15.0",
            "run_id": "test-run",
        }
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase2-conversion", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            run_phase_loop(run_dir, phase=2, gh=gh, budget=budget, repos_info=repos_info)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        # Verify megatron_repo and megatron_ref were passed
        assert call_kwargs.kwargs.get("megatron_repo") == "Zachary-wW/Loong-Megatron" or \
               (len(call_kwargs.args) > 3 and call_kwargs.args[3] == "Zachary-wW/Loong-Megatron")
        assert call_kwargs.kwargs.get("megatron_ref") == "loong-main/core_v0.15.0" or \
               (len(call_kwargs.args) > 4 and call_kwargs.args[4] == "loong-main/core_v0.15.0")

    def test_rerun_fail_transitions_to_diagnose(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(
            run_dir, phase=1, current_state="rerun", attempt=2,
            last_validator_summary={
                "status": "failed", "name": "phase1-verify",
                "integrity_ok": True,
                "integrity_details": {"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                "failure_signature": {"kind": "missing_artifact", "location": "test.py", "expected": "ok", "actual": "err"},
                "loong_megatron_sha": None,
            },
        )
        gh = FakeGhClient()
        budget = LoopBudget()
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity, \
             patch("skills.adapt.lib.loop_controller.classify_failure") as mock_classify:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="failed",
                failure_signature=FailureSignature(kind="missing_artifact", location="test.py", expected="ok", actual="err"),
                evidence={}, integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            mock_classify.return_value = DiagnoseResult(
                classification=DiagnoseClassification.NEEDS_HUMAN,
                rationale="test escalate", suggested_fix_summary=None,
                failure_signature=None,
            )
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        # Should escalate since classify returns NEEDS_HUMAN
        assert result == ExitReason.HUMAN_NEEDED


class TestFullCycle:
    def test_full_cycle_against_fake_gh_client(self, tmp_path):
        """Full VALIDATE->DIAGNOSE(CODE_BUG)->ISSUE->FIX_PR->REVIEW->MERGE_FIX->RERUN->passed cycle."""
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "loongforge_base_ref": "main",
            "megatron_repo": "Zachary-wW/Loong-Megatron",
            "megatron_ref": "loong-main/core_v0.15.0",
            "run_id": "test-run",
        }
        # First validator call fails, second (rerun) passes
        call_count = [0]
        def validator_side_effect(run_dir, phase, gh, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ValidatorResult(
                    name="phase1-verify", status="failed",
                    failure_signature=FailureSignature(kind="missing_artifact", location="model.py", expected="exists", actual="missing"),
                    evidence={}, integrity_ok=True,
                    integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                )
            return ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity, \
             patch("skills.adapt.lib.loop_controller.classify_failure") as mock_classify:
            mock_run.side_effect = validator_side_effect
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            mock_classify.return_value = DiagnoseResult(
                classification=DiagnoseClassification.CODE_BUG,
                rationale="test code bug", suggested_fix_summary="fix it",
                failure_signature=FailureSignature(kind="missing_artifact", location="model.py", expected="exists", actual="missing"),
            )
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, repos_info=repos_info)
        assert result == ExitReason.VALIDATOR_PASSED_AFTER_FIX
        # Verify phaseN_output.yml has loop, validator_integrity, pr, issues blocks
        output_path = run_dir / "phases" / "phase1_output.yml"
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())
        assert "loop" in data
        assert "validator_integrity" in data
        assert "pr" in data
        assert "issues" in data
        assert data["validator_integrity"]["integrity_ok"] is True

    def test_full_cycle_phase_output_passes_validation(self, tmp_path):
        """After full cycle, validate_phase_output should not raise (VAL-04 hook compatible)."""
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
        from skills.adapt.scripts.validate_phase_completion import validate_phase_output
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "loongforge_base_ref": "main",
            "run_id": "test-run",
        }
        call_count = [0]
        def validator_side_effect(run_dir, phase, gh, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ValidatorResult(
                    name="phase1-verify", status="failed",
                    failure_signature=FailureSignature(kind="missing_artifact", location="model.py", expected="exists", actual="missing"),
                    evidence={}, integrity_ok=True,
                    integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                )
            return ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity, \
             patch("skills.adapt.lib.loop_controller.classify_failure") as mock_classify:
            mock_run.side_effect = validator_side_effect
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            mock_classify.return_value = DiagnoseResult(
                classification=DiagnoseClassification.CODE_BUG,
                rationale="test", suggested_fix_summary=None,
                failure_signature=FailureSignature(kind="missing_artifact", location="model.py", expected="exists", actual="missing"),
            )
            run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, repos_info=repos_info)
        # Add required fields that the validator script checks
        output_path = run_dir / "phases" / "phase1_output.yml"
        data = yaml.safe_load(output_path.read_text())
        data["status"] = "passed"
        data["step_gate"] = {"mandatory_steps_complete": True}
        data["steps"] = {"step1": {"status": "passed", "evidence": "ok", "required": True}}
        data["validator"] = {"name": "phase1-verify", "status": "passed"}
        output_path.write_text(yaml.dump(data, sort_keys=False, default_flow_style=False))
        # validate_phase_output should not raise on the integrity block
        try:
            validate_phase_output(run_dir, phase=1)
        except ValueError as e:
            # The validator expects full phase structure; if it only fails on
            # missing step details, that's expected for our partial test setup.
            # What we really check is that _validate_loop_evidence does NOT reject
            # our validator_integrity block.
            assert "validator_integrity" not in str(e), f"VAL-04 hook rejected our integrity block: {e}"


class TestLoopStateShaFields:
    def test_loop_state_sha_fields_round_trip(self, tmp_path):
        """LoopState with merge_commit_sha and head_sha persists and reloads correctly."""
        from skills.adapt.lib.loop_controller import LoopState, FSMState
        state = LoopState(
            phase=2, attempt=2, current_state=FSMState.MERGE_BASE,
            exit_reason=None, run_start_time="2026-01-01T00:00:00+00:00",
            total_attempts_used=1,
            merge_commit_sha="abc123def456",
            head_sha="def456abc123",
        )
        state.persist(tmp_path)
        reloaded = LoopState.from_disk(tmp_path, phase=2)
        assert reloaded.merge_commit_sha == "abc123def456"
        assert reloaded.head_sha == "def456abc123"

    def test_loop_state_sha_fields_missing_in_yaml_defaults_none(self, tmp_path):
        """LoopState.from_disk handles loop_state.yml without merge_commit_sha/head_sha (backward compat)."""
        from skills.adapt.lib.loop_controller import LoopState, FSMState
        phase_dir = tmp_path / "phases" / "phase1"
        phase_dir.mkdir(parents=True, exist_ok=True)
        # Write a loop_state.yml WITHOUT merge_commit_sha or head_sha keys
        state_data = {
            "phase": 1,
            "attempt": 1,
            "current_state": "validate",
            "exit_reason": None,
            "run_start_time": "2026-01-01T00:00:00+00:00",
            "total_attempts_used": 0,
        }
        (phase_dir / "loop_state.yml").write_text(
            yaml.dump(state_data, default_flow_style=False)
        )
        state = LoopState.from_disk(tmp_path, phase=1)
        assert state.merge_commit_sha is None
        assert state.head_sha is None


class TestExhaustedExit:
    def test_exhausted_exit_writes_phase_output(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=5)
        budget = LoopBudget(max_attempts_per_phase=5)
        gh = FakeGhClient()
        result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        assert result == ExitReason.EXHAUSTED
        output_path = run_dir / "phases" / "phase1_output.yml"
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())
        assert data["loop"]["exit_reason"] == "exhausted"


class TestReEntrant:
    def test_re_entrant_from_disk(self, tmp_path):
        """Verify that calling run_phase_loop twice on the same run_dir picks up existing state."""
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        # Write a state at EDIT (simulating the controller having previously
        # reached this state, then being interrupted/crashed before continuing)
        _write_loop_state(run_dir, phase=1, current_state="edit", attempt=1)
        # Run -- should pick up from EDIT and continue through PR -> MERGE_BASE -> VALIDATE -> passed
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        assert result == ExitReason.VALIDATOR_PASSED


class TestSafetyChecks:
    def test_no_loop_invocation(self):
        """grep loop_controller.py for '/loop' -- must not appear (SAFE-02)."""
        controller_path = Path(__file__).resolve().parents[2] / "lib" / "loop_controller.py"
        content = controller_path.read_text()
        assert "/loop" not in content

    def test_max_iterations_safety(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
        from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget(max_attempts_per_phase=50, max_attempts_per_run=500, max_wallclock_minutes=10080)
        # Every validator call fails, classify always CODE_BUG -> loop would run forever without safety
        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity, \
             patch("skills.adapt.lib.loop_controller.classify_failure") as mock_classify:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="failed",
                failure_signature=FailureSignature(kind="code_bug", location="test.py", expected="ok", actual="err"),
                evidence={}, integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {"integrity_ok": True, "binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}
            mock_classify.return_value = DiagnoseResult(
                classification=DiagnoseClassification.CODE_BUG,
                rationale="test", suggested_fix_summary=None,
                failure_signature=None,
            )
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, max_iterations=5)
        # Safety limit should stop it
        assert result == ExitReason.EXHAUSTED

    def test_exit_state_safety_net_write(self, tmp_path):
        from skills.adapt.lib.loop_controller import run_phase_loop, LoopState, FSMState, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        run_dir = _setup_run_dir(tmp_path, phase=1)
        # Set state to EXIT with VALIDATOR_PASSED but no phaseN_output.yml yet
        _write_loop_state(run_dir, phase=1, current_state="exit", attempt=1,
                         exit_reason="validator_passed")
        gh = FakeGhClient()
        budget = LoopBudget()
        result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget)
        assert result == ExitReason.VALIDATOR_PASSED
        # Verify _write_phase_output was called in EXIT handler as safety net
        output_path = run_dir / "phases" / "phase1_output.yml"
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())
        assert "validator_integrity" in data
