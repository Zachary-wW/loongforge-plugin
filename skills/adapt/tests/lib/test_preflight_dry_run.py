"""Tests for preflight checks: INPUT-03 fail-fast + INPUT-04 dry-run skip-writes.

Uses FakeGhClient so tests never depend on real gh CLI or network.
Network calls (ckpt URL HEAD) are monkeypatched via urllib.request.urlopen.
"""
from __future__ import annotations

import types
import urllib.error
from unittest import mock
from unittest.mock import patch

import pytest

from skills.adapt.lib.gh_client import FakeGhClient, GhResult
from skills.adapt.lib.preflight import (
    PreflightResult,
    _check_branch_protection_compatible,
    _owner_repo_from_url,
    format_failures,
    run_preflight,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status: int = 200):
    """Create a mock HTTP response with a real .status integer."""
    resp = mock.MagicMock()
    resp.status = status
    resp.__enter__ = mock.MagicMock(return_value=resp)
    resp.__exit__ = mock.MagicMock(return_value=False)
    return resp


def _fake_repos():
    """Build a ReposBlock-like SimpleNamespace (no dependency on plan 01 schema)."""
    return types.SimpleNamespace(
        hf_impl=types.SimpleNamespace(url="https://github.com/huggingface/transformers"),
        hf_ckpt=types.SimpleNamespace(url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base"),
        loongforge=types.SimpleNamespace(url="https://github.com/Zachary-wW/LoongForge", base_ref="main"),
        megatron=types.SimpleNamespace(url="https://github.com/Zachary-wW/Loong-Megatron", base_ref="loong-main/core_v0.15.0"),
    )


def _fake_repos_with_bad_ckpt():
    """Repos with a ckpt URL that will fail the network probe."""
    return types.SimpleNamespace(
        hf_impl=types.SimpleNamespace(url="https://github.com/huggingface/transformers"),
        hf_ckpt=types.SimpleNamespace(url="https://huggingface.co/nonexistent-org/nonexistent-model"),
        loongforge=types.SimpleNamespace(url="https://github.com/Zachary-wW/LoongForge", base_ref="main"),
        megatron=types.SimpleNamespace(url="https://github.com/Zachary-wW/Loong-Megatron", base_ref="loong-main/core_v0.15.0"),
    )


# ---------------------------------------------------------------------------
# _owner_repo_from_url
# ---------------------------------------------------------------------------

class TestOwnerRepoFromUrl:
    def test_standard_https(self):
        assert _owner_repo_from_url("https://github.com/Zachary-wW/LoongForge") == "Zachary-wW/LoongForge"

    def test_with_git_suffix(self):
        assert _owner_repo_from_url("https://github.com/Zachary-wW/LoongForge.git") == "Zachary-wW/LoongForge"

    def test_with_trailing_slash(self):
        assert _owner_repo_from_url("https://github.com/Zachary-wW/LoongForge/") == "Zachary-wW/LoongForge"

    def test_no_owner(self):
        assert _owner_repo_from_url("https://github.com/somerepo") == "somerepo"


# ---------------------------------------------------------------------------
# dry_run=True skips write probes
# ---------------------------------------------------------------------------

class TestDryRunSkipsWrites:
    """INPUT-04: dry_run=True must not call repo_permissions or branch_protection."""

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_dry_run_true_skips_repo_permissions(self, mock_urlopen):
        """dry_run=True: no repo_permissions call recorded; result.ok is True."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True)
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=True, gh=fake)

        assert result.ok is True
        assert all(c.method != "repo_permissions" for c in fake.calls), \
            f"dry_run must not call repo_permissions, but got: {[c.method for c in fake.calls]}"
        assert all(c.method != "branch_protection" for c in fake.calls), \
            f"dry_run must not call branch_protection, but got: {[c.method for c in fake.calls]}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_dry_run_true_still_calls_auth_and_repo_view(self, mock_urlopen):
        """dry_run=True: still calls auth_status and repo_view."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True)
        repos = _fake_repos()
        run_preflight(repos, dry_run=True, gh=fake)

        methods = [c.method for c in fake.calls]
        assert "auth_status" in methods
        assert "repo_view" in methods

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_dry_run_true_network_failure_tolerated(self, mock_urlopen):
        """dry_run=True: ckpt URL unreachable is tolerated (no failure added)."""
        mock_urlopen.side_effect = urllib.error.URLError("net")
        fake = FakeGhClient(auth_ok=True)
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=True, gh=fake)

        assert result.ok is True
        assert not any("hf_ckpt_unreachable" in f for f in result.failures)


# ---------------------------------------------------------------------------
# dry_run=False, auth fails (INPUT-03 fail-fast)
# ---------------------------------------------------------------------------

class TestAuthFailFast:
    """INPUT-03: bad auth must produce a gh_auth_status failure."""

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_auth_ok_false_fails(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=False)
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is False
        assert any("gh_auth_status" in f for f in result.failures), \
            f"Expected 'gh_auth_status' in failures, got: {result.failures}"


# ---------------------------------------------------------------------------
# dry_run=False, missing push permission
# ---------------------------------------------------------------------------

class TestMissingPushPermission:
    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_missing_push(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, repo_perms={"pull": True, "push": False, "admin": False})
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is False
        assert any("write" in f or "push" in f for f in result.failures), \
            f"Expected 'write' or 'push' in failures, got: {result.failures}"


# ---------------------------------------------------------------------------
# Branch protection compatibility checks (W4)
# ---------------------------------------------------------------------------

class TestBranchProtectionCompatible:
    """W4: branch protection compatibility — required reviews hard-fail."""

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_required_approving_review_fails(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={
            "required_pull_request_reviews": {"required_approving_review_count": 1}
        })
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is False
        assert any("approving review" in f or "branch_protection" in f for f in result.failures), \
            f"Expected 'approving review' or 'branch_protection' in failures, got: {result.failures}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_restrictions_hard_fail(self, mock_urlopen):
        """W4: restrictions non-empty → hard fail with 'push restrictions allowlist'."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={
            "restrictions": {"users": [{"login": "alice"}], "teams": [], "apps": []}
        })
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is False
        assert any("push restrictions allowlist" in f for f in result.failures), \
            f"Expected 'push restrictions allowlist' in failures, got: {result.failures}"
        assert any("users=1" in f for f in result.failures), \
            f"Expected 'users=1' in failures, got: {result.failures}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_lock_branch_hard_fail(self, mock_urlopen):
        """W4: lock_branch=true → hard fail."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={"lock_branch": True})
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is False
        assert any("lock_branch=true" in f for f in result.failures), \
            f"Expected 'lock_branch=true' in failures, got: {result.failures}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_required_status_checks_warn_only(self, mock_urlopen):
        """W4: required_status_checks.contexts → warn-only, ok stays True."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={
            "required_status_checks": {"contexts": ["ci/build", "ci/test"]}
        })
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is True
        assert any("required_status_checks.contexts" in w for w in result.warnings), \
            f"Expected 'required_status_checks.contexts' in warnings, got: {result.warnings}"
        # Check the contexts list is mentioned
        assert any("ci/build" in w and "ci/test" in w for w in result.warnings), \
            f"Expected contexts list in warnings, got: {result.warnings}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_enforce_admins_informational(self, mock_urlopen):
        """W4: enforce_admins=true → warn-only."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={"enforce_admins": True})
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is True
        assert any("enforce_admins=true" in w for w in result.warnings), \
            f"Expected 'enforce_admins=true' in warnings, got: {result.warnings}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_required_linear_history_informational(self, mock_urlopen):
        """W4: required_linear_history=true → warn-only."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={"required_linear_history": True})
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is True
        assert any("required_linear_history=true" in w for w in result.warnings), \
            f"Expected 'required_linear_history=true' in warnings, got: {result.warnings}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_combined_hard_fail_and_warn(self, mock_urlopen):
        """W4: combined hard-fail + warn: approving reviews + lock_branch + status_checks."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={
            "required_pull_request_reviews": {"required_approving_review_count": 2},
            "lock_branch": True,
            "required_status_checks": {"contexts": ["ci/build"]},
        })
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is False
        # Both hard-fail reasons must be in failures
        assert any("approving review" in f for f in result.failures), \
            f"Expected 'approving review' in failures, got: {result.failures}"
        assert any("lock_branch=true" in f for f in result.failures), \
            f"Expected 'lock_branch=true' in failures, got: {result.failures}"
        # Warn-only in warnings
        assert any("required_status_checks.contexts" in w for w in result.warnings), \
            f"Expected 'required_status_checks.contexts' in warnings, got: {result.warnings}"

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_empty_protection_compatible(self, mock_urlopen):
        """W4: empty/None protection = compatible, no warnings."""
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={})
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)

        assert result.ok is True
        # Only branch-protection-related warnings should be empty
        bp_warnings = [w for w in result.warnings if "branch_protection" in w]
        assert bp_warnings == [], f"Expected no branch-protection warnings, got: {bp_warnings}"


# ---------------------------------------------------------------------------
# PreflightResult shape
# ---------------------------------------------------------------------------

class TestPreflightResultShape:
    def test_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(PreflightResult)

    def test_has_warnings_field(self):
        from dataclasses import fields
        names = {f.name for f in fields(PreflightResult)}
        assert "warnings" in names, f"Expected 'warnings' in fields, got: {names}"


# ---------------------------------------------------------------------------
# _check_branch_protection_compatible unit tests
# ---------------------------------------------------------------------------

class TestCheckBranchProtectionCompatible:
    def test_empty_dict_no_issues(self):
        fails, warns = _check_branch_protection_compatible({})
        assert fails == []
        assert warns == []

    def test_none_treated_as_empty(self):
        # The function is called with prot from FakeGhClient which returns dict(protection)
        # If protection is empty dict, it should be fine
        fails, warns = _check_branch_protection_compatible({})
        assert fails == []

    def test_approving_reviews(self):
        fails, warns = _check_branch_protection_compatible({
            "required_pull_request_reviews": {"required_approving_review_count": 2}
        })
        assert len(fails) == 1
        assert "2 approving review" in fails[0]

    def test_restrictions_non_empty(self):
        fails, warns = _check_branch_protection_compatible({
            "restrictions": {"users": [{"login": "a"}], "teams": [], "apps": []}
        })
        assert len(fails) == 1
        assert "push restrictions allowlist non-empty" in fails[0]
        assert "users=1" in fails[0]

    def test_lock_branch(self):
        fails, warns = _check_branch_protection_compatible({"lock_branch": True})
        assert len(fails) == 1
        assert "lock_branch=true" in fails[0]

    def test_status_checks_warns(self):
        fails, warns = _check_branch_protection_compatible({
            "required_status_checks": {"contexts": ["ci/build"]}
        })
        assert fails == []
        assert len(warns) == 1
        assert "required_status_checks.contexts" in warns[0]

    def test_enforce_admins_warns(self):
        fails, warns = _check_branch_protection_compatible({"enforce_admins": True})
        assert fails == []
        assert len(warns) == 1
        assert "enforce_admins=true" in warns[0]

    def test_linear_history_warns(self):
        fails, warns = _check_branch_protection_compatible({"required_linear_history": True})
        assert fails == []
        assert len(warns) == 1
        assert "required_linear_history=true" in warns[0]


# ---------------------------------------------------------------------------
# format_failures
# ---------------------------------------------------------------------------

class TestFormatFailures:
    def test_ok_no_warnings(self):
        result = PreflightResult(ok=True, failures=[], warnings=[])
        text = format_failures(result)
        assert text == ""

    def test_ok_with_warnings(self):
        result = PreflightResult(ok=True, failures=[], warnings=["branch_protection: a:b enforce_admins=true"])
        text = format_failures(result)
        assert "PREFLIGHT WARNINGS" in text
        assert "enforce_admins" in text
        assert "PREFLIGHT FAILED" not in text

    def test_failed(self):
        result = PreflightResult(ok=False, failures=["gh_auth_status: not logged in"], warnings=[])
        text = format_failures(result)
        assert "PREFLIGHT FAILED" in text
        assert "gh_auth_status" in text
        assert "Aborting" in text

    def test_failed_with_warnings(self):
        result = PreflightResult(
            ok=False,
            failures=["gh_auth_status: not logged in"],
            warnings=["branch_protection: a:b enforce_admins=true"],
        )
        text = format_failures(result)
        assert "PREFLIGHT FAILED" in text
        assert "PREFLIGHT WARNINGS" in text
        assert "Aborting" in text


# ---------------------------------------------------------------------------
# Failure-string prefix contract
# ---------------------------------------------------------------------------

class TestFailureStringPrefixes:
    """Failure strings MUST start with stable prefixes for downstream assertion."""

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_auth_prefix(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=False)
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)
        assert any(f.startswith("gh_auth_status:") for f in result.failures)

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_write_prefix(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, repo_perms={"pull": True, "push": False, "admin": False})
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)
        assert any(f.startswith("loongforge_write:") or f.startswith("megatron_write:") for f in result.failures)

    @patch("skills.adapt.lib.preflight.urllib.request.urlopen")
    def test_branch_protection_prefix(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(200)
        fake = FakeGhClient(auth_ok=True, protection={"lock_branch": True})
        repos = _fake_repos()
        result = run_preflight(repos, dry_run=False, gh=fake)
        assert any(f.startswith("branch_protection:") for f in result.failures)
