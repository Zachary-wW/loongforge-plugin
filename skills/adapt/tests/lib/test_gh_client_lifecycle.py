"""Comprehensive lifecycle tests for GhClient via FakeGhClient.

Covers: PR lifecycle, issue lifecycle, policy guards (ProtectedPathError,
HumanCommitError, DirectPushError), idempotency, dedup, label verification,
end-to-end fix loop.

No subprocess mocking -- all tests use FakeGhClient state machine injection.
"""
from __future__ import annotations

import pytest

from skills.adapt.lib.gh_client import (
    DirectPushError,
    FakeGhClient,
    GhResult,
    HumanCommitError,
    ProtectedPathError,
)
from skills.adapt.lib.idempotency import compute_dedup_key, compute_idempotency_key, parse_footer


# ---------------------------------------------------------------------------
# TestBranchCreation
# ---------------------------------------------------------------------------

class TestBranchCreation:
    def test_create_branch_ok(self):
        """Create branch with valid name and non-default base succeeds."""
        fake = FakeGhClient()
        r = fake.create_branch("Zachary-wW/LoongForge", "adapt/run1/phase1/attempt0", "develop")
        assert r.returncode == 0

    def test_create_branch_invalid_name(self):
        """Invalid branch name format raises ValueError."""
        fake = FakeGhClient()
        with pytest.raises(ValueError, match="Invalid branch name"):
            fake.create_branch("Zachary-wW/LoongForge", "feature/foo", "main")

    def test_create_branch_fork_from_default_is_allowed(self):
        """Basing a feature branch off the default branch is normal and allowed (PR-01 fix)."""
        fake = FakeGhClient()
        # Zachary-wW/LoongForge default is "main" — basing off it is fine
        result = fake.create_branch("Zachary-wW/LoongForge", "adapt/run1/phase1/attempt0", "main")
        assert result.returncode == 0

    def test_create_branch_branch_name_equals_default_raises(self):
        """Naming the new branch the same as the default branch raises DirectPushError."""
        fake = FakeGhClient()
        # The _BRANCH_RE won't match "main" anyway, but the DirectPushError
        # guard catches branch == default_branch (direct push to protected).
        fake._default_branches["Zachary-wW/LoongForge"] = "adapt/run1/phase1/attempt0"
        with pytest.raises(DirectPushError):
            fake.create_branch("Zachary-wW/LoongForge", "adapt/run1/phase1/attempt0", "develop")

    def test_create_branch_recorded(self):
        """Call is recorded in FakeGhClient.calls."""
        fake = FakeGhClient()
        fake.create_branch("Zachary-wW/LoongForge", "adapt/run1/phase1/attempt0", "develop")
        assert any(c.method == "create_branch" for c in fake.calls)


# ---------------------------------------------------------------------------
# TestPrLifecycle
# ---------------------------------------------------------------------------

class TestPrLifecycle:
    def test_open_pr_ok(self):
        """Open PR with full template params; verify title/body contain expected fields."""
        fake = FakeGhClient()
        r = fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase2/attempt1",
            "develop",
            run_id="run1", phase=2, attempt=1,
            validator="loss-diff", kind="fix", fixes_issue=5,
        )
        assert r.returncode == 0
        assert "pull/" in r.stdout
        # Check PR record
        pr = list(fake._pr_store.values())[0]
        assert "run1" in pr.title
        assert "phase-2" in pr.title or "phase-2" in pr.title.lower() or "phase 2" in pr.title
        assert "attempt-1" in pr.title or "attempt-1" in pr.title.lower() or "attempt 1" in pr.title
        assert "loss-diff" in pr.title
        assert "fix" in pr.title.lower()

    def test_open_pr_base_no_fixes(self):
        """Base PR body does NOT contain 'Fixes #'."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0",
            "develop",
            run_id="run1", phase=1, attempt=0, kind="base",
        )
        pr = list(fake._pr_store.values())[0]
        assert "Fixes #" not in pr.body

    def test_open_pr_fixes_issue(self):
        """Fix PR body contains 'Fixes #N'."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0",
            "develop",
            run_id="run1", phase=1, attempt=0, kind="fix", fixes_issue=7,
        )
        pr = list(fake._pr_store.values())[0]
        assert "Fixes #7" in pr.body

    def test_open_pr_idempotency_footer(self):
        """PR body contains idempotency footer markers."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0",
            "develop",
            run_id="run1", phase=1, attempt=0,
        )
        pr = list(fake._pr_store.values())[0]
        assert "<!-- adapt-skill:" in pr.body
        assert "[adapt-skill-key:" in pr.body

    def test_open_pr_labels(self):
        """Created PR has the correct labels."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase2/attempt0",
            "develop",
            run_id="run1", phase=2, attempt=0,
        )
        pr = list(fake._pr_store.values())[0]
        assert "loongforge-adapt" in pr.labels
        assert "run-run1" in pr.labels
        assert "phase-2" in pr.labels

    def test_open_pr_protected_path(self):
        """Protected path in diff raises ProtectedPathError."""
        fake = FakeGhClient()
        fake._protected_paths_in_diff = ["skills/adapt/scripts/validate_phase_completion.py"]
        with pytest.raises(ProtectedPathError) as exc_info:
            fake.open_pr(
                "Zachary-wW/LoongForge",
                "adapt/run1/phase1/attempt0",
                "develop",
                run_id="run1", phase=1, attempt=0,
            )
        assert "validate_phase_completion.py" in str(exc_info.value.paths)

    def test_open_pr_human_commit_no_existing_pr(self):
        """Human commits detected with no existing PR raises HumanCommitError without comment."""
        fake = FakeGhClient()
        fake._human_commit_branches = {"adapt/run1/phase1/attempt0"}
        with pytest.raises(HumanCommitError):
            fake.open_pr(
                "Zachary-wW/LoongForge",
                "adapt/run1/phase1/attempt0",
                "develop",
                run_id="run1", phase=1, attempt=0,
            )

    def test_open_pr_human_commit_with_existing_pr(self):
        """Human commits detected WITH existing PR: HumanCommitError raised AND /agent-resume comment posted."""
        fake = FakeGhClient()
        # First, open a normal PR
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0",
            "develop",
            run_id="run1", phase=1, attempt=0,
        )
        pr_before = list(fake._pr_store.values())[0]
        assert len(pr_before.comments) == 0

        # Now set human commits flag and try to open another PR on same branch
        fake._human_commit_branches = {"adapt/run1/phase1/attempt0"}
        with pytest.raises(HumanCommitError):
            fake.open_pr(
                "Zachary-wW/LoongForge",
                "adapt/run1/phase1/attempt0",
                "develop",
                run_id="run1", phase=1, attempt=0,
            )

        # Verify /agent-resume comment was posted on the existing PR (D-01)
        assert len(pr_before.comments) == 1
        assert "/agent-resume" in pr_before.comments[0]

    def test_merge_pr_ok(self):
        """Merge PR transitions state to 'merged' with merged_sha set."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0",
            "develop",
            run_id="run1", phase=1, attempt=0,
        )
        r = fake.merge_pr("Zachary-wW/LoongForge", 1)
        assert r.returncode == 0
        pr = fake._pr_store[("Zachary-wW/LoongForge", 1)]
        assert pr.state == "merged"
        assert pr.merged_sha == "fake-sha-1"

    def test_merge_pr_not_found(self):
        """Merging non-existent PR returns error GhResult."""
        fake = FakeGhClient()
        r = fake.merge_pr("Zachary-wW/LoongForge", 999)
        assert r.returncode != 0

    def test_find_pr_by_idempotency_key(self):
        """find_by_idempotency_key returns PR number for known key."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0",
            "develop",
            run_id="run1", phase=1, attempt=0,
        )
        pr = list(fake._pr_store.values())[0]
        key = pr.idempotency_key
        assert key is not None
        found = fake.find_by_idempotency_key("Zachary-wW/LoongForge", "pr", key)
        assert found == 1

    def test_find_pr_not_found(self):
        """find_by_idempotency_key with unknown key returns None."""
        fake = FakeGhClient()
        result = fake.find_by_idempotency_key("Zachary-wW/LoongForge", "pr", "nonexistent-key")
        assert result is None

    def test_pr_state_after_open(self):
        """PR record has state='open' after creation."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0",
            "develop",
            run_id="run1", phase=1, attempt=0,
        )
        pr = list(fake._pr_store.values())[0]
        assert pr.state == "open"


# ---------------------------------------------------------------------------
# TestIssueLifecycle
# ---------------------------------------------------------------------------

class TestIssueLifecycle:
    def test_open_issue_ok(self):
        """Open issue with failure_signature; verify title and body."""
        fake = FakeGhClient()
        r = fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42",
                               "expected": "0.99", "actual": "0.85"},
            log_excerpt="error: loss mismatch",
            attempts_jsonl_link="http://example.com/attempts.jsonl",
            reproduction_cmd="python test.py",
        )
        assert r.returncode == 0
        assert "issues/" in r.stdout
        issue = list(fake._issue_store.values())[0]
        assert "phase-2" in issue.title
        assert "loss-diff" in issue.title
        # Body should contain failure signature table
        assert "numerical_mismatch" in issue.body
        assert "model.py:L42" in issue.body

    def test_open_issue_dedup(self):
        """Same (phase, validator, failure_signature) appends comment, does not duplicate (D-02, ISSUE-03)."""
        fake = FakeGhClient()
        sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        # First issue
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff", failure_signature=sig,
            log_excerpt="error1",
            attempts_jsonl_link="http://example.com/log1",
            reproduction_cmd="python test.py",
        )
        # Same signature, different attempt
        r2 = fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=1,
            validator_name="loss-diff", failure_signature=sig,
            log_excerpt="error2",
            attempts_jsonl_link="http://example.com/log2",
            reproduction_cmd="python test.py",
        )
        # Second call should be a comment, not a new issue
        assert "comment on #" in r2.stdout
        # Only one issue should have been created
        assert fake._next_issue_number - 1 == 1

    def test_open_issue_dedup_different_signature(self):
        """Different failure signatures create separate issues."""
        fake = FakeGhClient()
        sig1 = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        sig2 = {"kind": "shape_mismatch", "location": "model.py:L10"}
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff", failure_signature=sig1,
            log_excerpt="error1",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff", failure_signature=sig2,
            log_excerpt="error2",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        assert fake._next_issue_number - 1 == 2

    def test_open_issue_labels(self):
        """Created issue has correct labels."""
        fake = FakeGhClient()
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42"},
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        issue = list(fake._issue_store.values())[0]
        assert "loongforge-adapt" in issue.labels
        assert "run-run1" in issue.labels
        assert "phase-2" in issue.labels

    def test_close_issue_ok(self):
        """Close issue transitions state to 'closed' and appends comment."""
        fake = FakeGhClient()
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42"},
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        r = fake.close_issue("Zachary-wW/LoongForge", 1, run_id="run1", phase=2)
        assert r.returncode == 0
        issue = fake._issue_store[("Zachary-wW/LoongForge", 1)]
        assert issue.state == "closed"
        assert len(issue.comments) >= 1

    def test_close_issue_not_found(self):
        """Closing non-existent issue returns error GhResult."""
        fake = FakeGhClient()
        r = fake.close_issue("Zachary-wW/LoongForge", 999)
        assert r.returncode != 0

    def test_find_issue_by_idempotency_key(self):
        """find_by_idempotency_key(kind='issue') returns issue number."""
        fake = FakeGhClient()
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42"},
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        issue = list(fake._issue_store.values())[0]
        key = issue.idempotency_key
        assert key is not None
        found = fake.find_by_idempotency_key("Zachary-wW/LoongForge", "issue", key)
        assert found == 1

    def test_find_issue_by_dedup_key(self):
        """find_by_dedup_key returns issue number for known dedup key."""
        fake = FakeGhClient()
        sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff", failure_signature=sig,
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        dedup_key = compute_dedup_key(2, "loss-diff", sig)
        found = fake.find_by_dedup_key("Zachary-wW/LoongForge", dedup_key)
        assert found == 1

    def test_find_dedup_key_not_found(self):
        """find_by_dedup_key with unknown key returns None."""
        fake = FakeGhClient()
        result = fake.find_by_dedup_key("Zachary-wW/LoongForge", "nonexistent-dedup-key")
        assert result is None

    def test_close_issue_with_custom_comment(self):
        """Passing explicit comment uses that instead of default closing_summary."""
        fake = FakeGhClient()
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42"},
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        custom = "Custom closing remark"
        fake.close_issue("Zachary-wW/LoongForge", 1, comment=custom)
        issue = fake._issue_store[("Zachary-wW/LoongForge", 1)]
        assert custom in issue.comments


# ---------------------------------------------------------------------------
# TestDedupKeyVsIdempotencyKey
# ---------------------------------------------------------------------------

class TestDedupKeyVsIdempotencyKey:
    def test_dedup_key_differs_from_idempotency_key(self):
        """Dedup key and idempotency key are different hex strings."""
        sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        idem_key = compute_idempotency_key("run1", 2, 0, "issue")
        dedup_key = compute_dedup_key(2, "loss-diff", sig)
        assert idem_key != dedup_key

    def test_dedup_finds_by_dedup_key_not_idempotency_key(self):
        """find_by_idempotency_key with dedup key returns None; find_by_dedup_key succeeds."""
        fake = FakeGhClient()
        sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff", failure_signature=sig,
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        dedup_key = compute_dedup_key(2, "loss-diff", sig)
        # Searching by idempotency key kind with a dedup key value returns None
        result = fake.find_by_idempotency_key("Zachary-wW/LoongForge", "issue", dedup_key)
        assert result is None
        # Searching by dedup key succeeds
        result2 = fake.find_by_dedup_key("Zachary-wW/LoongForge", dedup_key)
        assert result2 == 1


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_full_fix_loop(self):
        """create_branch -> open_pr(base) -> merge -> open_issue -> open_pr(fix) -> merge -> close_issue."""
        fake = FakeGhClient()
        owner = "Zachary-wW/LoongForge"

        # 1. Create branch (base="develop" since "main" is default for this repo)
        r = fake.create_branch(owner, "adapt/run1/phase2/attempt0", "develop")
        assert r.returncode == 0

        # 2. Open base PR
        r = fake.open_pr(owner, "adapt/run1/phase2/attempt0", "develop",
                         run_id="run1", phase=2, attempt=0, kind="base")
        assert r.returncode == 0
        pr_base_num = 1

        # 3. Merge base PR
        r = fake.merge_pr(owner, pr_base_num)
        assert r.returncode == 0
        assert fake._pr_store[(owner, pr_base_num)].state == "merged"

        # 4. Open issue (validator failure)
        sig = {"kind": "numerical_mismatch", "location": "model.py:L42"}
        r = fake.open_issue(owner, run_id="run1", phase=2, attempt=0,
                            validator_name="loss-diff", failure_signature=sig,
                            log_excerpt="error",
                            attempts_jsonl_link="http://example.com/log",
                            reproduction_cmd="python test.py")
        assert r.returncode == 0
        issue_num = 1

        # 5. Open fix PR referencing the issue
        fake.create_branch(owner, "adapt/run1/phase2/attempt1", "develop")
        r = fake.open_pr(owner, "adapt/run1/phase2/attempt1", "develop",
                         run_id="run1", phase=2, attempt=1, kind="fix",
                         validator="loss-diff", fixes_issue=issue_num)
        assert r.returncode == 0
        pr_fix_num = 2
        fix_pr = fake._pr_store[(owner, pr_fix_num)]
        assert f"Fixes #{issue_num}" in fix_pr.body

        # 6. Merge fix PR
        r = fake.merge_pr(owner, pr_fix_num)
        assert r.returncode == 0

        # 7. Close issue
        r = fake.close_issue(owner, issue_num, run_id="run1", phase=2)
        assert r.returncode == 0
        assert fake._issue_store[(owner, issue_num)].state == "closed"

        # Verify all labels present
        for key, pr in fake._pr_store.items():
            assert "loongforge-adapt" in pr.labels
        for key, issue in fake._issue_store.items():
            assert "loongforge-adapt" in issue.labels

    def test_idempotency_across_resets(self):
        """find_by_idempotency_key returns same PR number after re-opening with same params."""
        fake = FakeGhClient()
        owner = "Zachary-wW/LoongForge"

        # Open first PR
        fake.open_pr(owner, "adapt/run1/phase1/attempt0", "develop",
                     run_id="run1", phase=1, attempt=0)
        pr1 = fake._pr_store[(owner, 1)]
        key = pr1.idempotency_key

        # Find by idempotency key
        found = fake.find_by_idempotency_key(owner, "pr", key)
        assert found == 1

        # Open another PR with different params
        fake.open_pr(owner, "adapt/run1/phase1/attempt1", "develop",
                     run_id="run1", phase=1, attempt=1)

        # Original PR still findable
        found_again = fake.find_by_idempotency_key(owner, "pr", key)
        assert found_again == 1

        # New PR has different key
        pr2 = fake._pr_store[(owner, 2)]
        assert pr2.idempotency_key != key


# ---------------------------------------------------------------------------
# TestViewMethods
# ---------------------------------------------------------------------------

class TestViewMethods:
    def test_view_pr_returns_none_for_nonexistent(self):
        """FakeGhClient.view_pr returns None for non-existent PR."""
        fake = FakeGhClient()
        result = fake.view_pr("Zachary-wW/LoongForge", 999)
        assert result is None

    def test_view_pr_returns_state_for_existing(self):
        """FakeGhClient.view_pr returns dict with state/merged/merge_commit_sha/head_branch for existing PR."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0", "develop",
            run_id="run1", phase=1, attempt=0,
        )
        result = fake.view_pr("Zachary-wW/LoongForge", 1)
        assert result is not None
        assert result["state"] == "OPEN"
        assert result["merged"] is False
        assert result["merge_commit_sha"] is None
        assert result["head_branch"] == "adapt/run1/phase1/attempt0"

    def test_view_issue_returns_none_for_nonexistent(self):
        """FakeGhClient.view_issue returns None for non-existent issue."""
        fake = FakeGhClient()
        result = fake.view_issue("Zachary-wW/LoongForge", 999)
        assert result is None

    def test_view_issue_returns_state_for_existing(self):
        """FakeGhClient.view_issue returns dict with state for existing issue."""
        fake = FakeGhClient()
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42"},
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        result = fake.view_issue("Zachary-wW/LoongForge", 1)
        assert result is not None
        assert result["state"] == "OPEN"

    def test_view_pr_reflects_state_after_merge(self):
        """FakeGhClient.view_pr reflects state changes after merge_pr."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0", "develop",
            run_id="run1", phase=1, attempt=0,
        )
        fake.merge_pr("Zachary-wW/LoongForge", 1)
        result = fake.view_pr("Zachary-wW/LoongForge", 1)
        assert result is not None
        assert result["state"] == "MERGED"
        assert result["merged"] is True
        assert result["merge_commit_sha"] is not None

    def test_view_issue_reflects_state_after_close(self):
        """FakeGhClient.view_issue reflects state changes after close_issue."""
        fake = FakeGhClient()
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42"},
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        fake.close_issue("Zachary-wW/LoongForge", 1, run_id="run1", phase=2)
        result = fake.view_issue("Zachary-wW/LoongForge", 1)
        assert result is not None
        assert result["state"] == "CLOSED"

    def test_view_pr_records_call_in_fake(self):
        """FakeGhClient records view_pr calls."""
        fake = FakeGhClient()
        fake.open_pr(
            "Zachary-wW/LoongForge",
            "adapt/run1/phase1/attempt0", "develop",
            run_id="run1", phase=1, attempt=0,
        )
        fake.view_pr("Zachary-wW/LoongForge", 1)
        assert any(c.method == "view_pr" for c in fake.calls)

    def test_view_issue_records_call_in_fake(self):
        """FakeGhClient records view_issue calls."""
        fake = FakeGhClient()
        fake.open_issue(
            "Zachary-wW/LoongForge",
            run_id="run1", phase=2, attempt=0,
            validator_name="loss-diff",
            failure_signature={"kind": "numerical_mismatch", "location": "model.py:L42"},
            log_excerpt="error",
            attempts_jsonl_link="http://example.com/log",
            reproduction_cmd="python test.py",
        )
        fake.view_issue("Zachary-wW/LoongForge", 1)
        assert any(c.method == "view_issue" for c in fake.calls)
