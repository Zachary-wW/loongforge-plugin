---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - skills/adapt/lib/gh_client.py
  - skills/adapt/lib/preflight.py
  - skills/adapt/tests/lib/test_preflight_dry_run.py
autonomous: true
requirements:
  - INPUT-03
  - INPUT-04
must_haves:
  truths:
    - "GhClient is a typing.Protocol with auth_status / repo_view / repo_permissions / branch_protection plus stubbed PR/issue methods that raise NotImplementedError in RealGhClient."
    - "FakeGhClient records every call (method+args+kwargs) and returns ok-shaped responses by default; auth_ok / repo_perms / protection are parameterizable for failure-mode tests."
    - "run_preflight(repos, dry_run=True, gh=FakeGhClient()) skips repo_permissions calls (live-write probe); ok=True when auth_ok=True; failures list contains 'gh_auth_status' when auth_ok=False."
    - "run_preflight returns PreflightResult dataclass with fields ok: bool, failures: list[str], branch_protection: dict."
  artifacts:
    - path: "skills/adapt/lib/gh_client.py"
      provides: "GhClient Protocol, GhResult dataclass, RealGhClient (preflight subset), FakeGhClient (in-memory recorder)"
      contains: "class GhClient(Protocol)"
    - path: "skills/adapt/lib/preflight.py"
      provides: "run_preflight() + PreflightResult dataclass; concrete gh probes (auth, repo perms, branch protection, ckpt URL)"
      contains: "def run_preflight"
    - path: "skills/adapt/tests/lib/test_preflight_dry_run.py"
      provides: "INPUT-03 fail-fast on bad auth + INPUT-04 dry-run skip-writes invariants"
  key_links:
    - from: "skills/adapt/lib/preflight.py"
      to: "skills/adapt/lib/gh_client.py"
      via: "preflight calls gh.auth_status / gh.repo_view / gh.repo_permissions / gh.branch_protection"
      pattern: "gh\\.(auth_status|repo_view|repo_permissions|branch_protection)"
    - from: "skills/adapt/tests/lib/test_preflight_dry_run.py"
      to: "skills/adapt/lib/preflight.py + skills/adapt/lib/gh_client.py"
      via: "run_preflight(..., gh=FakeGhClient(...))"
      pattern: "FakeGhClient"
---

<objective>
Define the `GhClient` Protocol surface (Phase 1 implements only the preflight read-only subset; PR/issue lifecycle methods are declared but raise `NotImplementedError` until Phase 2). Ship `FakeGhClient` (in-memory recorder, parameterizable failure modes) so all downstream plans + Phase 5 ACC-01 dry-run gate can exercise the FSM offline. Implement `run_preflight()` with concrete gh-CLI probes for auth / repo perms / branch protection / ckpt URL, with a `dry_run=True` path that skips live-write probes.

Purpose: This is the substrate for INPUT-04 (dry-run). The next-wave CLI plan (03) calls `run_preflight()` from `init_run_dir` (skipped on `--resume`); the Phase-5 ACC-01 local-acceptance gate uses `FakeGhClient` end-to-end with no live gh calls.

Output: 2 new lib modules + 1 test file covering INPUT-03 + INPUT-04 invariants.

Parallelism with Plan 01: This plan does NOT modify `skills/adapt/lib/__init__.py` (plan 01 owns it). Annotations use `from __future__ import annotations` so type references to `ReposBlock` resolve lazily — no import-time dependency on `lib/schema.py`. Both plans run concurrently in Wave 1.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md
@.planning/research/PITFALLS.md

<interfaces>
<!-- The ReposBlock type that preflight accepts (defined in plan 01's schema.py).
     Preflight uses it only as a type hint; with `from __future__ import annotations`
     this is a forward-string and does NOT trigger an import at module load. -->
```python
class ReposBlock(BaseModel):
    hf_impl:    HFImplSpec     # .url (HttpUrl), .ref, .subpath
    hf_ckpt:    HFCkptSpec     # .url (HttpUrl), .revision
    loongforge: RepoSpec       # .url, .base_ref, .work_branch, .subpath
    megatron:   RepoSpec       # .url, .base_ref, .work_branch, .subpath
```

<!-- Preflight contract (RESEARCH §4) -->
```python
@dataclass
class PreflightResult:
    ok: bool
    failures: list[str]            # e.g. ["gh_auth_status: not logged in (run `gh auth login`)"]
    warnings: list[str]            # W4: branch-protection warn-only items
    branch_protection: dict        # raw gh api output for record

def run_preflight(repos: "ReposBlock", *, dry_run: bool, gh: "GhClient") -> PreflightResult: ...
```

<!-- gh-CLI probes (RESEARCH §4 table) -->
| Check                | Command                                                                | Pass condition                          |
|----------------------|------------------------------------------------------------------------|------------------------------------------|
| Auth                 | gh auth status --hostname github.com                                   | exit 0                                   |
| Read perm            | gh api repos/<owner>/<repo>                                            | exit 0                                   |
| Write perm (skipped in --dry-run) | gh api repos/<owner>/<repo> --jq .permissions.push        | output "true"                            |
| Branch protection    | gh api repos/<owner>/<repo>/branches/<base_ref>/protection             | exit 0 OR exit 1 with "Branch not protected" |
| Ckpt URL reachable   | urllib HEAD on https://huggingface.co/api/models/<org>/<model>         | HTTP 200                                 |
| HF impl URL reachable| gh api repos/<owner>/<repo> --jq .default_branch                       | exit 0                                   |
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 2.1: GhClient Protocol + RealGhClient (preflight subset) + FakeGhClient recorder</name>
  <read_first>
    - .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md (§10 GhClient interface, full code block lines 481-599)
    - skills/adapt/scripts/run.py (subprocess invocation pattern reference — match the existing `subprocess.run(..., capture_output=True, text=True, check=False)` style for RealGhClient._run; W1)
    - .planning/research/PITFALLS.md (Pitfall 7 — GH rate limits / auth scope / branch protection: shapes the auth-fail handling and the "GhResult(returncode != 0, stderr non-empty)" interpretation in RealGhClient; W1)
  </read_first>
  <behavior>
    - Test (Protocol shape): `GhClient` declares all of: `auth_status`, `repo_view`, `repo_permissions`, `branch_protection`, `create_branch`, `open_pr`, `merge_pr`, `open_issue`, `close_issue`, `find_by_idempotency_key`. (Verify via `hasattr(GhClient, ...)` on the Protocol or `inspect.getmembers`.)
    - Test (RealGhClient stub-mode): `RealGhClient().create_branch(...)` raises `NotImplementedError` with message containing "Phase 2"; same for `open_pr`, `merge_pr`, `open_issue`, `close_issue`, `find_by_idempotency_key`.
    - Test (FakeGhClient default OK): `f = FakeGhClient(); r = f.auth_status()` returns `GhResult(returncode=0, ...)`; `f.calls[0].method == "auth_status"`.
    - Test (FakeGhClient configurable failure): `f = FakeGhClient(auth_ok=False); f.auth_status().returncode == 1`.
    - Test (FakeGhClient PR stubs record but don't raise): `f.open_pr("owner/repo", "head", "base", "title", "body", ["lab"]).returncode == 0`; `f.calls` contains a FakeGhCall with method="open_pr".
    - Test (FakeGhClient repo_permissions returns dict): `f = FakeGhClient(); d = f.repo_permissions("owner/repo"); assert d == {"pull": True, "push": True, "admin": False}`.
  </behavior>
  <action>
**File: `skills/adapt/lib/gh_client.py`** — copy the code block from RESEARCH §10 lines 481-599 verbatim. Top of file: `from __future__ import annotations` + `import subprocess` + `from dataclasses import dataclass, field` + `from typing import Protocol, Optional`.

Required exact contents:

1. `@dataclass(frozen=True) class GhResult` with fields `returncode: int`, `stdout: str`, `stderr: str`.

2. `class GhClient(Protocol):` declaring methods (all `...` bodies):
   - Read-only: `auth_status() -> GhResult`, `repo_view(owner_repo: str) -> GhResult`, `repo_permissions(owner_repo: str) -> dict`, `branch_protection(owner_repo: str, branch: str) -> dict`.
   - PR/issue lifecycle (Phase 1 declares only): `create_branch(owner_repo: str, branch: str, base: str) -> GhResult`, `open_pr(owner_repo: str, head: str, base: str, title: str, body: str, labels: list[str], draft: bool = True) -> GhResult`, `merge_pr(owner_repo: str, number: int, method: str = "squash") -> GhResult`, `open_issue(owner_repo: str, title: str, body: str, labels: list[str]) -> GhResult`, `close_issue(owner_repo: str, number: int, comment: Optional[str] = None) -> GhResult`, `find_by_idempotency_key(owner_repo: str, kind: str, key: str) -> Optional[int]`.

3. `class RealGhClient:` — implements ONLY `_run`, `auth_status`, `repo_view`, `repo_permissions`, `branch_protection`. The other 6 PR/issue methods MUST be defined as `def create_branch(self, *a, **k): raise NotImplementedError("Phase 2")` and analogous for `open_pr`, `merge_pr`, `open_issue`, `close_issue`, `find_by_idempotency_key`.
   - `_run(self, args)` does `cp = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)`; returns `GhResult(cp.returncode, cp.stdout, cp.stderr)`.
   - `auth_status` returns `self._run(["auth", "status", "--hostname", "github.com"])`.
   - `repo_view(owner_repo)` returns `self._run(["api", f"repos/{owner_repo}"])`.
   - `repo_permissions(owner_repo)` calls `self._run(["api", f"repos/{owner_repo}", "--jq", ".permissions"])`; on rc!=0 returns `{}`; otherwise `json.loads(r.stdout)` with JSONDecodeError caught → `{}`.
   - `branch_protection(owner_repo, branch)` calls `self._run(["api", f"repos/{owner_repo}/branches/{branch}/protection"])`; same `{}` fallback.

4. `@dataclass class FakeGhCall` with fields `method: str`, `args: tuple`, `kwargs: dict`.

5. `@dataclass class FakeGhClient` with fields:
   - `calls: list[FakeGhCall] = field(default_factory=list)`
   - `auth_ok: bool = True`
   - `repo_perms: dict = field(default_factory=lambda: {"pull": True, "push": True, "admin": False})`
   - `protection: dict = field(default_factory=dict)`

   Helper `_record(self, method, *args, **kwargs)` appends to `self.calls`.

   All 10 GhClient methods implemented verbatim per RESEARCH §10 lines 567-599 (records call, returns ok-shaped GhResult or dict). Specifically:
   - `auth_status` returns `GhResult(0 if self.auth_ok else 1, "", "")`.
   - `repo_view(owner_repo)` returns `GhResult(0, '{"name":"' + owner_repo + '"}', "")`.
   - `repo_permissions(owner_repo)` returns `dict(self.repo_perms)`.
   - `branch_protection(owner_repo, branch)` returns `dict(self.protection)`.
   - `create_branch(*a, **k)` records and returns `GhResult(0, "", "")`.
   - `open_pr(*a, **k)` records and returns `GhResult(0, "https://example/pr/1", "")`.
   - `merge_pr(*a, **k)` records and returns `GhResult(0, "merged", "")`.
   - `open_issue(*a, **k)` records and returns `GhResult(0, "https://example/issue/1", "")`.
   - `close_issue(*a, **k)` records and returns `GhResult(0, "", "")`.
   - `find_by_idempotency_key(*a, **k)` records and returns `None`.

**No tests in this task** — combined test file lives in Task 2.2 since gh_client + preflight tests are coupled.
  </action>
  <verify>
    <automated>cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin && python3 -c "from skills.adapt.lib.gh_client import GhClient, GhResult, RealGhClient, FakeGhClient, FakeGhCall; f = FakeGhClient(); assert f.auth_status().returncode == 0; assert f.repo_permissions('a/b') == {'pull': True, 'push': True, 'admin': False}; rc = RealGhClient(); raised = False
try: rc.open_pr()
except NotImplementedError as e:
    raised = 'Phase 2' in str(e)
assert raised, 'RealGhClient.open_pr must raise NotImplementedError(Phase 2)'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -c "from skills.adapt.lib.gh_client import GhClient, GhResult, RealGhClient, FakeGhClient, FakeGhCall; print('ok')"` prints `ok`.
    - `grep -q "class GhClient(Protocol)" skills/adapt/lib/gh_client.py`.
    - `grep -q "raise NotImplementedError(\"Phase 2\")" skills/adapt/lib/gh_client.py` (one occurrence per method) — `grep -c "NotImplementedError(\"Phase 2\")" skills/adapt/lib/gh_client.py` returns 6.
    - `grep -q "auth_status" skills/adapt/lib/gh_client.py` AND `grep -q "branch_protection" skills/adapt/lib/gh_client.py` AND `grep -q "find_by_idempotency_key" skills/adapt/lib/gh_client.py`.
    - `grep -q "@dataclass(frozen=True)" skills/adapt/lib/gh_client.py` (for GhResult).
    - `python3 -c "from dataclasses import is_dataclass; from skills.adapt.lib.gh_client import FakeGhClient, GhResult; assert is_dataclass(FakeGhClient); assert is_dataclass(GhResult)"` exits 0.
  </acceptance_criteria>
  <done>GhClient Protocol + RealGhClient stub + FakeGhClient recorder are importable; PR/issue methods raise NotImplementedError("Phase 2") in RealGhClient; FakeGhClient records calls and returns ok-shaped responses.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2.2: run_preflight() + PreflightResult + dry-run skip-write tests</name>
  <read_first>
    - .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md (§4 Preflight commands, full table + fail-fast format + dry-run path; lines 196-238)
    - skills/adapt/lib/gh_client.py (just created in Task 2.1; FakeGhClient is the test substrate)
    - .planning/research/PITFALLS.md (Pitfall 7 — GH rate limits / auth scope / branch protection)
  </read_first>
  <behavior>
    - Test (dry_run=True skips write probes): build a `FakeGhClient(auth_ok=True)`, build a synthetic ReposBlock-like object (use `types.SimpleNamespace` or instantiate `ReposBlock` with valid HttpUrls if plan 01 is done — both work since import is lazy), call `run_preflight(repos, dry_run=True, gh=fake)`, assert `result.ok is True` AND no `FakeGhCall` in `fake.calls` has `method == "repo_permissions"` (the live-write probe).
    - Test (dry_run=False, auth_ok=False): `FakeGhClient(auth_ok=False)` → result.ok is False AND `"gh_auth_status"` substring appears in some entry of `result.failures`.
    - Test (dry_run=False, missing push): `FakeGhClient(auth_ok=True, repo_perms={"pull": True, "push": False, "admin": False})` → `result.ok is False` AND a failure mentions `"write"` or `"push"`.
    - Test (branch protection compatibility — required reviews fail): `FakeGhClient(protection={"required_pull_request_reviews": {"required_approving_review_count": 1}})` with `dry_run=False` → `result.ok is False` AND a failure mentions `"approving review"` or `"branch_protection"`.
    - Test (W4 — restrictions hard-fail): `FakeGhClient(protection={"restrictions": {"users": [{"login": "alice"}], "teams": [], "apps": []}})` with `dry_run=False` → `result.ok is False` AND a failure mentions `"push restrictions allowlist"` AND the failure includes `"users=1"`.
    - Test (W4 — lock_branch hard-fail): `FakeGhClient(protection={"lock_branch": True})` with `dry_run=False` → `result.ok is False` AND a failure mentions `"lock_branch=true"`.
    - Test (W4 — required_status_checks.contexts warn-only): `FakeGhClient(protection={"required_status_checks": {"contexts": ["ci/build", "ci/test"]}})` with `dry_run=False` → `result.ok is True` (no failures) AND `result.warnings` contains an entry mentioning `"required_status_checks.contexts"` AND the contexts list.
    - Test (W4 — enforce_admins informational): `FakeGhClient(protection={"enforce_admins": True})` → `result.ok is True` AND `result.warnings` contains an entry mentioning `"enforce_admins=true"`.
    - Test (W4 — required_linear_history informational): `FakeGhClient(protection={"required_linear_history": True})` → `result.ok is True` AND `result.warnings` contains an entry mentioning `"required_linear_history=true"`.
    - Test (W4 — combined hard-fail + warn): `FakeGhClient(protection={"required_pull_request_reviews": {"required_approving_review_count": 2}, "lock_branch": True, "required_status_checks": {"contexts": ["ci/build"]}})` → `result.ok is False`; `result.failures` contains BOTH the approving-review entry AND the lock_branch entry; `result.warnings` contains the contexts entry.
    - Test (W4 — empty/None protection still compatible): `FakeGhClient(protection={})` → `result.ok is True`, `result.warnings == []` for the branch-protection portion.
    - Test (PreflightResult shape): `from dataclasses import is_dataclass; from skills.adapt.lib.preflight import PreflightResult; assert is_dataclass(PreflightResult)`.
    - Test (gh CLI absent — robustness): does NOT need to run real gh; the FakeGhClient substrate already shields tests from real gh.
  </behavior>
  <action>
**File 1: `skills/adapt/lib/preflight.py`** — implement per RESEARCH §4. Required structure:

```python
"""Preflight checks for loop-engineering startup. Fails fast with a precise,
ordered, human-readable error block; on dry_run=True, skips live-write probes
but still validates URL shape and gh auth status."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import urllib.request, urllib.error

if TYPE_CHECKING:
    from skills.adapt.lib.schema import ReposBlock
    from skills.adapt.lib.gh_client import GhClient


@dataclass
class PreflightResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)   # W4: branch-protection warn-only items
    branch_protection: dict = field(default_factory=dict)


def _owner_repo_from_url(url: str) -> str:
    """Extract '<owner>/<repo>' from a https://github.com/<owner>/<repo>(.git)? URL."""
    # Strip scheme + host, trailing slash, .git suffix
    # ... implementation: urlparse path -> strip leading "/", strip trailing ".git" / "/"
    from urllib.parse import urlparse
    p = urlparse(str(url)).path.strip("/")
    if p.endswith(".git"):
        p = p[:-4]
    parts = p.split("/")
    if len(parts) < 2:
        return p
    return f"{parts[0]}/{parts[1]}"


def _check_branch_protection_compatible(prot: dict) -> tuple[list[str], list[str]]:
    """Return (fail_reasons, warnings).

    Hard-fail (fail_reasons) — auto-merge cannot satisfy these without a
    Phase 2 allowlist override (deferred):
      - required_pull_request_reviews.required_approving_review_count > 0
      - restrictions present and non-empty (push allowlist locks out the bot)
      - lock_branch == True (no commits allowed at all)

    Warn-only (Phase 1 informational; Phase 2 must satisfy):
      - required_status_checks.contexts non-empty (Phase 2 CI must pass them)
      - enforce_admins == True (informational; affects who can merge)
      - required_linear_history == True (informational; affects merge strategy)

    Empty dict (no protection) = compatible, no warnings."""
    fail_reasons: list[str] = []
    warnings: list[str] = []
    if not prot:
        return fail_reasons, warnings

    required = prot.get("required_pull_request_reviews") or {}
    n = required.get("required_approving_review_count", 0)
    if n and n > 0:
        fail_reasons.append(
            f"requires {n} approving review(s) (loop auto-merge incompatible)"
        )

    # restrictions: GH returns {"users": [...], "teams": [...], "apps": [...]}
    # when set; empty/missing means no restriction. Non-empty = hard fail.
    restrictions = prot.get("restrictions") or {}
    if restrictions:
        users = restrictions.get("users") or []
        teams = restrictions.get("teams") or []
        apps = restrictions.get("apps") or []
        if users or teams or apps:
            fail_reasons.append(
                f"push restrictions allowlist non-empty "
                f"(users={len(users)}, teams={len(teams)}, apps={len(apps)}); "
                f"loop bot is not in allowlist (Phase 2 will add --allowlist-override)"
            )

    if prot.get("lock_branch") is True:
        fail_reasons.append(
            "lock_branch=true (branch is fully locked; no commits allowed)"
        )

    rsc = prot.get("required_status_checks") or {}
    contexts = rsc.get("contexts") or []
    if contexts:
        warnings.append(
            f"required_status_checks.contexts={contexts!r} "
            f"(Phase 1 warn-only; Phase 2 CI must satisfy these)"
        )

    if prot.get("enforce_admins") is True:
        warnings.append(
            "enforce_admins=true (informational; admins also subject to protection)"
        )

    if prot.get("required_linear_history") is True:
        warnings.append(
            "required_linear_history=true (informational; Phase 2 merge strategy "
            "must use squash/rebase, not merge-commit)"
        )

    return fail_reasons, warnings


def run_preflight(repos: "ReposBlock", *, dry_run: bool, gh: "GhClient") -> PreflightResult:
    failures: list[str] = []
    warnings_list: list[str] = []   # W4: branch-protection warn-only items
    branch_protection_record: dict = {}

    # 1. gh auth status — always run, even in dry_run
    auth = gh.auth_status()
    if auth.returncode != 0:
        failures.append("gh_auth_status: not logged in (run `gh auth login`)")

    # 2. For each external repo, check read perm + (live mode only) write perm + branch protection
    for label, spec in (("loongforge", repos.loongforge), ("megatron", repos.megatron)):
        owner_repo = _owner_repo_from_url(str(spec.url))
        rv = gh.repo_view(owner_repo)
        if rv.returncode != 0:
            failures.append(f"{label}_read: cannot read {owner_repo}")
            continue
        if not dry_run:
            perms = gh.repo_permissions(owner_repo)
            if not perms.get("push"):
                failures.append(f"{label}_write: missing push permission on {owner_repo}")
            prot = gh.branch_protection(owner_repo, spec.base_ref)
            branch_protection_record[owner_repo] = prot
            fail_reasons, warns = _check_branch_protection_compatible(prot)
            for fr in fail_reasons:
                failures.append(
                    f"branch_protection: {owner_repo}:{spec.base_ref} {fr}"
                )
            for w in warns:
                warnings_list.append(
                    f"branch_protection: {owner_repo}:{spec.base_ref} {w}"
                )

    # 3. HF impl URL reachable (gh api on the github repo)
    impl_owner_repo = _owner_repo_from_url(str(repos.hf_impl.url))
    if "/" in impl_owner_repo:
        impl_rv = gh.repo_view(impl_owner_repo)
        if impl_rv.returncode != 0:
            failures.append(f"hf_impl_read: cannot read {impl_owner_repo}")

    # 4. ckpt URL reachable — HEAD probe to https://huggingface.co/api/models/<org>/<model>
    #    Always run (read-only) unless we cannot reach the network at all.
    try:
        ckpt_url = str(repos.hf_ckpt.url)
        # ... if URL is huggingface.co/<org>/<model>, derive api URL; else fall back to HEAD on URL itself
        from urllib.parse import urlparse as _urlparse
        p = _urlparse(ckpt_url)
        api_url = ckpt_url
        if p.netloc == "huggingface.co":
            path = p.path.strip("/")
            if path.count("/") >= 1:
                api_url = f"https://huggingface.co/api/models/{path}"
        req = urllib.request.Request(api_url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                failures.append(f"hf_ckpt_unreachable: HTTP {resp.status} on {api_url}")
    except (urllib.error.URLError, OSError) as e:
        # Don't fail dry_run for unreachable network (matches RESEARCH §4 dry-run path).
        if not dry_run:
            failures.append(f"hf_ckpt_unreachable: {type(e).__name__} on {ckpt_url}")

    return PreflightResult(
        ok=not failures,
        failures=failures,
        warnings=warnings_list,
        branch_protection=branch_protection_record,
    )


def format_failures(result: PreflightResult) -> str:
    """Render the canonical fail-fast error block.

    W4: also renders warnings (warn-only branch-protection items) when present,
    even when ok=True (warnings are informational, do not block)."""
    lines: list[str] = []
    if not result.ok:
        lines.append("PREFLIGHT FAILED:")
        for f in result.failures:
            lines.append(f"  - {f}")
    if result.warnings:
        if lines:
            lines.append("")
        lines.append("PREFLIGHT WARNINGS (informational):")
        for w in result.warnings:
            lines.append(f"  - {w}")
    if not result.ok:
        lines.append("Aborting. Re-run with --dry-run to bypass live-write probes.")
    return "\n".join(lines)
```

Key invariants (verbatim from RESEARCH §4):
- `dry_run=True` MUST skip `repo_permissions` and `branch_protection` calls but MUST still call `auth_status` and `repo_view`.
- `dry_run=True` MUST tolerate ckpt URL unreachable (network failure) without adding to failures.
- Failure strings in `result.failures` MUST start with a stable prefix (`gh_auth_status`, `<label>_read`, `<label>_write`, `branch_protection`, `hf_impl_read`, `hf_ckpt_unreachable`).

**File 2: `skills/adapt/tests/lib/test_preflight_dry_run.py`** — implement all sub-tests from `<behavior>`. Use a tiny helper to build a `ReposBlock`-like object without forcing import order:

```python
import types
def _fake_repos():
    return types.SimpleNamespace(
        hf_impl=types.SimpleNamespace(url="https://github.com/huggingface/transformers"),
        hf_ckpt=types.SimpleNamespace(url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base"),
        loongforge=types.SimpleNamespace(url="https://github.com/Zachary-wW/LoongForge", base_ref="main"),
        megatron=types.SimpleNamespace(url="https://github.com/Zachary-wW/Loong-Megatron", base_ref="loong-main/core_v0.15.0"),
    )
```

(Using `SimpleNamespace` keeps this test independent of plan 01's schema landing — important for Wave 1 parallelism. The runtime preflight code only does `repos.loongforge.url` etc.)

Each sub-test asserts the exact invariant from `<behavior>`. For dry_run=True, also stub network: monkeypatch `urllib.request.urlopen` to raise `urllib.error.URLError("net")` so the test never depends on real network — assert `result.ok is True` regardless (dry_run absorbs the network failure).
  </action>
  <verify>
    <automated>cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin && python3 -m pytest skills/adapt/tests/lib/test_preflight_dry_run.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -c "from skills.adapt.lib.preflight import run_preflight, PreflightResult, format_failures; print('ok')"` prints `ok`.
    - `grep -q "def run_preflight" skills/adapt/lib/preflight.py` AND `grep -q "dry_run" skills/adapt/lib/preflight.py`.
    - `grep -q "PREFLIGHT FAILED:" skills/adapt/lib/preflight.py` (canonical error header).
    - `grep -q "gh_auth_status" skills/adapt/lib/preflight.py` AND `grep -q "branch_protection" skills/adapt/lib/preflight.py` AND `grep -q "hf_ckpt_unreachable" skills/adapt/lib/preflight.py`.
    - W4: `grep -q "lock_branch" skills/adapt/lib/preflight.py` AND `grep -q "push restrictions allowlist" skills/adapt/lib/preflight.py` AND `grep -q "required_status_checks" skills/adapt/lib/preflight.py` AND `grep -q "enforce_admins" skills/adapt/lib/preflight.py` AND `grep -q "required_linear_history" skills/adapt/lib/preflight.py`.
    - W4: `grep -q "PREFLIGHT WARNINGS" skills/adapt/lib/preflight.py` (warn-only renderer in format_failures).
    - W4: `python3 -c "from dataclasses import fields; from skills.adapt.lib.preflight import PreflightResult; names = {f.name for f in fields(PreflightResult)}; assert 'warnings' in names, names"` exits 0.
    - W4: existing `required_approving_review_count` test in `test_preflight_dry_run.py` MUST still pass after the signature change to `_check_branch_protection_compatible` returning `(fail_reasons, warnings)`.
    - `python3 -m pytest skills/adapt/tests/lib/test_preflight_dry_run.py -x -q` exits 0.
    - Negative assertion: `python3 -c "from skills.adapt.lib.gh_client import FakeGhClient; from skills.adapt.lib.preflight import run_preflight; import types; r = types.SimpleNamespace(hf_impl=types.SimpleNamespace(url='https://github.com/huggingface/transformers'), hf_ckpt=types.SimpleNamespace(url='https://huggingface.co/x/y'), loongforge=types.SimpleNamespace(url='https://github.com/a/b', base_ref='main'), megatron=types.SimpleNamespace(url='https://github.com/c/d', base_ref='main')); f = FakeGhClient(); res = run_preflight(r, dry_run=True, gh=f); assert all(c.method != 'repo_permissions' for c in f.calls), 'dry_run must not call repo_permissions'"` exits 0 (network call may still happen — that's tolerated; test only asserts no permissions probe).
  </acceptance_criteria>
  <done>run_preflight + PreflightResult + format_failures shipped; dry-run path skips repo_permissions and branch_protection live-write probes; INPUT-03 fail-fast invariants and INPUT-04 dry-run substrate verified by test_preflight_dry_run.py.</done>
</task>

</tasks>

<verification>
After both tasks complete, run from repo root:

```
cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin
python3 -m pytest skills/adapt/tests/lib/test_preflight_dry_run.py -x -q
```

Wave-level invariant: at the end of Wave 1 (plans 01 + 02 both green), `python3 -m pytest skills/adapt/tests/lib/ -x -q` MUST exit 0.
</verification>

<success_criteria>
- `GhClient` Protocol declares full PR/issue surface; `RealGhClient` implements only the preflight subset; the 6 PR/issue methods raise `NotImplementedError("Phase 2")`.
- `FakeGhClient` records every call; configurable failure modes (`auth_ok`, `repo_perms`, `protection`) drive negative-path tests.
- `run_preflight(repos, dry_run=True, gh=FakeGhClient())` is `ok=True` and never calls `repo_permissions` or `branch_protection`.
- Live-mode preflight failures emit stable-prefix strings (`gh_auth_status`, `<label>_write`, `branch_protection: <repo>:<branch> requires N approving review(s) ...`).
- W4: branch-protection compat checks cover hard-fail (`required_approving_review_count > 0`, `restrictions` non-empty, `lock_branch=true`) AND warn-only (`required_status_checks.contexts` non-empty, `enforce_admins=true`, `required_linear_history=true`); `PreflightResult.warnings` list carries warn-only entries; `format_failures` renders both blocks.
- Test `test_preflight_dry_run.py` covers INPUT-03 fail-fast invariants and INPUT-04 dry-run skip-writes invariants.
</success_criteria>

<output>
After completion, create `.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/02-SUMMARY.md` summarizing:
- Files created (paths)
- GhClient Protocol method list (one line per method)
- run_preflight failure-string prefixes (the stable-string contract that plan 03 / Phase 2 / Phase 5 ACC-01 will assert against)
- Test file pass status
- Any deviations from RESEARCH §4 / §10
</output>
