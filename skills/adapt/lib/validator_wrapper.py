"""Validator wrapper: invocation, integrity checks, flake-rerun logic, SHA pinning, attempt-row helper.

Exports:
  FailureSignature -- structured failure record from validator output
  ValidatorResult -- normalized result from a validator invocation
  run_validator -- invoke loongforge-phase-gate and return ValidatorResult
  should_rerun_for_flake -- decide whether to rerun for near-threshold flake (VAL-03)
  check_validator_integrity -- three-part integrity check (VAL-04)
  get_megatron_head_sha -- retrieve SHA from gh api for cross-repo pinning (VAL-05)
  make_attempt_row -- build a LOG-01 attempts.jsonl row with event_id hash

Constants:
  FLAKE_RERUN_PHASES -- {3, 4}
  DEFAULT_FLAKE_RERUN_COUNT -- 3
  PHASE_VALIDATORS -- {1: "phase1-verify", 2: "phase2-conversion", ...}
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from skills.adapt.lib.gh_client import GhClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLAKE_RERUN_PHASES: set[int] = {3, 4}
DEFAULT_FLAKE_RERUN_COUNT: int = 3
PHASE_VALIDATORS: dict[int, str] = {
    1: "phase1-verify",
    2: "phase2-conversion",
    3: "loss-diff",
    4: "feature-compat",
    5: "kb-consistency",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FailureSignature:
    """Structured failure record from validator output (VAL-02).

    When a validator emits a structured failure with kind/location/expected/actual
    fields, they are captured here. Free-text-only failures have failure_signature=None.
    """
    kind: str
    location: str
    expected: str
    actual: str


@dataclass
class ValidatorResult:
    """Normalized result from a single validator invocation.

    Fields:
      name: validator name (e.g. "phase1-verify", "loss-diff")
      status: "passed" | "failed" | "flaky"
      failure_signature: FailureSignature if structured, None if free-text-only (VAL-02)
      evidence: raw validator output dict
      integrity_ok: True iff all VAL-04 integrity checks pass
      integrity_details: per-check results for binary_hash_ok, log_mtime_ok, log_present
      rerun_count: how many times this result was produced by a flake rerun
      loong_megatron_sha: SHA of Megatron HEAD at validation time (VAL-05)
    """
    name: str
    status: str  # "passed" | "failed" | "flaky"
    failure_signature: Optional[FailureSignature]
    evidence: dict[str, Any]
    integrity_ok: bool
    integrity_details: dict[str, bool]
    rerun_count: int = 0
    loong_megatron_sha: Optional[str] = None


# ---------------------------------------------------------------------------
# run_validator
# ---------------------------------------------------------------------------

def run_validator(
    run_dir: Path,
    phase: int,
    gh: GhClient,
    megatron_repo: Optional[str] = None,
    megatron_ref: Optional[str] = None,
) -> ValidatorResult:
    """Invoke loongforge-phase-gate and return a ValidatorResult (VAL-01).

    Calls loongforge-phase-gate --run-dir --phase via subprocess with a 300s timeout.
    Never rewrites validator logic -- only normalizes output.
    """
    validator_name = PHASE_VALIDATORS.get(phase, f"phase{phase}")
    evidence: dict[str, Any] = {}
    failure_signature: Optional[FailureSignature] = None
    status = "failed"

    try:
        proc = subprocess.run(
            ["loongforge-phase-gate", "--run-dir", str(run_dir), "--phase", str(phase)],
            capture_output=True, text=True, check=False, timeout=300,
        )
        if "PASSED" in proc.stdout:
            status = "passed"
        elif "BLOCKED" in proc.stderr:
            status = "failed"
            # Try to parse structured failure from phaseN_output.yml (VAL-02)
            output_path = run_dir / "phases" / f"phase{phase}_output.yml"
            if output_path.exists():
                data = yaml.safe_load(output_path.read_text())
                if isinstance(data, dict):
                    validator_block = data.get("validator") or {}
                    fs_dict = validator_block.get("failure_signature") if isinstance(validator_block, dict) else None
                    if isinstance(fs_dict, dict) and "kind" in fs_dict and "location" in fs_dict:
                        failure_signature = FailureSignature(
                            kind=fs_dict["kind"],
                            location=fs_dict["location"],
                            expected=str(fs_dict.get("expected", "")),
                            actual=str(fs_dict.get("actual", "")),
                        )
                    evidence = data
        else:
            status = "failed"
    except subprocess.TimeoutExpired:
        status = "failed"

    # Integrity check (VAL-04) -- using approximate "now" as attempt start
    attempt_start = datetime.now(timezone.utc).isoformat()
    integrity = check_validator_integrity(run_dir, phase, attempt_start)

    # Cross-repo SHA pinning (VAL-05)
    megatron_sha: Optional[str] = None
    if megatron_repo and megatron_ref:
        try:
            megatron_sha = get_megatron_head_sha(gh, megatron_repo, megatron_ref)
        except RuntimeError:
            pass  # SHA unavailable; caller decides whether to fail

    return ValidatorResult(
        name=validator_name,
        status=status,
        failure_signature=failure_signature,
        evidence=evidence,
        integrity_ok=integrity["integrity_ok"],
        integrity_details=integrity,
        rerun_count=0,
        loong_megatron_sha=megatron_sha,
    )


# ---------------------------------------------------------------------------
# should_rerun_for_flake
# ---------------------------------------------------------------------------

def should_rerun_for_flake(result: ValidatorResult, phase: int) -> bool:
    """Decide whether to rerun validator for near-threshold flake (VAL-03).

    Returns True iff:
      - phase is in FLAKE_RERUN_PHASES ({3, 4})
      - result.status == "failed"
      - result.failure_signature is not None
      - failure_signature.kind in ("numerical_mismatch", "threshold_exceeded")
    """
    if phase not in FLAKE_RERUN_PHASES:
        return False
    if result.status != "failed":
        return False
    if result.failure_signature is None:
        return False
    if result.failure_signature.kind not in ("numerical_mismatch", "threshold_exceeded"):
        return False
    return True


# ---------------------------------------------------------------------------
# check_validator_integrity
# ---------------------------------------------------------------------------

def check_validator_integrity(
    run_dir: Path,
    phase: int,
    attempt_start_time: str,
    recorded_hash: Optional[str] = None,
) -> dict[str, bool]:
    """Three-part integrity check for validator output (VAL-04).

    Returns dict with keys:
      binary_hash_ok, log_mtime_ok, log_present, integrity_ok
    """
    results: dict[str, bool] = {
        "binary_hash_ok": True,
        "log_mtime_ok": True,
        "log_present": True,
    }

    # Check 1: Binary hash
    if recorded_hash is not None:
        validator_path = run_dir / "bin" / "loongforge-phase-gate"
        if validator_path.exists():
            current_hash = hashlib.sha256(validator_path.read_bytes()).hexdigest()[:16]
            results["binary_hash_ok"] = current_hash == recorded_hash
        else:
            results["binary_hash_ok"] = False

    # Check 2: Log file present
    log_dir = run_dir / "phases" / f"phase{phase}" / "logs"
    if not log_dir.exists() or not any(log_dir.iterdir()):
        results["log_present"] = False

    # Check 3: Log mtime >= attempt timestamp
    if results["log_present"]:
        attempt_dt = datetime.fromisoformat(attempt_start_time)
        attempt_ts = attempt_dt.timestamp()
        any_fresh = False
        for log_file in log_dir.iterdir():
            if log_file.stat().st_mtime >= attempt_ts:
                any_fresh = True
                break
        results["log_mtime_ok"] = any_fresh

    results["integrity_ok"] = all(results.values())
    return results


# ---------------------------------------------------------------------------
# get_megatron_head_sha
# ---------------------------------------------------------------------------

def get_megatron_head_sha(gh: GhClient, owner_repo: str, ref: str) -> str:
    """Retrieve HEAD SHA of a Megatron repo branch via gh api (VAL-05)."""
    # Use _run to call gh api, matching the pattern in gh_client.py
    result = gh._run(["api", f"repos/{owner_repo}/git/ref/heads/{ref}", "--jq", ".object.sha"])
    if result.returncode != 0:
        raise RuntimeError(f"Cannot resolve Megatron SHA for {owner_repo}:{ref}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# make_attempt_row
# ---------------------------------------------------------------------------

def make_attempt_row(
    attempt: int,
    kind: str,
    phase: int,
    pr_url: str = "",
    issue_url: str = "",
    validator: str = "",
    verdict: str = "",
    exit_reason: str = "",
) -> dict[str, Any]:
    """Build a LOG-01 attempts.jsonl row with event_id hash.

    Row fields: ts, attempt, kind, pr_url, issue_url, validator, verdict, exit_reason, event_id
    event_id = sha256(f"{ts}:{attempt}:{kind}:{phase}")[:16]
    """
    ts = datetime.now(timezone.utc).isoformat()
    event_id = hashlib.sha256(f"{ts}:{attempt}:{kind}:{phase}".encode()).hexdigest()[:16]
    return {
        "ts": ts,
        "attempt": attempt,
        "kind": kind,
        "pr_url": pr_url,
        "issue_url": issue_url,
        "validator": validator,
        "verdict": verdict,
        "exit_reason": exit_reason,
        "event_id": event_id,
    }
