"""GhClient Protocol + RealGhClient (preflight subset) + FakeGhClient (in-memory recorder).

Phase 1 only implements read-only preflight methods (auth_status, repo_view,
repo_permissions, branch_protection). The six PR/issue lifecycle methods are
declared on the Protocol but raise NotImplementedError in RealGhClient until
Phase 2 implements them.

FakeGhClient records every call and returns ok-shaped responses by default;
its auth_ok / repo_perms / protection fields are parameterizable for
failure-mode tests.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class GhResult:
    """Minimal result shape from a gh-CLI call."""
    returncode: int
    stdout: str
    stderr: str


class GhClient(Protocol):
    """Adapter shielding the rest of the skill from `gh` CLI syntax.
    Phase 1: only auth/perm/branch-protection methods are implemented.
    Phase 2: PR/issue lifecycle methods filled in."""

    # --- Read-only / preflight (Phase 1 fully implements) ---
    def auth_status(self) -> GhResult: ...
    def repo_view(self, owner_repo: str) -> GhResult: ...
    def repo_permissions(self, owner_repo: str) -> dict: ...
    def branch_protection(self, owner_repo: str, branch: str) -> dict: ...

    # --- PR / issue lifecycle (Phase 1 declares; Phase 2 implements) ---
    def create_branch(self, owner_repo: str, branch: str, base: str) -> GhResult: ...
    def open_pr(self, owner_repo: str, head: str, base: str, title: str, body: str,
                labels: list[str], draft: bool = True) -> GhResult: ...
    def merge_pr(self, owner_repo: str, number: int, method: str = "squash") -> GhResult: ...
    def open_issue(self, owner_repo: str, title: str, body: str, labels: list[str]) -> GhResult: ...
    def close_issue(self, owner_repo: str, number: int, comment: Optional[str] = None) -> GhResult: ...
    def find_by_idempotency_key(self, owner_repo: str, kind: str, key: str) -> Optional[int]: ...


class RealGhClient:
    """Phase 1 only implements the preflight subset. PR/issue methods raise."""

    def _run(self, args: list[str]) -> GhResult:
        cp = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
        return GhResult(cp.returncode, cp.stdout, cp.stderr)

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

    # --- PR / issue lifecycle stubs (Phase 2 implements) ---
    def create_branch(self, *a, **k):    raise NotImplementedError("Phase 2")
    def open_pr(self, *a, **k):          raise NotImplementedError("Phase 2")
    def merge_pr(self, *a, **k):         raise NotImplementedError("Phase 2")
    def open_issue(self, *a, **k):       raise NotImplementedError("Phase 2")
    def close_issue(self, *a, **k):      raise NotImplementedError("Phase 2")
    def find_by_idempotency_key(self, *a, **k): raise NotImplementedError("Phase 2")


@dataclass
class FakeGhCall:
    """Record of a single call to FakeGhClient."""
    method: str
    args: tuple
    kwargs: dict


@dataclass
class FakeGhClient:
    """In-memory GhClient for tests / dry-run.
    Records every call. Returns ok-shaped responses unless preset to fail."""
    calls: list[FakeGhCall] = field(default_factory=list)
    auth_ok: bool = True
    repo_perms: dict = field(default_factory=lambda: {"pull": True, "push": True, "admin": False})
    protection: dict = field(default_factory=dict)  # empty == unprotected

    def _record(self, method: str, *args, **kwargs):
        self.calls.append(FakeGhCall(method, args, kwargs))

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

    # PR / issue lifecycle: record only, return placeholder shapes
    def create_branch(self, *a, **k):
        self._record("create_branch", *a, **k); return GhResult(0, "", "")
    def open_pr(self, *a, **k):
        self._record("open_pr", *a, **k); return GhResult(0, "https://example/pr/1", "")
    def merge_pr(self, *a, **k):
        self._record("merge_pr", *a, **k); return GhResult(0, "merged", "")
    def open_issue(self, *a, **k):
        self._record("open_issue", *a, **k); return GhResult(0, "https://example/issue/1", "")
    def close_issue(self, *a, **k):
        self._record("close_issue", *a, **k); return GhResult(0, "", "")
    def find_by_idempotency_key(self, *a, **k):
        self._record("find_by_idempotency_key", *a, **k); return None
