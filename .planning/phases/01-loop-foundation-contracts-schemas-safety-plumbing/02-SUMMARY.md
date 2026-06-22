---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
plan: 02
subsystem: gh-adapter
tags: [gh-cli, protocol, preflight, dry-run, branch-protection, fake-gh]

# Dependency graph
requires: []
provides:
  - GhClient Protocol (10 methods: auth_status, repo_view, repo_permissions, branch_protection, create_branch, open_pr, merge_pr, open_issue, close_issue, find_by_idempotency_key)
  - RealGhClient with preflight subset implemented; 6 PR/issue methods raise NotImplementedError("Phase 2")
  - FakeGhClient in-memory recorder with parameterizable failure modes (auth_ok, repo_perms, protection)
  - run_preflight() with dry_run=True path skipping live-write probes
  - PreflightResult dataclass with ok, failures, warnings, branch_protection fields
  - format_failures() rendering both PREFLIGHT FAILED and PREFLIGHT WARNINGS blocks
  - _check_branch_protection_compatible() with W4 hard-fail and warn-only logic
affects: [03-PLAN, 04-PLAN, phase-02-loop-controller, phase-05-acc-01]

# Tech tracking
tech-stack:
  added: []
  patterns: [GhClient-Protocol-adapter, FakeGhClient-in-memory-recorder, stable-prefix-failure-strings, dry-run-skip-writes, branch-protection-compat-check]

key-files:
  created:
    - skills/adapt/lib/gh_client.py
    - skills/adapt/lib/preflight.py
    - skills/adapt/tests/lib/test_preflight_dry_run.py
    - skills/__init__.py
    - skills/adapt/__init__.py
    - skills/adapt/lib/__init__.py
    - skills/adapt/tests/__init__.py
    - skills/adapt/tests/lib/__init__.py
  modified: []

key-decisions:
  - "GhClient is typing.Protocol (not ABC) for structural typing; FakeGhClient and RealGhClient are independent classes"
  - "RealGhClient PR/issue stubs raise NotImplementedError('Phase 2') so mypy/pytest surface missing impl immediately"
  - "FakeGhClient records all calls via FakeGhCall dataclass; PR/issue methods return ok-shaped GhResult (not raise)"
  - "dry_run=True skips repo_permissions and branch_protection but still runs auth_status and repo_view"
  - "Branch protection checks split into hard-fail (approving reviews, restrictions, lock_branch) and warn-only (status_checks, enforce_admins, linear_history)"

patterns-established:
  - "GhClient-Protocol-adapter: wrap subprocess gh calls behind Protocol for testability"
  - "FakeGhClient-in-memory-recorder: record all method calls, return ok-shaped responses, parameterizable failure modes"
  - "stable-prefix-failure-strings: all PreflightResult.failures entries start with a machine-parseable prefix (gh_auth_status, <label>_read, <label>_write, branch_protection, hf_impl_read, hf_ckpt_unreachable)"
  - "dry-run-skip-writes: dry_run=True skips write probes but keeps read probes and auth checks"
  - "branch-protection-compat-check: _check_branch_protection_compatible returns (fail_reasons, warnings) tuple"

requirements-completed: [INPUT-03, INPUT-04]

# Metrics
duration: 7min
completed: 2026-06-22
---

# Phase 01 Plan 02: GhClient + Preflight Summary

**GhClient Protocol (10 methods) + RealGhClient preflight subset + FakeGhClient in-memory recorder; run_preflight() with dry_run=True skip-writes and W4 branch-protection compat checks (hard-fail + warn-only)**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-22T08:04:05Z
- **Completed:** 2026-06-22T08:11:32Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- GhClient Protocol declares full PR/issue surface (10 methods); RealGhClient implements only 4 read-only preflight methods; 6 PR/issue stubs raise NotImplementedError("Phase 2")
- FakeGhClient records every call, returns ok-shaped responses by default; parameterizable failure modes (auth_ok, repo_perms, protection) drive negative-path tests
- run_preflight() with dry_run=True skips repo_permissions and branch_protection calls but still calls auth_status and repo_view; tolerates ckpt URL unreachable in dry_run mode
- W4 branch-protection compatibility: hard-fail on approving reviews / restrictions / lock_branch; warn-only on status_checks / enforce_admins / linear_history
- 34 tests covering INPUT-03 fail-fast + INPUT-04 dry-run + W4 branch-protection compat

## Task Commits

Each task was committed atomically:

1. **Task 2.1: GhClient Protocol + RealGhClient + FakeGhClient** - `0c151e8` (feat)
2. **Task 2.2: run_preflight + PreflightResult + dry-run skip-write tests** - `974174e` (feat)

## Files Created/Modified
- `skills/adapt/lib/gh_client.py` - GhClient Protocol, GhResult dataclass, RealGhClient (preflight subset), FakeGhClient (in-memory recorder), FakeGhCall dataclass
- `skills/adapt/lib/preflight.py` - run_preflight(), PreflightResult dataclass, _owner_repo_from_url(), _check_branch_protection_compatible(), format_failures()
- `skills/adapt/tests/lib/test_preflight_dry_run.py` - 34 tests: dry-run skip-writes, auth fail-fast, push permission, W4 branch-protection hard-fail and warn-only, failure-string prefixes
- `skills/__init__.py` - Package marker for import chain
- `skills/adapt/__init__.py` - Package marker for import chain
- `skills/adapt/lib/__init__.py` - Package marker for import chain
- `skills/adapt/tests/__init__.py` - Package marker for import chain
- `skills/adapt/tests/lib/__init__.py` - Package marker for import chain

## GhClient Protocol Method List

| Method | Category | RealGhClient Status |
|--------|----------|-------------------|
| `auth_status()` | Read-only / preflight | Implemented |
| `repo_view(owner_repo)` | Read-only / preflight | Implemented |
| `repo_permissions(owner_repo)` | Read-only / preflight | Implemented |
| `branch_protection(owner_repo, branch)` | Read-only / preflight | Implemented |
| `create_branch(owner_repo, branch, base)` | PR/issue lifecycle | NotImplementedError("Phase 2") |
| `open_pr(owner_repo, head, base, title, body, labels, draft)` | PR/issue lifecycle | NotImplementedError("Phase 2") |
| `merge_pr(owner_repo, number, method)` | PR/issue lifecycle | NotImplementedError("Phase 2") |
| `open_issue(owner_repo, title, body, labels)` | PR/issue lifecycle | NotImplementedError("Phase 2") |
| `close_issue(owner_repo, number, comment)` | PR/issue lifecycle | NotImplementedError("Phase 2") |
| `find_by_idempotency_key(owner_repo, kind, key)` | PR/issue lifecycle | NotImplementedError("Phase 2") |

## run_preflight Failure-String Prefixes

These are the stable-string contract that plan 03 / Phase 2 / Phase 5 ACC-01 will assert against:

| Prefix | Meaning |
|--------|---------|
| `gh_auth_status:` | gh CLI not authenticated |
| `loongforge_read:` | Cannot read LoongForge repo |
| `loongforge_write:` | Missing push permission on LoongForge repo |
| `megatron_read:` | Cannot read Loong-Megatron repo |
| `megatron_write:` | Missing push permission on Loong-Megatron repo |
| `branch_protection:` | Branch protection incompatibility (hard-fail or warn) |
| `hf_impl_read:` | Cannot read HF impl repo |
| `hf_ckpt_unreachable:` | HF checkpoint URL unreachable |

## Decisions Made
- GhClient is typing.Protocol (not ABC) for structural typing without forcing inheritance
- RealGhClient PR/issue stubs raise NotImplementedError("Phase 2") so downstream code surfaces missing impl at runtime
- FakeGhClient PR/issue methods return ok-shaped GhResult (not raise) so tests can verify call recording
- dry_run=True skips repo_permissions and branch_protection but keeps auth_status and repo_view
- W4 branch-protection checks split into hard-fail vs warn-only; PreflightResult.warnings carries informational items
- _owner_repo_from_url() extracts owner/repo from GitHub HTTPS URLs with .git suffix and trailing slash handling

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added __init__.py files for import chain**
- **Found during:** Task 2.1 (GhClient creation)
- **Issue:** Plan 01 owns `skills/adapt/lib/__init__.py` but it had not landed yet in this parallel worktree; without it, `from skills.adapt.lib.gh_client import ...` fails
- **Fix:** Created minimal `__init__.py` files for skills/, skills/adapt/, skills/adapt/lib/, skills/adapt/tests/, skills/adapt/tests/lib/
- **Files modified:** 5 new __init__.py files
- **Verification:** `python3 -c "from skills.adapt.lib.gh_client import GhClient"` exits 0
- **Committed in:** 0c151e8 (Task 2.1 commit)

**2. [Rule 1 - Bug] Fixed mock urlopen returning MagicMock instead of real response object**
- **Found during:** Task 2.2 (test execution)
- **Issue:** `@patch("skills.adapt.lib.preflight.urllib.request.urlopen")` mock returns MagicMock for `.status`, causing `TypeError: '>=' not supported between instances of 'MagicMock' and 'int'`
- **Fix:** Added `_mock_response()` helper that creates a mock with real `.status` integer and context manager support; configured all non-side_effect tests with `mock_urlopen.return_value = _mock_response(200)`
- **Files modified:** skills/adapt/tests/lib/test_preflight_dry_run.py
- **Verification:** All 34 tests pass
- **Committed in:** 974174e (Task 2.2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both auto-fixes necessary for correctness and test reliability. No scope creep.

## Issues Encountered
None beyond the deviations documented above.

## Next Phase Readiness
- GhClient Protocol + FakeGhClient ready for plan 03 (CLI) and plan 04 (validator hook) to use
- run_preflight() ready for plan 03's init_run_dir to call at startup
- Branch-protection compat checks provide W4 coverage for the Phase 2 loop controller
- The __init__.py files may overlap with plan 01's versions; merge will need to reconcile (plan 01 may add imports to __init__.py)

---
*Phase: 01-loop-foundation-contracts-schemas-safety-plumbing*
*Completed: 2026-06-22*

## Self-Check: PASSED

- All created files verified present: gh_client.py, preflight.py, test_preflight_dry_run.py, 02-SUMMARY.md
- All commits verified in git log: 0c151e8, 974174e
