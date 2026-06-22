"""FSM loop controller: re-entrant phase loop driving Probe->Edit->PR->Merge(base)->Validate->(Diagnose->Issue->Fix-PR->Review->Merge->Rerun)*.

This is the FSM spine -- the re-entrant controller that composes the validator
wrapper (Plan 01) and GhClient (Phase 2) into a working closed-loop system.
It exits only on a verifiable validator-pass or a bounded escalation, never
on hope (P3, P18).

Exports:
  FSMState -- enum: 12 FSM states
  ExitReason -- enum: 6 exit reasons
  LoopState -- dataclass: full FSM state, re-read from disk every invocation
  check_budget -- three-axis budget enforcement (LOOP-03)
  _advance_attempt -- increment attempt counters
  _transition -- FSM state transition with attempts.jsonl logging
  _read_attempts_history -- read all lines from attempts.jsonl
  _compute_validator_hash -- SHA-256 hash of validator binary for VAL-04
  _write_phase_output -- write phaseN_output.yml with loop/integrity/pr/issues blocks
  run_phase_loop -- re-entrant FSM controller (LOOP-01)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

from skills.adapt.lib.gh_client import GhClient
from skills.adapt.lib.jsonl import append_attempt
from skills.adapt.lib.schema import LoopBudget, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput
from skills.adapt.lib.validator_wrapper import (
    ValidatorResult, FailureSignature,
    run_validator, should_rerun_for_flake, check_validator_integrity,
    make_attempt_row, DEFAULT_FLAKE_RERUN_COUNT,
)
from skills.adapt.lib.diagnose_classifier import (
    DiagnoseClassification, DiagnoseResult,
    classify_failure, write_escalation,
)


# ---------------------------------------------------------------------------
# FSM enums
# ---------------------------------------------------------------------------

class FSMState(str, Enum):
    """FSM states for the loop controller (LOOP-01)."""
    PROBE = "probe"
    EDIT = "edit"
    PR = "pr"
    MERGE_BASE = "merge_base"
    VALIDATE = "validate"
    DIAGNOSE = "diagnose"
    ISSUE = "issue"
    FIX_PR = "fix_pr"
    REVIEW = "review"
    MERGE_FIX = "merge_fix"
    RERUN = "rerun"
    EXIT = "exit"


class ExitReason(str, Enum):
    """Exit reasons for the loop controller (LOOP-02)."""
    VALIDATOR_PASSED = "validator_passed"
    VALIDATOR_PASSED_AFTER_FIX = "validator_passed_after_fix"
    EXHAUSTED = "exhausted"
    ESCALATED = "escalated"
    BASE_ONLY = "base_only"
    HUMAN_NEEDED = "human_needed"


# ---------------------------------------------------------------------------
# LoopState
# ---------------------------------------------------------------------------

@dataclass
class LoopState:
    """Full FSM state, re-read from disk every invocation (P1).

    Persisted as loop_state.yml; re-entrant controller reconstructs this
    on every entry.
    """
    phase: int
    attempt: int
    current_state: FSMState
    exit_reason: ExitReason | None
    run_start_time: str  # ISO timestamp, written once at run init
    total_attempts_used: int
    pr_number: int | None = None
    issue_number: int | None = None
    validator_hash: str | None = None
    loong_megatron_sha: str | None = None
    last_validator_summary: dict | None = None
    issues_opened: list[int] = field(default_factory=list)
    issues_closed: list[int] = field(default_factory=list)

    @classmethod
    def from_disk(cls, run_dir: Path, phase: int) -> "LoopState":
        """Reconstruct state from loop_state.yml + attempts.jsonl tail (P1).

        If loop_state.yml is missing, creates initial state (PROBE, attempt=1).
        Also reads the tail of attempts.jsonl to get the latest attempt number
        and count of unique attempt numbers (for total_attempts_used).
        """
        state_path = run_dir / "phases" / f"phase{phase}" / "loop_state.yml"
        if state_path.exists():
            try:
                data = yaml.safe_load(state_path.read_text()) or {}
                current_state = FSMState(data.get("current_state", "probe"))
                exit_reason_raw = data.get("exit_reason")
                exit_reason = ExitReason(exit_reason_raw) if exit_reason_raw else None
                state = cls(
                    phase=phase,
                    attempt=data.get("attempt", 1),
                    current_state=current_state,
                    exit_reason=exit_reason,
                    run_start_time=data.get("run_start_time", datetime.now(timezone.utc).isoformat()),
                    total_attempts_used=data.get("total_attempts_used", 0),
                    pr_number=data.get("pr_number"),
                    issue_number=data.get("issue_number"),
                    validator_hash=data.get("validator_hash"),
                    loong_megatron_sha=data.get("loong_megatron_sha"),
                    last_validator_summary=data.get("last_validator_summary"),
                    issues_opened=data.get("issues_opened", []),
                    issues_closed=data.get("issues_closed", []),
                )
            except (ValueError, TypeError, yaml.YAMLError):
                state = cls(
                    phase=phase, attempt=1, current_state=FSMState.PROBE,
                    exit_reason=None,
                    run_start_time=datetime.now(timezone.utc).isoformat(),
                    total_attempts_used=0,
                )
        else:
            state = cls(
                phase=phase, attempt=1, current_state=FSMState.PROBE,
                exit_reason=None,
                run_start_time=datetime.now(timezone.utc).isoformat(),
                total_attempts_used=0,
            )

        # Also read the tail of attempts.jsonl to update attempt and total_attempts_used
        attempts_path = run_dir / "phases" / f"phase{phase}" / "attempts.jsonl"
        if attempts_path.exists():
            try:
                lines = attempts_path.read_text().strip().split("\n")
                valid_lines = [l for l in lines if l.strip()]
                if valid_lines:
                    last_row = json.loads(valid_lines[-1])
                    state.attempt = max(state.attempt, last_row.get("attempt", state.attempt))
                    # Count unique attempt numbers for total_attempts_used
                    unique_attempts = set()
                    for line in valid_lines:
                        row = json.loads(line)
                        attempt_num = row.get("attempt", 0)
                        if attempt_num > 0:
                            unique_attempts.add(attempt_num)
                    state.total_attempts_used = max(state.total_attempts_used, len(unique_attempts))
            except (json.JSONDecodeError, ValueError, OSError):
                pass

        return state

    def persist(self, run_dir: Path) -> None:
        """Write state to loop_state.yml (P1 disk persistence)."""
        phase_dir = run_dir / "phases" / f"phase{self.phase}"
        phase_dir.mkdir(parents=True, exist_ok=True)
        state_path = phase_dir / "loop_state.yml"
        data = {
            "phase": self.phase,
            "attempt": self.attempt,
            "current_state": self.current_state.value,
            "exit_reason": self.exit_reason.value if self.exit_reason else None,
            "run_start_time": self.run_start_time,
            "total_attempts_used": self.total_attempts_used,
            "pr_number": self.pr_number,
            "issue_number": self.issue_number,
            "validator_hash": self.validator_hash,
            "loong_megatron_sha": self.loong_megatron_sha,
            "last_validator_summary": self.last_validator_summary,
            "issues_opened": self.issues_opened,
            "issues_closed": self.issues_closed,
        }
        state_path.write_text(yaml.dump(data, sort_keys=False, default_flow_style=False))


# ---------------------------------------------------------------------------
# Budget check
# ---------------------------------------------------------------------------

def check_budget(
    budget: LoopBudget,
    phase_attempts: int,
    total_attempts: int,
    run_start_time: str,
) -> ExitReason | None:
    """Return ExitReason if any budget axis is breached, else None.

    IMPORTANT: This check MUST happen before processing validator results.
    If budget is breached, exit reason is ALWAYS EXHAUSTED, never passed (Pitfall 2).
    """
    if phase_attempts >= budget.max_attempts_per_phase:
        return ExitReason.EXHAUSTED
    if total_attempts >= budget.max_attempts_per_run:
        return ExitReason.EXHAUSTED
    start = datetime.fromisoformat(run_start_time)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds() / 60.0
    if elapsed >= budget.max_wallclock_minutes:
        return ExitReason.EXHAUSTED
    return None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _advance_attempt(state: LoopState) -> LoopState:
    """Return new LoopState with attempt+1 and total_attempts_used+1."""
    return replace(state, attempt=state.attempt + 1, total_attempts_used=state.total_attempts_used + 1)


def _transition(state: LoopState, new_state: FSMState, run_dir: Path, kind: str, **attempt_fields) -> LoopState:
    """Append one row to attempts.jsonl and update current_state."""
    attempts_path = run_dir / "phases" / f"phase{state.phase}" / "attempts.jsonl"
    row = make_attempt_row(state.attempt, kind, state.phase, **attempt_fields)
    append_attempt(attempts_path, row)
    return replace(state, current_state=new_state)


def _read_attempts_history(run_dir: Path, phase: int) -> list[dict]:
    """Read all lines from attempts.jsonl, parse each as JSON, return list."""
    attempts_path = run_dir / "phases" / f"phase{phase}" / "attempts.jsonl"
    if not attempts_path.exists():
        return []
    try:
        lines = attempts_path.read_text().strip().split("\n")
        return [json.loads(line) for line in lines if line.strip()]
    except (json.JSONDecodeError, ValueError):
        return []


def _compute_validator_hash(run_dir: Path) -> str | None:
    """Compute sha256[:16] of the loongforge-phase-gate binary, or None if missing."""
    validator_path = run_dir / "bin" / "loongforge-phase-gate"
    if not validator_path.exists():
        return None
    return hashlib.sha256(validator_path.read_bytes()).hexdigest()[:16]


def _write_phase_output(
    run_dir: Path, phase: int, state: LoopState,
    validator_result: ValidatorResult | None, budget: LoopBudget,
) -> None:
    """Write phaseN_output.yml with loop, validator_integrity, pr, issues blocks.

    This file is read by validate_phase_completion.py -> _validate_loop_evidence,
    which enforces VAL-04: if exit_reason is validator_passed, validator_integrity
    must be present and integrity_ok=True.
    """
    output_path = run_dir / "phases" / f"phase{phase}_output.yml"
    # Read existing file if present (merge with any pre-existing fields)
    existing: dict = {}
    if output_path.exists():
        try:
            existing = yaml.safe_load(output_path.read_text()) or {}
        except Exception:
            existing = {}

    # loop block (LoopBlockOutput schema)
    loop_block = LoopBlockOutput(
        attempts=state.attempt,
        max_attempts=budget.max_attempts_per_phase,
        exit_reason=state.exit_reason.value if state.exit_reason else "validator_passed",
        attempts_journal=str(run_dir / "phases" / f"phase{phase}" / "attempts.jsonl"),
    ).model_dump()

    # validator_integrity block (consumed by _validate_loop_evidence VAL-04 hook)
    validator_integrity: dict = {}
    if validator_result is not None:
        validator_integrity = {
            "integrity_ok": validator_result.integrity_ok,
            "binary_hash_ok": validator_result.integrity_details.get("binary_hash_ok", True),
            "log_mtime_ok": validator_result.integrity_details.get("log_mtime_ok", True),
            "log_present": validator_result.integrity_details.get("log_present", True),
        }

    # pr block
    pr_block = PrBlockOutput(number=state.pr_number).model_dump(exclude_none=True)

    # issues block
    issues_block = IssuesBlockOutput(
        opened=state.issues_opened,
        closed=state.issues_closed,
    ).model_dump()

    # Merge into existing data (existing wins for non-loop keys like status, validator, steps)
    merged = {
        **existing,
        "loop_engineering": True,
        "loop": loop_block,
        "validator_integrity": validator_integrity,
        "pr": pr_block,
        "issues": issues_block,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.dump(merged, sort_keys=False, default_flow_style=False))


# ---------------------------------------------------------------------------
# Reconstruct ValidatorResult from last_validator_summary (for DIAGNOSE)
# ---------------------------------------------------------------------------

def _reconstruct_validator_result(summary: dict) -> ValidatorResult:
    """Reconstruct a ValidatorResult from the last_validator_summary dict stored in loop_state.yml.

    This is used by the DIAGNOSE state to reconstruct the result without relying
    on in-memory state (P1 compatibility).
    """
    failure_signature = None
    fs_dict = summary.get("failure_signature")
    if isinstance(fs_dict, dict) and fs_dict.get("kind"):
        failure_signature = FailureSignature(
            kind=fs_dict["kind"],
            location=fs_dict.get("location", ""),
            expected=fs_dict.get("expected", ""),
            actual=fs_dict.get("actual", ""),
        )
    return ValidatorResult(
        name=summary.get("name", "unknown"),
        status=summary.get("status", "failed"),
        failure_signature=failure_signature,
        evidence={},
        integrity_ok=summary.get("integrity_ok", False),
        integrity_details=summary.get("integrity_details", {}),
        loong_megatron_sha=summary.get("loong_megatron_sha"),
    )


# ---------------------------------------------------------------------------
# run_phase_loop -- re-entrant FSM controller
# ---------------------------------------------------------------------------

def run_phase_loop(
    run_dir: Path,
    phase: int,
    gh: GhClient,
    budget: LoopBudget,
    dry_run: bool = False,
    max_iterations: int = 100,
    repos_info: dict | None = None,
) -> ExitReason:
    """Re-entrant controller implementing LOOP-01 FSM dispatch.

    The repos_info dict (default None) contains loongforge_repo, loongforge_base_ref,
    megatron_repo, megatron_ref, run_id. When None, PR/issue steps are skipped
    (local-only mode).

    Returns ExitReason when the loop terminates.
    """
    # 1. Read state from disk
    state = LoopState.from_disk(run_dir, phase)

    # 2. Record validator_hash at first entry if not recorded
    if state.validator_hash is None:
        state.validator_hash = _compute_validator_hash(run_dir)
        state.persist(run_dir)

    # 3. Budget pre-check (LOOP-03, Pitfall 2)
    budget_breach = check_budget(budget, state.attempt, state.total_attempts_used, state.run_start_time)
    if budget_breach:
        state.exit_reason = budget_breach
        state.current_state = FSMState.EXIT
        _transition(state, FSMState.EXIT, run_dir, kind="budget_check", exit_reason=budget_breach.value)
        _write_phase_output(run_dir, phase, state, None, budget)
        state.persist(run_dir)
        return budget_breach

    # 4. Safety iteration limit
    if max_iterations <= 0:
        state.exit_reason = ExitReason.EXHAUSTED
        state.current_state = FSMState.EXIT
        state.persist(run_dir)
        return ExitReason.EXHAUSTED

    # 5. FSM dispatch
    match state.current_state:
        # --- PROBE: transition to EDIT ---
        case FSMState.PROBE:
            state = _transition(state, FSMState.EDIT, run_dir, kind="probe")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- EDIT: transition to PR ---
        case FSMState.EDIT:
            state = _transition(state, FSMState.PR, run_dir, kind="edit")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- PR: create branch + open PR if repos_info ---
        case FSMState.PR:
            if repos_info:
                owner_repo = repos_info.get("loongforge_repo", "")
                base_ref = repos_info.get("loongforge_base_ref", "main")
                run_id = repos_info.get("run_id", "unknown")
                branch = f"adapt/{run_id}/phase{phase}/attempt{state.attempt}"
                gh.create_branch(owner_repo, branch, base=base_ref)
                pr_result = gh.open_pr(
                    owner_repo, head=branch, base=base_ref,
                    run_id=run_id, phase=phase, attempt=state.attempt,
                    kind="base",
                )
                # Parse PR number from URL
                try:
                    state.pr_number = int(pr_result.stdout.strip().split("/")[-1])
                except (ValueError, IndexError):
                    state.pr_number = None
            state = _transition(state, FSMState.MERGE_BASE, run_dir, kind="pr",
                                pr_url=f"https://github.com/{repos_info.get('loongforge_repo', '')}/pull/{state.pr_number}" if repos_info and state.pr_number else "")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- MERGE_BASE: merge base PR if repos_info ---
        case FSMState.MERGE_BASE:
            if repos_info and state.pr_number:
                owner_repo = repos_info.get("loongforge_repo", "")
                gh.merge_pr(owner_repo, state.pr_number)
            state = _transition(state, FSMState.VALIDATE, run_dir, kind="merge_base")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- VALIDATE: run validator ---
        case FSMState.VALIDATE:
            megatron_repo = repos_info.get("megatron_repo") if repos_info else None
            megatron_ref = repos_info.get("megatron_ref") if repos_info else None
            result = run_validator(run_dir, phase, gh, megatron_repo=megatron_repo, megatron_ref=megatron_ref)

            # Call check_validator_integrity with recorded_hash
            integrity = check_validator_integrity(run_dir, phase, state.run_start_time, recorded_hash=state.validator_hash)
            result.integrity_ok = integrity["integrity_ok"]
            result.integrity_details = integrity

            # Store loong_megatron_sha
            if result.loong_megatron_sha is not None:
                state.loong_megatron_sha = result.loong_megatron_sha

            # Store validator result in last_validator_summary
            state.last_validator_summary = {
                "status": result.status,
                "name": result.name,
                "integrity_ok": result.integrity_ok,
                "integrity_details": result.integrity_details,
                "failure_signature": {
                    "kind": result.failure_signature.kind,
                    "location": result.failure_signature.location,
                    "expected": result.failure_signature.expected,
                    "actual": result.failure_signature.actual,
                } if result.failure_signature else None,
                "loong_megatron_sha": result.loong_megatron_sha,
            }

            # IMPORTANT: Budget check FIRST (Pitfall 2)
            budget_breach = check_budget(budget, state.attempt + 1, state.total_attempts_used + 1, state.run_start_time)
            if budget_breach:
                state.exit_reason = budget_breach
                state.current_state = FSMState.EXIT
                _transition(state, FSMState.EXIT, run_dir, kind="validate", exit_reason=budget_breach.value)
                _write_phase_output(run_dir, phase, state, None, budget)
                state.persist(run_dir)
                return budget_breach

            if result.status == "passed":
                state.exit_reason = ExitReason.VALIDATOR_PASSED
                state = _transition(state, FSMState.EXIT, run_dir, kind="validate", verdict="passed", validator=result.name)
                _write_phase_output(run_dir, phase, state, result, budget)
                state.persist(run_dir)
                return ExitReason.VALIDATOR_PASSED

            if should_rerun_for_flake(result, phase) and result.rerun_count < DEFAULT_FLAKE_RERUN_COUNT:
                # Flake rerun: SAME attempt number (no _advance_attempt)
                state = _transition(state, FSMState.RERUN, run_dir, kind="validate_rerun", verdict="failed")
                state.persist(run_dir)
                return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

            # Normal failure: transition to DIAGNOSE
            state = _transition(state, FSMState.DIAGNOSE, run_dir, kind="validate", verdict="failed", validator=result.name)
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- DIAGNOSE: classify failure ---
        case FSMState.DIAGNOSE:
            # Reconstruct ValidatorResult from last_validator_summary
            if state.last_validator_summary is None:
                # No summary available; exit as HUMAN_NEEDED
                state.exit_reason = ExitReason.HUMAN_NEEDED
                state = _transition(state, FSMState.EXIT, run_dir, kind="diagnose", exit_reason="human_needed")
                _write_phase_output(run_dir, phase, state, None, budget)
                state.persist(run_dir)
                return ExitReason.HUMAN_NEEDED

            reconstructed_result = _reconstruct_validator_result(state.last_validator_summary)
            attempts_history = _read_attempts_history(run_dir, phase)
            diagnosis = classify_failure(reconstructed_result, attempts_history)

            if diagnosis.classification in (DiagnoseClassification.WRONG_DIRECTION, DiagnoseClassification.NEEDS_HUMAN):
                write_escalation(run_dir, phase, diagnosis.classification, diagnosis.rationale, attempts_history)
                state.exit_reason = ExitReason.HUMAN_NEEDED
                state = _transition(state, FSMState.EXIT, run_dir, kind="diagnose", exit_reason="human_needed")
                _write_phase_output(run_dir, phase, state, None, budget)
                state.persist(run_dir)
                return ExitReason.HUMAN_NEEDED

            # CODE_BUG or FLAKY: transition to ISSUE
            state = _transition(state, FSMState.ISSUE, run_dir, kind="diagnose", verdict=diagnosis.classification.value)
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- ISSUE: open GitHub issue ---
        case FSMState.ISSUE:
            if repos_info:
                owner_repo = repos_info.get("loongforge_repo", "")
                run_id = repos_info.get("run_id", "unknown")
                fs = state.last_validator_summary.get("failure_signature") if state.last_validator_summary else None
                validator_name = state.last_validator_summary.get("name", "") if state.last_validator_summary else ""
                issue_result = gh.open_issue(
                    owner_repo,
                    run_id=run_id, phase=phase, attempt=state.attempt,
                    validator_name=validator_name,
                    failure_signature=fs if fs else None,
                )
                # Parse issue number from URL
                try:
                    issue_num = int(issue_result.stdout.strip().split("/")[-1])
                    state.issue_number = issue_num
                    state.issues_opened.append(issue_num)
                except (ValueError, IndexError):
                    pass

            state = _transition(state, FSMState.FIX_PR, run_dir, kind="issue")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- Remaining states (Task 2 fills in) ---
        case FSMState.FIX_PR:
            # Advance attempt
            state = _advance_attempt(state)
            state = _transition(state, FSMState.REVIEW, run_dir, kind="fix_pr")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        case FSMState.REVIEW:
            # Advisory per P11: just log the review state
            state = _transition(state, FSMState.MERGE_FIX, run_dir, kind="review")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        case FSMState.MERGE_FIX:
            if repos_info and state.pr_number:
                owner_repo = repos_info.get("loongforge_repo", "")
                gh.merge_pr(owner_repo, state.pr_number)
            state = _transition(state, FSMState.RERUN, run_dir, kind="merge_fix")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        case FSMState.RERUN:
            megatron_repo = repos_info.get("megatron_repo") if repos_info else None
            megatron_ref = repos_info.get("megatron_ref") if repos_info else None
            result = run_validator(run_dir, phase, gh, megatron_repo=megatron_repo, megatron_ref=megatron_ref)

            # Call check_validator_integrity with recorded_hash
            integrity = check_validator_integrity(run_dir, phase, state.run_start_time, recorded_hash=state.validator_hash)
            result.integrity_ok = integrity["integrity_ok"]
            result.integrity_details = integrity

            # Store result in last_validator_summary
            state.last_validator_summary = {
                "status": result.status,
                "name": result.name,
                "integrity_ok": result.integrity_ok,
                "integrity_details": result.integrity_details,
                "failure_signature": {
                    "kind": result.failure_signature.kind,
                    "location": result.failure_signature.location,
                    "expected": result.failure_signature.expected,
                    "actual": result.failure_signature.actual,
                } if result.failure_signature else None,
                "loong_megatron_sha": result.loong_megatron_sha,
            }

            if result.loong_megatron_sha is not None:
                state.loong_megatron_sha = result.loong_megatron_sha

            # Budget check FIRST
            budget_breach = check_budget(budget, state.attempt + 1, state.total_attempts_used + 1, state.run_start_time)
            if budget_breach:
                state.exit_reason = budget_breach
                state.current_state = FSMState.EXIT
                _transition(state, FSMState.EXIT, run_dir, kind="rerun", exit_reason=budget_breach.value)
                _write_phase_output(run_dir, phase, state, None, budget)
                state.persist(run_dir)
                return budget_breach

            if result.status == "passed":
                state.exit_reason = ExitReason.VALIDATOR_PASSED_AFTER_FIX
                state = _transition(state, FSMState.EXIT, run_dir, kind="rerun", verdict="passed")
                _write_phase_output(run_dir, phase, state, result, budget)
                state.persist(run_dir)
                return ExitReason.VALIDATOR_PASSED_AFTER_FIX

            # Failed: transition to DIAGNOSE
            state = _transition(state, FSMState.DIAGNOSE, run_dir, kind="rerun", verdict="failed")
            state.persist(run_dir)
            return run_phase_loop(run_dir, phase, gh, budget, dry_run, max_iterations - 1, repos_info)

        # --- EXIT: return exit_reason ---
        case FSMState.EXIT:
            # Safety net: write phase_output if not already written with validator_integrity
            output_path = run_dir / "phases" / f"phase{phase}_output.yml"
            needs_write = True
            if output_path.exists():
                try:
                    existing = yaml.safe_load(output_path.read_text()) or {}
                    if "validator_integrity" in existing:
                        needs_write = False
                except Exception:
                    pass
            if needs_write:
                _write_phase_output(run_dir, phase, state, None, budget)
            state.persist(run_dir)
            return state.exit_reason or ExitReason.EXHAUSTED

        case _:
            # Unknown state -- should never happen
            state.exit_reason = ExitReason.EXHAUSTED
            state.persist(run_dir)
            return ExitReason.EXHAUSTED
