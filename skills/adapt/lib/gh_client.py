"""GhClient Protocol + RealGhClient + FakeGhClient with full PR/issue lifecycle.

Phase 1: read-only preflight methods (auth_status, repo_view, repo_permissions,
branch_protection).
Phase 2: PR/issue lifecycle methods with policy guards, idempotency, dedup,
and simulated state machine.

Policy exceptions:
  ProtectedPathError -- PR diff touches validator-protected paths (PR-06, D-03)
  HumanCommitError   -- branch contains non-bot commits (PR-05, D-01)
  DirectPushError    -- create_branch targets default branch (PR-01)

FakeGhClient provides an in-memory state machine with FakePrRecord and
FakeIssueRecord stores for testability without subprocess mocking.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from skills.adapt.lib.redact import redact
from skills.adapt.lib.protected_paths import is_protected
from skills.adapt.lib.idempotency import compute_idempotency_key, format_footer, parse_footer, compute_dedup_key
from skills.adapt.lib.templates import (
    pr_title, pr_body, issue_title, issue_body,
    REQUIRED_LABELS, dedup_comment, agent_resume_comment,
)


@dataclass(frozen=True)
class GhResult:
    """Minimal result shape from a gh-CLI call."""
    returncode: int
    stdout: str
    stderr: str


# ---------------------------------------------------------------------------
# Policy exceptions
# ---------------------------------------------------------------------------

class ProtectedPathError(Exception):
    """Raised when a PR diff touches validator-protected paths (PR-06, D-03)."""
    def __init__(self, paths: list[str]):
        self.paths = paths
        super().__init__(f"Protected paths in diff: {paths}")


class HumanCommitError(Exception):
    """Raised when a branch contains non-bot commits (PR-05, D-01).

    The bot_login attribute identifies the authenticated gh user whose commits
    are expected on bot branches.
    """
    def __init__(self, branch: str, bot_login: str):
        self.branch = branch
        self.bot_login = bot_login
        super().__init__(f"Non-bot commits on {branch}; bot identity is {bot_login}")


class DirectPushError(Exception):
    """Raised when create_branch is called targeting the default branch (PR-01)."""
    def __init__(self, branch: str):
        self.branch = branch
        super().__init__(f"Direct push to default branch {branch} is forbidden")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _timestamp_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Fake record types
# ---------------------------------------------------------------------------

@dataclass
class FakePrRecord:
    """Simulated PR record for FakeGhClient state machine."""
    number: int
    owner_repo: str
    head: str
    base: str
    title: str
    body: str
    labels: list[str]
    state: str  # "open" | "closed" | "merged"
    merged_sha: Optional[str] = None
    idempotency_key: Optional[str] = None
    comments: list[str] = field(default_factory=list)


@dataclass
class FakeIssueRecord:
    """Simulated issue record for FakeGhClient state machine."""
    number: int
    owner_repo: str
    title: str
    body: str
    labels: list[str]
    state: str  # "open" | "closed"
    failure_signature: Optional[dict] = None
    idempotency_key: Optional[str] = None
    dedup_key: Optional[str] = None  # For cross-attempt dedup (D-02, ISSUE-03)
    comments: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GhClient Protocol
# ---------------------------------------------------------------------------

_BRANCH_RE = re.compile(r"^adapt/[a-zA-Z0-9_-]+/phase[0-9]+/attempt[0-9]+$")


class GhClient(Protocol):
    """Adapter shielding the rest of the skill from `gh` CLI syntax.
    Phase 1: only auth/perm/branch-protection methods are implemented.
    Phase 2: PR/issue lifecycle methods filled in."""

    # --- Read-only / preflight (Phase 1 fully implements) ---
    def auth_status(self) -> GhResult: ...
    def repo_view(self, owner_repo: str) -> GhResult: ...
    def repo_permissions(self, owner_repo: str) -> dict: ...
    def branch_protection(self, owner_repo: str, branch: str) -> dict: ...

    # --- PR / issue lifecycle (Phase 2 implements) ---
    def create_branch(self, owner_repo: str, branch: str, base: str) -> GhResult: ...
    def open_pr(self, owner_repo: str, head: str, base: str,
                run_id: str = "", phase: int = 0, attempt: int = 0,
                validator: str = "", kind: str = "base",
                fixes_issue: Optional[int] = None,
                diff_summary: str = "", draft: bool = True) -> GhResult: ...
    def merge_pr(self, owner_repo: str, number: int, method: str = "squash") -> GhResult: ...
    def open_issue(self, owner_repo: str,
                   run_id: str = "", phase: int = 0, attempt: int = 0,
                   validator_name: str = "", failure_signature: dict = None,
                   log_excerpt: str = "", attempts_jsonl_link: str = "",
                   reproduction_cmd: str = "") -> GhResult: ...
    def close_issue(self, owner_repo: str, number: int, comment: Optional[str] = None,
                    run_id: str = "", phase: int = 0, outcome: str = "completed") -> GhResult: ...
    def find_by_idempotency_key(self, owner_repo: str, kind: str, key: str) -> Optional[int]: ...
    def find_by_dedup_key(self, owner_repo: str, dedup_key: str) -> Optional[int]: ...


class RealGhClient:
    """Phase 1: preflight subset. Phase 2: PR/issue lifecycle methods."""

    def _run(self, args: list[str]) -> GhResult:
        cp = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
        return GhResult(cp.returncode, cp.stdout, cp.stderr)

    # --- Preflight (Phase 1) ---
    def auth_status(self) -> GhResult:
        return self._run(["auth", "status", "--hostname", "github.com"])

    def repo_view(self, owner_repo: str) -> GhResult:
        return self._run(["api", f"repos/{owner_repo}"])

    def repo_permissions(self, owner_repo: str) -> dict:
        r = self._run(["api", f"repos/{owner_repo}", "--jq", ".permissions"])
        if r.returncode != 0:
            return {}
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {}

    def branch_protection(self, owner_repo: str, branch: str) -> dict:
        r = self._run(["api", f"repos/{owner_repo}/branches/{branch}/protection"])
        if r.returncode != 0:
            return {}  # 404 == unprotected, which is fine
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {}

    # --- PR lifecycle (Phase 2) ---

    def create_branch(self, owner_repo: str, branch: str, base: str) -> GhResult:
        """Create a branch via gh api. Validates name format and refuses default-branch base."""
        if not _BRANCH_RE.match(branch):
            raise ValueError(f"Invalid branch name: {branch}; expected adapt/<run_id>/phase<N>/attempt<K>")
        # Detect default branch to refuse direct push (PR-01)
        default_r = self._run(["api", f"repos/{owner_repo}", "--jq", ".default_branch"])
        if default_r.returncode == 0 and default_r.stdout.strip() == base:
            raise DirectPushError(base)
        # Get base SHA
        base_sha_r = self._run(["api", f"repos/{owner_repo}/git/ref/heads/{base}", "--jq", ".object.sha"])
        if base_sha_r.returncode != 0:
            return base_sha_r
        base_sha = base_sha_r.stdout.strip()
        r = self._run(["api", f"repos/{owner_repo}/git/refs",
                       "-f", f"ref=refs/heads/{branch}",
                       "-f", f"sha={base_sha}"])
        return r

    def open_pr(self, owner_repo: str, head: str, base: str,
                run_id: str = "", phase: int = 0, attempt: int = 0,
                validator: str = "", kind: str = "base",
                fixes_issue: Optional[int] = None,
                diff_summary: str = "", draft: bool = True) -> GhResult:
        """Open a PR with templated title/body, policy guards, redaction, and labels."""
        # Policy pre-check 1: Protected path scan (PR-06, D-03)
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base}...{head}"],
            capture_output=True, text=True, check=False
        )
        if diff_result.returncode == 0 and diff_result.stdout.strip():
            changed = [f.strip() for f in diff_result.stdout.strip().split("\n") if f.strip()]
            protected = [f for f in changed if is_protected(f)]
            if protected:
                raise ProtectedPathError(protected)

        # Policy pre-check 2: Human commit detection (PR-05, D-01)
        bot_email_r = self._run(["api", "user", "--jq", ".email"])
        bot_email = bot_email_r.stdout.strip() if bot_email_r.returncode == 0 else ""
        log_result = subprocess.run(
            ["git", "log", f"origin/{base}..{head}", "--format=%ae"],
            capture_output=True, text=True, check=False
        )
        if log_result.returncode == 0 and log_result.stdout.strip():
            emails = set(e.strip() for e in log_result.stdout.strip().split("\n") if e.strip())
            non_bot_emails = emails - {bot_email}
            if non_bot_emails:
                # Try to find existing open PR on this branch and post /agent-resume comment (D-01)
                search_r = self._run([
                    "pr", "list", "-R", owner_repo,
                    "--head", head,
                    "--state", "open",
                    "--json", "number",
                    "--limit", "1",
                ])
                if search_r.returncode == 0:
                    try:
                        items = json.loads(search_r.stdout)
                        if items:
                            existing_pr_number = int(items[0]["number"])
                            comment = agent_resume_comment(run_id, phase)
                            rr = redact(comment)
                            self._run([
                                "pr", "comment", str(existing_pr_number),
                                "-R", owner_repo,
                                "--body", rr.cleaned,
                            ])
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass  # Best-effort comment posting; HumanCommitError is the primary signal
                raise HumanCommitError(head, bot_email)

        # Build title/body from templates
        title = pr_title(run_id, phase, attempt, validator, kind)
        body = pr_body(run_id, phase, attempt, kind, validator, diff_summary, fixes_issue)
        # Redact body (SAFE-01)
        rr = redact(body)
        if not rr.accept:
            pass  # Log warning but proceed with cleaned text
        body = rr.cleaned

        # Bootstrap labels (ISSUE-04 pitfall 4)
        run_label = f"run-{run_id}"
        phase_label = f"phase-{phase}"
        all_labels = REQUIRED_LABELS + [run_label, phase_label]
        for label in all_labels:
            color = "0e8a16" if label == "loongforge-adapt" else "bfd4f2"
            self._run(["label", "create", label, "--color", color, "-R", owner_repo])

        # Create PR via gh
        r = self._run([
            "pr", "create",
            "-R", owner_repo,
            "--base", base,
            "--head", head,
            "--title", title,
            "--body", body,
            "--label", ",".join(all_labels),
        ] + (["--draft"] if draft else []))
        return r

    def merge_pr(self, owner_repo: str, number: int, method: str = "squash") -> GhResult:
        """Merge a PR. Per PR-02, uses gh pr merge --squash --delete-branch."""
        method_flag = f"--{method}"
        r = self._run([
            "pr", "merge", str(number),
            "-R", owner_repo,
            method_flag,
            "--delete-branch",
        ])
        return r

    # --- Issue lifecycle (Phase 2) ---

    def open_issue(self, owner_repo: str,
                   run_id: str = "", phase: int = 0, attempt: int = 0,
                   validator_name: str = "", failure_signature: dict = None,
                   log_excerpt: str = "", attempts_jsonl_link: str = "",
                   reproduction_cmd: str = "") -> GhResult:
        """Open an issue with structured failure signature, dedup, and labels."""
        # Dedup check (ISSUE-03, D-02) -- using find_by_dedup_key, NOT find_by_idempotency_key
        if failure_signature:
            dedup_key = compute_dedup_key(phase, validator_name, failure_signature)
            existing = self.find_by_dedup_key(owner_repo, dedup_key)
            if existing is not None:
                comment = dedup_comment(attempt, log_excerpt, _timestamp_now())
                rr = redact(comment)
                return self._run([
                    "issue", "comment", str(existing),
                    "-R", owner_repo,
                    "--body", rr.cleaned,
                ])

        # Build title/body from templates
        kind = failure_signature.get("kind", "unknown") if failure_signature else "unknown"
        title = issue_title(phase, validator_name, kind)
        body = issue_body(phase, validator_name, failure_signature or {}, log_excerpt,
                          attempts_jsonl_link, reproduction_cmd, run_id, attempt)
        # Redact body
        rr = redact(body)
        if not rr.accept:
            pass  # Log warning, proceed with cleaned text
        body = rr.cleaned

        # Bootstrap labels
        all_labels = REQUIRED_LABELS + [f"run-{run_id}", f"phase-{phase}"]
        for label in all_labels:
            color = "0e8a16" if label == "loongforge-adapt" else "bfd4f2"
            self._run(["label", "create", label, "--color", color, "-R", owner_repo])

        # Create issue
        r = self._run([
            "issue", "create",
            "-R", owner_repo,
            "--title", title,
            "--body", body,
            "--label", ",".join(all_labels),
        ])
        return r

    def close_issue(self, owner_repo: str, number: int, comment: Optional[str] = None,
                    run_id: str = "", phase: int = 0, outcome: str = "completed") -> GhResult:
        """Close an issue with optional closing summary comment."""
        if comment is None:
            from skills.adapt.lib.templates import closing_summary
            comment = closing_summary(run_id, phase, outcome)
        rr = redact(comment)
        r = self._run([
            "issue", "close", str(number),
            "-R", owner_repo,
            "--comment", rr.cleaned,
            "--reason", "completed",
        ])
        return r

    # --- Find methods (Phase 2) ---

    def find_by_idempotency_key(self, owner_repo: str, kind: str, key: str) -> Optional[int]:
        """Search for PRs or issues containing the idempotency key (RESUME-03)."""
        if kind == "pr":
            r = self._run([
                "pr", "list", "-R", owner_repo,
                "--state", "all",
                "--search", f"adapt-skill-key: {key}",
                "--json", "number",
                "--limit", "5",
            ])
        else:  # kind == "issue"
            r = self._run([
                "issue", "list", "-R", owner_repo,
                "--state", "all",
                "--search", f"adapt-skill-key: {key}",
                "--json", "number",
                "--limit", "5",
            ])
        if r.returncode != 0:
            return None
        try:
            items = json.loads(r.stdout)
            if items:
                return int(items[0]["number"])
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
        return None

    def find_by_dedup_key(self, owner_repo: str, dedup_key: str) -> Optional[int]:
        """Search for open issues containing the dedup key (D-02, ISSUE-03).

        Separate from find_by_idempotency_key because dedup key and idempotency
        key serve different purposes (cross-attempt dedup vs crash-resume) and
        have different hash inputs.
        """
        r = self._run([
            "issue", "list", "-R", owner_repo,
            "--state", "open",
            "--search", f"dedup-key: {dedup_key}",
            "--json", "number",
            "--limit", "5",
        ])
        if r.returncode != 0:
            return None
        try:
            items = json.loads(r.stdout)
            if items:
                return int(items[0]["number"])
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
        return None


# ---------------------------------------------------------------------------
# FakeGhClient -- in-memory state machine for tests
# ---------------------------------------------------------------------------

@dataclass
class FakeGhCall:
    """Record of a single call to FakeGhClient."""
    method: str
    args: tuple
    kwargs: dict


@dataclass
class FakeGhClient:
    """In-memory GhClient for tests / dry-run.
    Records every call. Returns ok-shaped responses unless preset to fail.

    PR/issue lifecycle methods maintain simulated state:
      _pr_store / _issue_store: dict of (owner_repo, number) -> record
      find_by_idempotency_key / find_by_dedup_key: search the stores
    """
    calls: list[FakeGhCall] = field(default_factory=list)
    auth_ok: bool = True
    repo_perms: dict = field(default_factory=lambda: {"pull": True, "push": True, "admin": False})
    protection: dict = field(default_factory=dict)  # empty == unprotected

    # PR-side state
    _pr_store: dict[tuple[str, int], FakePrRecord] = field(default_factory=dict)
    _next_pr_number: int = 1
    _bot_login: str = "adapt-bot"
    _bot_email: str = "adapt-bot@users.noreply.github.com"
    _default_branches: dict = field(default_factory=lambda: {
        "Zachary-wW/LoongForge": "main",
        "Zachary-wW/Loong-Megatron": "loong-main/core_v0.15.0",
    })
    _protected_paths_in_diff: list[str] = field(default_factory=list)
    _human_commit_branches: set[str] = field(default_factory=set)

    # Issue-side state
    _issue_store: dict[tuple[str, int], FakeIssueRecord] = field(default_factory=dict)
    _next_issue_number: int = 1
    _sha_store: dict[str, str] = field(default_factory=lambda: {
        "Zachary-wW/Loong-Megatron:loong-main/core_v0.15.0": "fake-megatron-sha-abc123",
    })

    def _record(self, method: str, *args, **kwargs):
        self.calls.append(FakeGhCall(method, args, kwargs))

    def _run(self, args: list[str]) -> GhResult:
        """Simulate gh CLI _run for methods that bypass the protocol (e.g., get_megatron_head_sha)."""
        self._record("_run", tuple(args))
        # Handle gh api repos/OWNER/REPO/git/ref/heads/REF --jq .object.sha
        if len(args) >= 3 and args[0] == "api":
            key = f"{args[1].split('repos/')[-1].split('/git/')[0]}:{args[1].split('/heads/')[-1]}"
            sha = self._sha_store.get(key)
            if sha:
                return GhResult(0, sha, "")
        return GhResult(1, "", "not found")

    # --- Preflight (Phase 1) ---
    def auth_status(self) -> GhResult:
        self._record("auth_status")
        return GhResult(0 if self.auth_ok else 1, "", "")

    def repo_view(self, owner_repo: str) -> GhResult:
        self._record("repo_view", owner_repo)
        return GhResult(0, '{"name":"' + owner_repo + '"}', "")

    def repo_permissions(self, owner_repo: str) -> dict:
        self._record("repo_permissions", owner_repo)
        return dict(self.repo_perms)

    def branch_protection(self, owner_repo: str, branch: str) -> dict:
        self._record("branch_protection", owner_repo, branch)
        return dict(self.protection)

    # --- PR lifecycle (Phase 2) ---

    def create_branch(self, owner_repo: str, branch: str, base: str) -> GhResult:
        """Create a simulated branch. Validates name format and refuses default-branch base."""
        self._record("create_branch", owner_repo, branch, base)
        if not _BRANCH_RE.match(branch):
            raise ValueError(f"Invalid branch name: {branch}; expected adapt/<run_id>/phase<N>/attempt<K>")
        default_branch = self._default_branches.get(owner_repo, "main")
        if base == default_branch:
            raise DirectPushError(base)
        return GhResult(0, "", "")

    def open_pr(self, owner_repo: str, head: str, base: str,
                run_id: str = "", phase: int = 0, attempt: int = 0,
                validator: str = "", kind: str = "base",
                fixes_issue: Optional[int] = None,
                diff_summary: str = "", draft: bool = True) -> GhResult:
        """Open a simulated PR with policy guards."""
        self._record("open_pr", owner_repo, head, base,
                     run_id=run_id, phase=phase, attempt=attempt,
                     validator=validator, kind=kind, fixes_issue=fixes_issue,
                     diff_summary=diff_summary, draft=draft)

        # Policy pre-check 1: Protected path scan
        if self._protected_paths_in_diff:
            protected = [f for f in self._protected_paths_in_diff if is_protected(f)]
            if protected:
                raise ProtectedPathError(protected)

        # Policy pre-check 2: Human commit detection
        if head in self._human_commit_branches:
            # Search for existing open PR on this branch
            for key, pr in self._pr_store.items():
                if pr.head == head and pr.state == "open":
                    comment = agent_resume_comment(run_id, phase)
                    pr.comments.append(comment)
                    break
            raise HumanCommitError(head, self._bot_email)

        # Build title/body from templates
        title = pr_title(run_id, phase, attempt, validator, kind)
        body = pr_body(run_id, phase, attempt, kind, validator, diff_summary, fixes_issue)

        # Parse idempotency key from footer
        footer = parse_footer(body)
        idem_key = footer.key if footer else None

        # Store the PR record
        number = self._next_pr_number
        self._next_pr_number += 1
        run_label = f"run-{run_id}"
        phase_label = f"phase-{phase}"
        all_labels = REQUIRED_LABELS + [run_label, phase_label]

        record = FakePrRecord(
            number=number,
            owner_repo=owner_repo,
            head=head,
            base=base,
            title=title,
            body=body,
            labels=all_labels,
            state="open",
            idempotency_key=idem_key,
        )
        self._pr_store[(owner_repo, number)] = record
        return GhResult(0, f"https://github.com/{owner_repo}/pull/{number}", "")

    def merge_pr(self, owner_repo: str, number: int, method: str = "squash") -> GhResult:
        """Merge a simulated PR. Transitions state to 'merged' and sets merged_sha."""
        self._record("merge_pr", owner_repo, number, method)
        key = (owner_repo, number)
        if key not in self._pr_store:
            return GhResult(1, "", f"PR #{number} not found in {owner_repo}")
        pr = self._pr_store[key]
        pr.state = "merged"
        pr.merged_sha = f"fake-sha-{number}"
        return GhResult(0, f"merged as fake-sha-{number}", "")

    # --- Issue lifecycle (Phase 2) ---

    def open_issue(self, owner_repo: str,
                   run_id: str = "", phase: int = 0, attempt: int = 0,
                   validator_name: str = "", failure_signature: dict = None,
                   log_excerpt: str = "", attempts_jsonl_link: str = "",
                   reproduction_cmd: str = "") -> GhResult:
        """Open a simulated issue with dedup logic."""
        self._record("open_issue", owner_repo,
                     run_id=run_id, phase=phase, attempt=attempt,
                     validator_name=validator_name,
                     failure_signature=failure_signature,
                     log_excerpt=log_excerpt,
                     attempts_jsonl_link=attempts_jsonl_link,
                     reproduction_cmd=reproduction_cmd)

        # Dedup check: if failure_signature provided, compute dedup key and search
        dedup_key = None
        if failure_signature:
            dedup_key = compute_dedup_key(phase, validator_name, failure_signature)
            existing = self.find_by_dedup_key(owner_repo, dedup_key)
            if existing is not None:
                # Append comment to existing issue (D-02, ISSUE-03)
                comment = dedup_comment(attempt, log_excerpt, _timestamp_now())
                existing_issue = self._issue_store.get((owner_repo, existing))
                if existing_issue:
                    existing_issue.comments.append(comment)
                return GhResult(0, f"comment on #{existing}", "")

        # Build title/body from templates
        kind = failure_signature.get("kind", "unknown") if failure_signature else "unknown"
        title = issue_title(phase, validator_name, kind)
        body = issue_body(phase, validator_name, failure_signature or {}, log_excerpt,
                          attempts_jsonl_link, reproduction_cmd, run_id, attempt)

        # Parse idempotency key from footer
        footer = parse_footer(body)
        idem_key = footer.key if footer else None

        # Store the issue record
        number = self._next_issue_number
        self._next_issue_number += 1
        run_label = f"run-{run_id}"
        phase_label = f"phase-{phase}"
        all_labels = REQUIRED_LABELS + [run_label, phase_label]

        record = FakeIssueRecord(
            number=number,
            owner_repo=owner_repo,
            title=title,
            body=body,
            labels=all_labels,
            state="open",
            failure_signature=failure_signature,
            idempotency_key=idem_key,
            dedup_key=dedup_key,
        )
        self._issue_store[(owner_repo, number)] = record
        return GhResult(0, f"https://github.com/{owner_repo}/issues/{number}", "")

    def close_issue(self, owner_repo: str, number: int, comment: Optional[str] = None,
                    run_id: str = "", phase: int = 0, outcome: str = "completed") -> GhResult:
        """Close a simulated issue. Transitions state to 'closed'."""
        self._record("close_issue", owner_repo, number,
                     comment=comment, run_id=run_id, phase=phase, outcome=outcome)
        key = (owner_repo, number)
        if key not in self._issue_store:
            return GhResult(1, "", f"Issue #{number} not found")
        issue = self._issue_store[key]
        issue.state = "closed"
        if comment is None:
            from skills.adapt.lib.templates import closing_summary
            comment = closing_summary(run_id, phase, outcome)
        issue.comments.append(comment)
        return GhResult(0, "", "")

    # --- Find methods (Phase 2) ---

    def find_by_idempotency_key(self, owner_repo: str, kind: str, key: str) -> Optional[int]:
        """Search _pr_store or _issue_store for a record with matching idempotency_key."""
        self._record("find_by_idempotency_key", owner_repo, kind, key)
        if kind == "pr":
            for store_key, record in self._pr_store.items():
                if record.idempotency_key == key:
                    return record.number
        else:  # kind == "issue"
            for store_key, record in self._issue_store.items():
                if record.idempotency_key == key:
                    return record.number
        return None

    def find_by_dedup_key(self, owner_repo: str, dedup_key: str) -> Optional[int]:
        """Search _issue_store for an open issue with matching dedup_key."""
        self._record("find_by_dedup_key", owner_repo, dedup_key)
        for store_key, record in self._issue_store.items():
            if record.dedup_key == dedup_key and record.state == "open" and record.owner_repo == owner_repo:
                return record.number
        return None
