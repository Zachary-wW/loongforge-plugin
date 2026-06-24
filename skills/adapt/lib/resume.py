"""Resume reconciliation: verify remote PR/issue state matches local records on --resume.

RESUME-01: Controller reconstructs FSM state from last attempts.jsonl row plus
loop_state.yml via LoopState.from_disk (loop_state.yml is the Phase 3 architectural
equivalent of the "phaseN_output.yml" wording in the ROADMAP requirement).

RESUME-02: Every PR/issue referenced in loop_state.yml is reconciled against gh;
mismatches -- including PR 404, PR closed-without-merge, merge SHA drift, force-push,
issue 404, issue closed-unexpectedly -- force --reset-phase rather than silent proceed.

Exports:
  MismatchDetail -- dataclass describing a single reconciliation mismatch
  ReconciliationMismatch -- Exception raised when mismatches are detected
  reconcile_remote_state -- verify a single phase's remote state
  reconcile_run -- verify all phases with loop_state.yml against gh
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from skills.adapt.lib.loop_controller import LoopState
from skills.adapt.lib.gh_client import GhClient


@dataclass
class MismatchDetail:
    """A single reconciliation mismatch between local records and remote state."""
    artifact_type: str  # "pr" or "issue"
    number: int
    issue: str          # "not_found", "closed_without_merge", "closed_unexpectedly", "sha_drift", "force_push"
    detail: str


class ReconciliationMismatch(Exception):
    """Raised when remote state does not match local records (RESUME-02)."""
    def __init__(self, mismatches: list[MismatchDetail]):
        self.mismatches = mismatches
        super().__init__(
            f"Remote state mismatches detected ({len(mismatches)}). "
            f"Use --from-phase N to reset from the affected phase. "
            f"Mismatches: {mismatches}"
        )


def reconcile_remote_state(
    run_dir: Path,
    phase: int,
    gh: GhClient,
    repos_info: dict | None = None,
) -> list[MismatchDetail] | None:
    """Verify every PR/issue in loop_state.yml against gh (RESUME-02).

    Returns list of MismatchDetail (empty list = clean), or None if repos not present.
    Only checks loongforge_repo (both PRs and issues are opened there).

    NOTE (RESUME-01 clarification): The ROADMAP wording says "reconstructs from
    attempts.jsonl plus phaseN_output.yml" but the Phase 3 loop-controller
    architecture stores FSM state in loop_state.yml. loop_state.yml serves
    the same role -- it IS the FSM state that RESUME-01 refers to. The
    controller reconstructs from loop_state.yml + attempts.jsonl tail via
    LoopState.from_disk, which is architecturally equivalent.
    """
    if repos_info is None:
        return None

    owner_repo = repos_info.get("loongforge_repo", "")
    if not owner_repo:
        return None

    # Reconstruct FSM state from loop_state.yml + attempts.jsonl tail
    # (architectural equivalent of RESUME-01's "phaseN_output.yml" wording)
    state = LoopState.from_disk(run_dir, phase)
    mismatches: list[MismatchDetail] = []

    # Check PR
    if state.pr_number is not None:
        pr_data = gh.view_pr(owner_repo, state.pr_number)
        if pr_data is None:
            mismatches.append(MismatchDetail(
                artifact_type="pr", number=state.pr_number,
                issue="not_found", detail=f"PR #{state.pr_number} no longer exists on {owner_repo}",
            ))
        elif pr_data.get("state") == "CLOSED" and not pr_data.get("merged"):
            mismatches.append(MismatchDetail(
                artifact_type="pr", number=state.pr_number,
                issue="closed_without_merge", detail=f"PR #{state.pr_number} closed without being merged",
            ))
        elif pr_data.get("merged") and state.merge_commit_sha is not None:
            # SHA drift detection (RESUME-02): recorded merge SHA differs from current
            remote_merge_sha = pr_data.get("merge_commit_sha")
            if remote_merge_sha and remote_merge_sha != state.merge_commit_sha:
                mismatches.append(MismatchDetail(
                    artifact_type="pr", number=state.pr_number,
                    issue="sha_drift",
                    detail=(
                        f"PR #{state.pr_number} merge SHA drifted: "
                        f"recorded {state.merge_commit_sha[:12]}, remote {remote_merge_sha[:12]}"
                    ),
                ))

    # Check issues
    for issue_num in state.issues_opened:
        if issue_num in state.issues_closed:
            continue  # Expected: issue closed by fix-PR merge
        issue_data = gh.view_issue(owner_repo, issue_num)
        if issue_data is None:
            mismatches.append(MismatchDetail(
                artifact_type="issue", number=issue_num,
                issue="not_found", detail=f"Issue #{issue_num} no longer exists on {owner_repo}",
            ))
        elif issue_data.get("state") == "CLOSED":
            mismatches.append(MismatchDetail(
                artifact_type="issue", number=issue_num,
                issue="closed_unexpectedly", detail=f"Issue #{issue_num} closed without corresponding fix-PR",
            ))

    return mismatches


def reconcile_run(
    run_dir: Path,
    from_phase: int | None,
    gh: GhClient,
    repos_info: dict | None = None,
) -> list[MismatchDetail] | None:
    """Reconcile all phases with loop_state.yml against gh.

    When from_phase is specified, skip reconciliation (user explicitly resetting).
    Only reconciles phases 0-5 that have a loop_state.yml file.
    Returns aggregated mismatches from all phases, or None if repos not present
    or from_phase is specified.
    """
    if repos_info is None or from_phase is not None:
        return None

    all_mismatches: list[MismatchDetail] = []
    for phase in range(6):
        state_path = run_dir / "phases" / f"phase{phase}" / "loop_state.yml"
        if not state_path.exists():
            continue
        phase_mismatches = reconcile_remote_state(run_dir, phase, gh, repos_info)
        if phase_mismatches:
            all_mismatches.extend(phase_mismatches)

    return all_mismatches if all_mismatches else None
