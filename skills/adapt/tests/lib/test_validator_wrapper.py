"""Tests for validator_wrapper.py: FailureSignature, ValidatorResult, run_validator,
should_rerun_for_flake, check_validator_integrity, get_megatron_head_sha, make_attempt_row.

Covers:
  - VAL-01: run_validator calls loongforge-phase-gate subprocess, never rewrites validator logic
  - VAL-02: Free-text-only failures produce failure_signature=None; structured failures produce FailureSignature
  - VAL-03: should_rerun_for_flake gates Phase 3/4 numerical near-threshold
  - VAL-04: check_validator_integrity performs 3 checks (binary hash, log mtime, log presence)
  - VAL-05: get_megatron_head_sha retrieves SHA from gh api
  - LOG-01: make_attempt_row produces all 9 required fields including event_id hash
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from skills.adapt.lib.gh_client import FakeGhClient, GhResult
from skills.adapt.lib.validator_wrapper import (
    DEFAULT_FLAKE_RERUN_COUNT,
    FLAKE_RERUN_PHASES,
    PHASE_VALIDATORS,
    FailureSignature,
    ValidatorResult,
    check_validator_integrity,
    get_megatron_head_sha,
    make_attempt_row,
    run_validator,
    should_rerun_for_flake,
)


# ---------------------------------------------------------------------------
# FailureSignature dataclass
# ---------------------------------------------------------------------------

class TestFailureSignature:
    def test_fields(self) -> None:
        sig = FailureSignature(kind="numerical_mismatch", location="L42", expected="<1e-5", actual="3.2e-4")
        assert sig.kind == "numerical_mismatch"
        assert sig.location == "L42"
        assert sig.expected == "<1e-5"
        assert sig.actual == "3.2e-4"

    def test_is_frozen(self) -> None:
        sig = FailureSignature(kind="x", location="y", expected="z", actual="w")
        with pytest.raises(AttributeError):
            sig.kind = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ValidatorResult dataclass
# ---------------------------------------------------------------------------

class TestValidatorResult:
    def test_passed_result(self) -> None:
        r = ValidatorResult(
            name="phase1-verify", status="passed",
            failure_signature=None, evidence={"raw": "ok"},
            integrity_ok=True, integrity_details={},
        )
        assert r.status == "passed"
        assert r.failure_signature is None
        assert r.rerun_count == 0
        assert r.loong_megatron_sha is None

    def test_failed_result_with_signature(self) -> None:
        sig = FailureSignature(kind="missing_artifact", location="modeling.py", expected="exists", actual="missing")
        r = ValidatorResult(
            name="phase1-verify", status="failed",
            failure_signature=sig, evidence={},
            integrity_ok=False, integrity_details={"log_present": False},
        )
        assert r.status == "failed"
        assert r.failure_signature is not None
        assert r.failure_signature.kind == "missing_artifact"

    def test_failed_result_no_signature(self) -> None:
        """VAL-02: free-text-only failures produce failure_signature=None."""
        r = ValidatorResult(
            name="phase1-verify", status="failed",
            failure_signature=None, evidence={"text": "something went wrong"},
            integrity_ok=False, integrity_details={},
        )
        assert r.failure_signature is None

    def test_default_fields(self) -> None:
        r = ValidatorResult(
            name="loss-diff", status="flaky",
            failure_signature=None, evidence={},
            integrity_ok=True, integrity_details={},
            rerun_count=2, loong_megatron_sha="abc123",
        )
        assert r.rerun_count == 2
        assert r.loong_megatron_sha == "abc123"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_flake_rerun_phases(self) -> None:
        assert FLAKE_RERUN_PHASES == {3, 4}

    def test_default_flake_rerun_count(self) -> None:
        assert DEFAULT_FLAKE_RERUN_COUNT == 3

    def test_phase_validators(self) -> None:
        assert PHASE_VALIDATORS == {
            1: "phase1-verify",
            2: "phase2-conversion",
            3: "loss-diff",
            4: "feature-compat",
            5: "kb-consistency",
        }


# ---------------------------------------------------------------------------
# run_validator
# ---------------------------------------------------------------------------

class TestRunValidator:
    def _make_run_dir(self, tmp_path: Path, phase: int, output_data: dict) -> Path:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        phases_dir = run_dir / "phases"
        phases_dir.mkdir()
        # Write phaseN_output.yml
        (phases_dir / f"phase{phase}_output.yml").write_text(
            yaml.dump(output_data, sort_keys=False)
        )
        return run_dir

    @patch("skills.adapt.lib.validator_wrapper.subprocess.run")
    def test_passed_validator(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """VAL-01: run_validator returns passed when loongforge-phase-gate emits PASSED."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="PASSED: phase 1 completion gate satisfied", stderr=""
        )
        output_data = {
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"s1": {"status": "passed", "evidence": "ok"}},
            "validator": {"name": "phase1-verify", "status": "passed"},
        }
        run_dir = self._make_run_dir(tmp_path, 1, output_data)
        result = run_validator(run_dir, 1, FakeGhClient())
        assert result.status == "passed"
        assert result.failure_signature is None
        assert result.name == "phase1-verify"

    @patch("skills.adapt.lib.validator_wrapper.subprocess.run")
    def test_failed_with_structured_signature(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Structured failure in phaseN_output.yml -> FailureSignature."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr="BLOCKED: validation failed"
        )
        output_data = {
            "status": "failed",
            "validator": {
                "name": "phase1-verify",
                "status": "failed",
                "failure_signature": {
                    "kind": "missing_artifact",
                    "location": "modeling.py",
                    "expected": "class DeepseekV4Model exists",
                    "actual": "class not found",
                },
            },
        }
        run_dir = self._make_run_dir(tmp_path, 1, output_data)
        result = run_validator(run_dir, 1, FakeGhClient())
        assert result.status == "failed"
        assert result.failure_signature is not None
        assert result.failure_signature.kind == "missing_artifact"
        assert result.failure_signature.location == "modeling.py"

    @patch("skills.adapt.lib.validator_wrapper.subprocess.run")
    def test_failed_free_text_only(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """VAL-02: free-text-only failure -> failure_signature=None."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=2, stdout="", stderr="BLOCKED: something went wrong"
        )
        output_data = {
            "status": "failed",
            "validator": {
                "name": "phase1-verify",
                "status": "failed",
                # No failure_signature dict
            },
        }
        run_dir = self._make_run_dir(tmp_path, 1, output_data)
        result = run_validator(run_dir, 1, FakeGhClient())
        assert result.status == "failed"
        assert result.failure_signature is None

    @patch("skills.adapt.lib.validator_wrapper.subprocess.run")
    def test_subprocess_timeout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """run_validator handles subprocess timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["loongforge-phase-gate"], timeout=300)
        output_data = {
            "status": "failed",
            "validator": {"name": "phase1-verify", "status": "failed"},
        }
        run_dir = self._make_run_dir(tmp_path, 1, output_data)
        result = run_validator(run_dir, 1, FakeGhClient())
        assert result.status == "failed"

    @patch("skills.adapt.lib.validator_wrapper.subprocess.run")
    def test_megatron_sha_recorded(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """VAL-05: when megatron_repo provided, loong_megatron_sha is populated."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="PASSED: phase 1", stderr=""
        )
        output_data = {
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"s1": {"status": "passed", "evidence": "ok"}},
            "validator": {"name": "phase1-verify", "status": "passed"},
        }
        run_dir = self._make_run_dir(tmp_path, 1, output_data)

        gh = FakeGhClient()
        result = run_validator(
            run_dir, 1, gh,
            megatron_repo="Zachary-wW/Loong-Megatron",
            megatron_ref="loong-main/core_v0.15.0",
        )
        assert result.loong_megatron_sha is not None
        assert len(result.loong_megatron_sha) > 0


# ---------------------------------------------------------------------------
# should_rerun_for_flake
# ---------------------------------------------------------------------------

class TestShouldRerunForFlake:
    def test_phase3_numerical_mismatch(self) -> None:
        """VAL-03: Phase 3 numerical_mismatch -> should rerun."""
        sig = FailureSignature(kind="numerical_mismatch", location="L1", expected="<1e-5", actual="2e-5")
        r = ValidatorResult(
            name="loss-diff", status="failed",
            failure_signature=sig, evidence={},
            integrity_ok=True, integrity_details={},
        )
        assert should_rerun_for_flake(r, 3) is True

    def test_phase4_threshold_exceeded(self) -> None:
        """VAL-03: Phase 4 threshold_exceeded -> should rerun."""
        sig = FailureSignature(kind="threshold_exceeded", location="L1", expected="<0.01", actual="0.015")
        r = ValidatorResult(
            name="feature-compat", status="failed",
            failure_signature=sig, evidence={},
            integrity_ok=True, integrity_details={},
        )
        assert should_rerun_for_flake(r, 4) is True

    def test_phase1_numerical_no_rerun(self) -> None:
        """Phase 1 numerical mismatch -> no rerun (not in FLAKE_RERUN_PHASES)."""
        sig = FailureSignature(kind="numerical_mismatch", location="L1", expected="x", actual="y")
        r = ValidatorResult(
            name="phase1-verify", status="failed",
            failure_signature=sig, evidence={},
            integrity_ok=True, integrity_details={},
        )
        assert should_rerun_for_flake(r, 1) is False

    def test_phase3_missing_artifact_no_rerun(self) -> None:
        """Phase 3 non-numerical failure -> no rerun."""
        sig = FailureSignature(kind="missing_artifact", location="L1", expected="x", actual="y")
        r = ValidatorResult(
            name="loss-diff", status="failed",
            failure_signature=sig, evidence={},
            integrity_ok=True, integrity_details={},
        )
        assert should_rerun_for_flake(r, 3) is False

    def test_no_signature_no_rerun(self) -> None:
        """No failure signature -> no rerun."""
        r = ValidatorResult(
            name="loss-diff", status="failed",
            failure_signature=None, evidence={},
            integrity_ok=True, integrity_details={},
        )
        assert should_rerun_for_flake(r, 3) is False

    def test_passed_no_rerun(self) -> None:
        """Passed result -> no rerun."""
        r = ValidatorResult(
            name="loss-diff", status="passed",
            failure_signature=None, evidence={},
            integrity_ok=True, integrity_details={},
        )
        assert should_rerun_for_flake(r, 3) is False


# ---------------------------------------------------------------------------
# check_validator_integrity
# ---------------------------------------------------------------------------

class TestCheckValidatorIntegrity:
    def test_all_ok(self, tmp_path: Path) -> None:
        """All three integrity checks pass."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Create bin with validator
        bin_dir = run_dir / "bin"
        bin_dir.mkdir()
        validator_bin = bin_dir / "loongforge-phase-gate"
        validator_bin.write_bytes(b"#!/bin/bash\ntrue\n")
        recorded_hash = hashlib.sha256(validator_bin.read_bytes()).hexdigest()[:16]
        # Create logs
        log_dir = run_dir / "phases" / "phase1" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "validator.log"
        log_file.write_text("passed\n")
        # Set mtime to now
        now = datetime.now(timezone.utc)
        os.utime(log_file, (now.timestamp(), now.timestamp()))
        attempt_time = now.isoformat()
        result = check_validator_integrity(run_dir, 1, attempt_time, recorded_hash)
        assert result["binary_hash_ok"] is True
        assert result["log_present"] is True
        assert result["log_mtime_ok"] is True
        assert result["integrity_ok"] is True

    def test_no_logs_dir(self, tmp_path: Path) -> None:
        """log_present=False when no logs dir."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        result = check_validator_integrity(run_dir, 1, datetime.now(timezone.utc).isoformat())
        assert result["log_present"] is False
        assert result["integrity_ok"] is False

    def test_log_mtime_too_old(self, tmp_path: Path) -> None:
        """log_mtime_ok=False when log mtime < attempt timestamp."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        log_dir = run_dir / "phases" / "phase1" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "validator.log"
        log_file.write_text("old log\n")
        # Set log mtime to 1 hour ago
        one_hour_ago = datetime.now(timezone.utc).timestamp() - 3600
        os.utime(log_file, (one_hour_ago, one_hour_ago))
        # Attempt time is now
        attempt_time = datetime.now(timezone.utc).isoformat()
        result = check_validator_integrity(run_dir, 1, attempt_time)
        assert result["log_mtime_ok"] is False
        assert result["integrity_ok"] is False

    def test_binary_hash_mismatch(self, tmp_path: Path) -> None:
        """binary_hash_ok=False when hash mismatches."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        bin_dir = run_dir / "bin"
        bin_dir.mkdir()
        validator_bin = bin_dir / "loongforge-phase-gate"
        validator_bin.write_bytes(b"real content")
        log_dir = run_dir / "phases" / "phase1" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "validator.log"
        log_file.write_text("log\n")
        now = datetime.now(timezone.utc)
        os.utime(log_file, (now.timestamp(), now.timestamp()))
        attempt_time = now.isoformat()
        result = check_validator_integrity(run_dir, 1, attempt_time, recorded_hash="wronghash12345678")
        assert result["binary_hash_ok"] is False
        assert result["integrity_ok"] is False

    def test_no_recorded_hash_skips_binary_check(self, tmp_path: Path) -> None:
        """When no recorded_hash, binary_hash_ok defaults to True (skip check)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        log_dir = run_dir / "phases" / "phase1" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "validator.log"
        log_file.write_text("log\n")
        now = datetime.now(timezone.utc)
        os.utime(log_file, (now.timestamp(), now.timestamp()))
        attempt_time = now.isoformat()
        result = check_validator_integrity(run_dir, 1, attempt_time, recorded_hash=None)
        assert result["binary_hash_ok"] is True
        assert result["integrity_ok"] is True


# ---------------------------------------------------------------------------
# get_megatron_head_sha
# ---------------------------------------------------------------------------

class TestGetMegatronHeadSha:
    def test_success(self) -> None:
        """VAL-05: returns SHA from gh api."""
        gh = FakeGhClient()
        sha = get_megatron_head_sha(gh, "Zachary-wW/Loong-Megatron", "loong-main/core_v0.15.0")
        assert isinstance(sha, str)
        assert len(sha) > 0

    def test_failure_raises(self) -> None:
        """Raises RuntimeError when gh api fails."""
        gh = FakeGhClient()
        # Force _run to fail by patching
        with patch.object(gh, "_run", return_value=GhResult(1, "", "not found")):
            with pytest.raises(RuntimeError, match="Cannot resolve Megatron SHA"):
                get_megatron_head_sha(gh, "Zachary-wW/Loong-Megatron", "bad-ref")


# ---------------------------------------------------------------------------
# make_attempt_row
# ---------------------------------------------------------------------------

class TestMakeAttemptRow:
    def test_all_nine_fields(self) -> None:
        """LOG-01: make_attempt_row produces all 9 required fields."""
        row = make_attempt_row(
            attempt=2, kind="validate", phase=3,
            pr_url="https://github.com/pull/1",
            issue_url="https://github.com/issues/2",
            validator="loss-diff",
            verdict="failed",
            exit_reason="validator_failed",
        )
        expected_keys = {"ts", "attempt", "kind", "pr_url", "issue_url", "validator", "verdict", "exit_reason", "event_id"}
        assert set(row.keys()) == expected_keys
        assert row["attempt"] == 2
        assert row["kind"] == "validate"
        assert row["pr_url"] == "https://github.com/pull/1"

    def test_event_id_is_deterministic_hash(self) -> None:
        """event_id = sha256(ts:attempt:kind:phase)[:16]."""
        row = make_attempt_row(attempt=1, kind="edit", phase=2)
        ts = row["ts"]
        expected_id = hashlib.sha256(f"{ts}:1:edit:2".encode()).hexdigest()[:16]
        assert row["event_id"] == expected_id

    def test_defaults(self) -> None:
        """Optional fields default to empty string."""
        row = make_attempt_row(attempt=1, kind="probe", phase=1)
        assert row["pr_url"] == ""
        assert row["issue_url"] == ""
        assert row["validator"] == ""
        assert row["verdict"] == ""
        assert row["exit_reason"] == ""

    def test_ts_is_utc_iso(self) -> None:
        """ts is a valid ISO datetime string."""
        row = make_attempt_row(attempt=1, kind="probe", phase=1)
        # Should parse without error
        parsed = datetime.fromisoformat(row["ts"])
        assert parsed.tzinfo is not None
