"""Tests for resume.py: reconcile_remote_state, reconcile_run, TEST-04 resume idempotency.

Covers RESUME-01 (FSM reconstruction from loop_state.yml), RESUME-02 (remote PR/issue
reconciliation with SHA drift/force-push detection), and TEST-04 (kill mid-Diagnose/mid-Issue
and resume produces zero duplicate artifacts).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml
import pytest

from skills.adapt.lib.gh_client import FakeGhClient
from skills.adapt.lib.loop_controller import LoopState, FSMState
from skills.adapt.lib.schema import LoopBudget
from skills.adapt.tests.lib.test_loop_controller import _setup_run_dir, _write_loop_state


# ---------------------------------------------------------------------------
# TestReconcileRemoteState
# ---------------------------------------------------------------------------

class TestReconcileRemoteState:
    """Tests for reconcile_remote_state (RESUME-02)."""

    def _make_repos_info(self, loongforge_repo="Zachary-wW/LoongForge"):
        return {"loongforge_repo": loongforge_repo}

    def test_returns_none_when_repos_info_is_none(self, tmp_path):
        """reconcile_remote_state returns None when repos_info is None (legacy mode)."""
        from skills.adapt.lib.resume import reconcile_remote_state
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=None)
        assert result is None

    def test_returns_empty_list_when_all_match(self, tmp_path):
        """reconcile_remote_state returns empty list when PR and issues match remote state."""
        from skills.adapt.lib.resume import reconcile_remote_state
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Open a PR and merge it
        gh.open_pr(owner, "adapt/run1/phase1/attempt0", "develop",
                    run_id="run1", phase=1, attempt=0)
        gh.merge_pr(owner, 1)
        # Write loop_state matching this PR
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1,
                         pr_number=1, merge_commit_sha="fake-sha-1")
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert result == []

    def test_returns_mismatch_when_pr_is_404(self, tmp_path):
        """reconcile_remote_state returns mismatch when PR is 404 (view_pr returns None)."""
        from skills.adapt.lib.resume import reconcile_remote_state, MismatchDetail
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        # No PR created in FakeGhClient -> view_pr returns None
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1, pr_number=999)
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert result is not None
        assert len(result) == 1
        assert result[0].artifact_type == "pr"
        assert result[0].issue == "not_found"

    def test_returns_mismatch_when_pr_closed_without_merge(self, tmp_path):
        """reconcile_remote_state returns mismatch when PR is closed without being merged."""
        from skills.adapt.lib.resume import reconcile_remote_state, MismatchDetail
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Open a PR then close it without merging
        gh.open_pr(owner, "adapt/run1/phase1/attempt0", "develop",
                    run_id="run1", phase=1, attempt=0)
        # Manually set state to closed (not merged)
        pr = gh._pr_store[(owner, 1)]
        pr.state = "closed"
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1, pr_number=1)
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert result is not None
        assert len(result) == 1
        assert result[0].issue == "closed_without_merge"

    def test_returns_mismatch_when_issue_is_404(self, tmp_path):
        """reconcile_remote_state returns mismatch when issue is deleted (view_issue returns None)."""
        from skills.adapt.lib.resume import reconcile_remote_state, MismatchDetail
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        # No issue created in FakeGhClient -> view_issue returns None
        _write_loop_state(run_dir, phase=1, current_state="diagnose", attempt=1,
                         issues_opened=[999])
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert result is not None
        assert any(m.issue == "not_found" and m.artifact_type == "issue" for m in result)

    def test_returns_mismatch_when_issue_closed_unexpectedly(self, tmp_path):
        """reconcile_remote_state returns mismatch when issue closed but not in issues_closed list."""
        from skills.adapt.lib.resume import reconcile_remote_state, MismatchDetail
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Open an issue then close it externally
        gh.open_issue(owner, run_id="run1", phase=1, attempt=0,
                       validator_name="phase1-verify",
                       failure_signature={"kind": "missing_artifact", "location": "model.py"},
                       log_excerpt="error",
                       attempts_jsonl_link="http://example.com/log",
                       reproduction_cmd="python test.py")
        issue = gh._issue_store[(owner, 1)]
        issue.state = "closed"  # Closed externally
        # Write loop_state with issue in issues_opened but NOT in issues_closed
        _write_loop_state(run_dir, phase=1, current_state="diagnose", attempt=1,
                         issues_opened=[1], issues_closed=[])
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert result is not None
        assert any(m.issue == "closed_unexpectedly" for m in result)

    def test_no_mismatch_for_issue_closed_by_fix_pr(self, tmp_path):
        """reconcile_remote_state does NOT report mismatch for issue closed by fix-PR (in issues_closed list)."""
        from skills.adapt.lib.resume import reconcile_remote_state
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Open and close issue normally
        gh.open_issue(owner, run_id="run1", phase=1, attempt=0,
                       validator_name="phase1-verify",
                       failure_signature={"kind": "missing_artifact", "location": "model.py"},
                       log_excerpt="error",
                       attempts_jsonl_link="http://example.com/log",
                       reproduction_cmd="python test.py")
        gh.close_issue(owner, 1, run_id="run1", phase=1)
        # Write loop_state with issue in both issues_opened and issues_closed
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1,
                         issues_opened=[1], issues_closed=[1])
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        # No mismatch for closed issues that are in issues_closed
        assert not any(m.artifact_type == "issue" for m in (result or []))

    def test_returns_mismatch_for_merge_sha_drift(self, tmp_path):
        """reconcile_remote_state returns mismatch for merge SHA drift (RESUME-02)."""
        from skills.adapt.lib.resume import reconcile_remote_state, MismatchDetail
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Open and merge a PR
        gh.open_pr(owner, "adapt/run1/phase1/attempt0", "develop",
                    run_id="run1", phase=1, attempt=0)
        gh.merge_pr(owner, 1)  # merge_commit_sha = "fake-sha-1"
        # Write loop_state with a DIFFERENT merge_commit_sha (simulating SHA drift)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1,
                         pr_number=1, merge_commit_sha="different-sha-xyz789")
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert result is not None
        assert any(m.issue == "sha_drift" for m in result)

    def test_no_mismatch_when_merge_sha_matches(self, tmp_path):
        """reconcile_remote_state does NOT report SHA drift when merge_commit_sha matches."""
        from skills.adapt.lib.resume import reconcile_remote_state
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Open and merge a PR
        gh.open_pr(owner, "adapt/run1/phase1/attempt0", "develop",
                    run_id="run1", phase=1, attempt=0)
        gh.merge_pr(owner, 1)  # merge_commit_sha = "fake-sha-1"
        # Write loop_state with MATCHING merge_commit_sha
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1,
                         pr_number=1, merge_commit_sha="fake-sha-1")
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert not any(m.issue == "sha_drift" for m in (result or []))

    def test_force_push_detected_as_sha_drift(self, tmp_path):
        """Force-push detected as SHA drift when merge_commit_sha changes after re-merge (RESUME-02)."""
        from skills.adapt.lib.resume import reconcile_remote_state, MismatchDetail
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Open and merge a PR
        gh.open_pr(owner, "adapt/run1/phase1/attempt0", "develop",
                    run_id="run1", phase=1, attempt=0)
        gh.merge_pr(owner, 1)  # merge_commit_sha = "fake-sha-1"
        # Simulate force-push + re-merge by changing merge_commit_sha on the record
        pr = gh._pr_store[(owner, 1)]
        pr.merge_commit_sha = "new-sha-after-force-push"
        # Write loop_state with original merge_commit_sha
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1,
                         pr_number=1, merge_commit_sha="fake-sha-1")
        result = reconcile_remote_state(run_dir, 1, gh, repos_info=self._make_repos_info())
        assert result is not None
        assert any(m.issue == "sha_drift" for m in result)


# ---------------------------------------------------------------------------
# TestReconcileRun
# ---------------------------------------------------------------------------

class TestReconcileRun:
    def test_reconcile_run_iterates_all_phases(self, tmp_path):
        """reconcile_run iterates over all phases with loop_state.yml and collects mismatches."""
        from skills.adapt.lib.resume import reconcile_run, MismatchDetail
        run_dir = _setup_run_dir(tmp_path, phase=1)
        # Also set up phase2
        phase2_dir = run_dir / "phases" / "phase2"
        phase2_dir.mkdir(parents=True, exist_ok=True)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Phase 1: PR 404
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1, pr_number=999)
        # Phase 2: clean (no PR)
        _write_loop_state(run_dir, phase=2, current_state="validate", attempt=1)
        repos_info = {"loongforge_repo": owner}
        result = reconcile_run(run_dir, None, gh, repos_info=repos_info)
        assert result is not None
        assert any(m.issue == "not_found" for m in result)

    def test_reconcile_run_returns_none_when_no_mismatches(self, tmp_path):
        """reconcile_run returns None when all phases are clean."""
        from skills.adapt.lib.resume import reconcile_run
        run_dir = _setup_run_dir(tmp_path, phase=1)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        # Phase 1: no PR number
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        repos_info = {"loongforge_repo": owner}
        result = reconcile_run(run_dir, None, gh, repos_info=repos_info)
        assert result is None

    def test_reconcile_run_skips_when_from_phase(self, tmp_path):
        """reconcile_run returns None when from_phase is specified (explicit reset)."""
        from skills.adapt.lib.resume import reconcile_run
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1, pr_number=999)
        gh = FakeGhClient()
        repos_info = {"loongforge_repo": "Zachary-wW/LoongForge"}
        result = reconcile_run(run_dir, from_phase=1, gh=gh, repos_info=repos_info)
        assert result is None

    def test_reconcile_run_returns_none_when_repos_absent(self, tmp_path):
        """reconcile_run returns None when repos_info is None."""
        from skills.adapt.lib.resume import reconcile_run
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1, pr_number=999)
        gh = FakeGhClient()
        result = reconcile_run(run_dir, None, gh, repos_info=None)
        assert result is None


# ---------------------------------------------------------------------------
# TestResumeIdempotency (TEST-04)
# ---------------------------------------------------------------------------

class TestResumeIdempotency:
    """TEST-04: Kill mid-DIAGNOSE or mid-ISSUE, resume, zero duplicate artifacts."""

    def test_kill_mid_diagnose_resume_no_duplicate_issue(self, tmp_path):
        """Kill mid-DIAGNOSE (write loop_state at DIAGNOSE, open issue in FakeGhClient),
        resume with same run_dir, assert find_by_idempotency_key returns existing issue
        (no duplicate created)."""
        from skills.adapt.lib.resume import reconcile_remote_state
        from skills.adapt.lib.idempotency import compute_idempotency_key
        run_dir = _setup_run_dir(tmp_path, phase=2)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        repos_info = {"loongforge_repo": owner}
        # Simulate mid-DIAGNOSE crash: an issue was already opened
        sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        gh.open_issue(
            owner,
            run_id="run1", phase=2, attempt=1,
            validator_name="loss-diff",
            failure_signature=sig,
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        # Write loop_state at DIAGNOSE
        _write_loop_state(
            run_dir, phase=2, current_state="diagnose", attempt=1,
            issues_opened=[1],
            last_validator_summary={
                "status": "failed", "name": "loss-diff",
                "integrity_ok": True,
                "integrity_details": {"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                "failure_signature": sig,
                "loong_megatron_sha": None,
            },
        )
        # Simulate resume: try to open another issue for the same failure
        # The dedup key should find the existing issue
        from skills.adapt.lib.idempotency import compute_dedup_key
        dedup_key = compute_dedup_key(2, "loss-diff", sig)
        existing = gh.find_by_dedup_key(owner, dedup_key)
        assert existing == 1, "Should find existing issue by dedup key -- no duplicate"
        # Also try opening a new issue; dedup should kick in
        result = gh.open_issue(
            owner,
            run_id="run1", phase=2, attempt=2,
            validator_name="loss-diff",
            failure_signature=sig,
            log_excerpt="error2",
            attempts_jsonl_link="http://example.com/log2",
            reproduction_cmd="python test.py",
        )
        assert "comment on #" in result.stdout
        # Only 1 issue in the store
        assert len(gh._issue_store) == 1

    def test_kill_mid_issue_resume_no_duplicate_issue(self, tmp_path):
        """Kill mid-ISSUE (write loop_state at ISSUE with issue_number, issue exists in FakeGhClient),
        resume, assert no second issue opened for same failure signature."""
        from skills.adapt.lib.resume import reconcile_remote_state
        from skills.adapt.lib.idempotency import compute_dedup_key
        run_dir = _setup_run_dir(tmp_path, phase=2)
        gh = FakeGhClient()
        owner = "Zachary-wW/LoongForge"
        repos_info = {"loongforge_repo": owner}
        sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        # Simulate mid-ISSUE crash: issue was already opened
        gh.open_issue(
            owner,
            run_id="run1", phase=2, attempt=1,
            validator_name="loss-diff",
            failure_signature=sig,
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        # Write loop_state at ISSUE with issue_number set
        _write_loop_state(
            run_dir, phase=2, current_state="issue", attempt=1,
            issues_opened=[1], issue_number=1,
            last_validator_summary={
                "status": "failed", "name": "loss-diff",
                "integrity_ok": True,
                "integrity_details": {"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
                "failure_signature": sig,
                "loong_megatron_sha": None,
            },
        )
        # Simulate resume: re-trying to open issue for same signature
        dedup_key = compute_dedup_key(2, "loss-diff", sig)
        existing = gh.find_by_dedup_key(owner, dedup_key)
        assert existing == 1, "Should find existing issue by dedup key"
        # Opening another issue with same signature should comment, not duplicate
        result = gh.open_issue(
            owner,
            run_id="run1", phase=2, attempt=2,
            validator_name="loss-diff",
            failure_signature=sig,
            log_excerpt="error2",
            attempts_jsonl_link="http://example.com/log2",
            reproduction_cmd="python test.py",
        )
        assert "comment on #" in result.stdout
        assert len(gh._issue_store) == 1, "No duplicate issues created"


# ---------------------------------------------------------------------------
# TestReconciliationMismatch
# ---------------------------------------------------------------------------

class TestReconciliationMismatch:
    def test_mismatch_exception_message(self):
        """ReconciliationMismatch includes hint about --from-phase."""
        from skills.adapt.lib.resume import ReconciliationMismatch, MismatchDetail
        mismatches = [
            MismatchDetail(artifact_type="pr", number=42, issue="not_found",
                          detail="PR #42 no longer exists"),
        ]
        exc = ReconciliationMismatch(mismatches)
        assert "--from-phase" in str(exc)
        assert len(exc.mismatches) == 1


# ---------------------------------------------------------------------------
# TestRunResumeIntegration
# ---------------------------------------------------------------------------

class TestRunResumeIntegration:
    """Integration tests for resume_run_dir + reconciliation wiring in run.py."""

    def test_resume_with_repos_no_from_phase_calls_reconcile(self, tmp_path):
        """resume_run_dir with repos present and no from_phase triggers reconciliation on mismatch."""
        run_dir = str(_setup_run_dir(tmp_path, phase=1))
        owner = "Zachary-wW/LoongForge"
        # Write run_inputs.yml with repos block
        from skills.adapt.scripts.run import save_run_inputs
        inputs = {
            "source": {"hf_ckpt_path": "test"},
            "paths": {},
            "options": {"model_name": "test"},
            "repos": {
                "loongforge": {"url": f"https://github.com/{owner}", "base_ref": "main"},
                "hf_impl": {"url": "https://github.com/hf/transformers", "ref": "main"},
                "hf_ckpt": {"url": "https://huggingface.co/test/model", "revision": "main"},
                "megatron": {"url": "https://github.com/Zachary-wW/Loong-Megatron", "base_ref": "loong-main/core_v0.15.0"},
            },
        }
        save_run_inputs(run_dir, inputs)
        # Write a loop_state with a PR that doesn't exist in remote
        _write_loop_state(tmp_path, phase=1, current_state="validate", attempt=1, pr_number=999)
        # The reconciliation is lazy-imported inside run.py's main(),
        # so patch at the source module level.
        from skills.adapt.lib.resume import MismatchDetail
        with patch("skills.adapt.lib.resume.reconcile_run") as mock_reconcile, \
             patch("skills.adapt.lib.resume.RealGhClient", create=True), \
             patch("skills.adapt.scripts.run.RealGhClient"):
            mock_reconcile.return_value = [
                MismatchDetail(artifact_type="pr", number=999, issue="not_found",
                              detail="PR #999 not found"),
            ]
            from skills.adapt.scripts.run import main
            with pytest.raises(SystemExit) as exc_info:
                main(["--resume", run_dir])
            assert exc_info.value.code == 3

    def test_resume_with_from_phase_skips_reconciliation(self, tmp_path):
        """resume_run_dir with repos present and --from-phase N skips reconciliation (explicit reset)."""
        run_dir = str(_setup_run_dir(tmp_path, phase=1))
        owner = "Zachary-wW/LoongForge"
        from skills.adapt.scripts.run import save_run_inputs
        inputs = {
            "source": {"hf_ckpt_path": "test"},
            "paths": {},
            "options": {"model_name": "test"},
            "repos": {
                "loongforge": {"url": f"https://github.com/{owner}", "base_ref": "main"},
                "hf_impl": {"url": "https://github.com/hf/transformers", "ref": "main"},
                "hf_ckpt": {"url": "https://huggingface.co/test/model", "revision": "main"},
                "megatron": {"url": "https://github.com/Zachary-wW/Loong-Megatron", "base_ref": "loong-main/core_v0.15.0"},
            },
        }
        save_run_inputs(run_dir, inputs)
        _write_loop_state(tmp_path, phase=1, current_state="validate", attempt=1, pr_number=999)
        # With --from-phase 1, reconciliation should be skipped entirely
        with patch("skills.adapt.lib.resume.reconcile_run") as mock_reconcile:
            from skills.adapt.scripts.run import main
            try:
                main(["--resume", run_dir, "--from-phase", "1"])
            except SystemExit as e:
                assert e.code != 3, "Should not exit with code 3 when --from-phase specified"
            mock_reconcile.assert_not_called()
