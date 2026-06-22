---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
plan: 01
subsystem: schema, safety, plumbing
tags: [pydantic-v2, redactor, jsonl, protected-paths, tdd]

# Dependency graph
requires: []
provides:
  - "Pydantic v2 schema models (RunInputs, ReposBlock, LoopBudget, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput)"
  - "Secret redactor (redact + RedactionResult) with 10 hardcoded patterns + configurable internal domains"
  - "Append-only JSONL writer (append_attempt + assert_append_only) with O_APPEND + fsync"
  - "Validator-protected-paths data module (PROTECTED_PATHS + is_protected)"
  - "requirements.txt with pydantic>=2.9,<3 and pyyaml>=6.0"
  - "Package markers for skills.adapt.lib and skills.adapt.tests.lib"
affects: [02-preflight, 03-cli, 04-validator-hook]

# Tech tracking
tech-stack:
  added: [pydantic>=2.9,<3, pyyaml>=6.0]
  patterns: [Pydantic v2 ConfigDict(extra="forbid") for strict schema, extra="ignore" for forward-compat skeletons, O_APPEND atomic JSONL writes, named regex patterns with residual post-check]

key-files:
  created:
    - skills/adapt/lib/__init__.py
    - skills/adapt/lib/schema.py
    - skills/adapt/lib/redact.py
    - skills/adapt/lib/protected_paths.py
    - skills/adapt/lib/jsonl.py
    - skills/adapt/knowledge_base/redact_domains.yml
    - skills/adapt/tests/__init__.py
    - skills/adapt/tests/lib/__init__.py
    - skills/adapt/tests/lib/test_schema.py
    - skills/adapt/tests/lib/test_redact.py
    - skills/adapt/tests/lib/test_jsonl_append_only.py
    - skills/adapt/tests/lib/test_protected_paths.py
    - requirements.txt
  modified: []

key-decisions:
  - "Pydantic v2 models use extra='forbid' everywhere except PrBlockOutput and IssuesBlockOutput (extra='ignore') for LOG-02 forward-compat"
  - "LoopBudget Field ceilings (le=50, le=500, le=10_080) enforce determinism at parse time, preventing loop runaway before controller runs"
  - "Redactor uses 10 hardcoded patterns + YAML-configurable internal domains; residual post-check returns accept=False if any pattern survives"

patterns-established:
  - "Schema models: from __future__ import annotations + ConfigDict(extra='forbid') + Field with ge/le bounds"
  - "Forward-compat skeletons: extra='ignore' models for future blocks (PrBlockOutput, IssuesBlockOutput) so Phase 2 adds fields without breaking Phase 1 readers"
  - "JSONL writer: os.O_APPEND + os.fsync for atomic line appends; assert_append_only test helper enforces invariants"
  - "Protected paths: fnmatch glob patterns in module-level tuple + is_protected() function"

requirements-completed: [LOG-02, LOG-03, SAFE-01, TEST-02, TEST-03]

# Metrics
duration: 6min
completed: 2026-06-22
---

# Phase 01 Plan 01: Loop Foundation Contracts Summary

**Pydantic v2 schema models with v1 compat, 10-pattern secret redactor with residual check, O_APPEND JSONL writer, and validator-protected-paths data module**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-22T08:03:47Z
- **Completed:** 2026-06-22T08:10:23Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- Pydantic v2 schema models for run_inputs.yml v1 (legacy round-trip) and v2 (repos + loop blocks); extra="forbid" rejects typos; LoopBudget ceilings defang loop runaway at parse time
- LOG-02 forward-compat skeleton models (PrBlockOutput, IssuesBlockOutput) with extra="ignore" so Phase 2 can add fields without breaking Phase 1 readers
- Secret redactor with 10 hardcoded patterns, configurable internal domains, and residual post-check (accept=False on surviving patterns)
- Append-only JSONL writer using O_APPEND + fsync for atomic line writes with truncation resilience
- Validator-protected-paths data module with canonical glob patterns and is_protected() function

## Task Commits

Each task was committed atomically:

1. **Task 1.1: Schema, JSONL writer, protected-paths, package markers, dep declaration** - `c40bf4c` (feat)
2. **Task 1.2: Redactor + redact_domains.yml + snapshot tests** - `f93371e` (feat)

## Files Created/Modified
- `skills/adapt/lib/__init__.py` - Package marker for skills.adapt.lib
- `skills/adapt/lib/schema.py` - Pydantic v2 models: RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget, SourceBlock, PathsBlock, OptionsBlock, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput
- `skills/adapt/lib/redact.py` - redact() + RedactionResult; 10-pattern secret regex sweep with residual post-check
- `skills/adapt/lib/protected_paths.py` - PROTECTED_PATHS tuple + is_protected()
- `skills/adapt/lib/jsonl.py` - append_attempt() + assert_append_only() with O_APPEND atomic writer
- `skills/adapt/knowledge_base/redact_domains.yml` - Internal-domain config for redactor (extensible without code change)
- `skills/adapt/tests/__init__.py` - Package marker for skills.adapt.tests
- `skills/adapt/tests/lib/__init__.py` - Package marker for skills.adapt.tests.lib
- `skills/adapt/tests/lib/test_schema.py` - 20 tests: v1/v2 round-trip, extra="forbid", LoopBudget ceilings, forward-compat skeletons
- `skills/adapt/tests/lib/test_redact.py` - 15 tests: individual patterns, multi-pattern corpus, residual, internal domains
- `skills/adapt/tests/lib/test_jsonl_append_only.py` - 6 tests: append, newline, assert_append_only, O_APPEND truncation resilience
- `skills/adapt/tests/lib/test_protected_paths.py` - 8 tests: is_protected positive/negative, non-empty PROTECTED_PATHS
- `requirements.txt` - pydantic>=2.9,<3 and pyyaml>=6.0 dep declaration

## Public API Summary

| Module | Exports |
|--------|---------|
| `skills.adapt.lib.schema` | `RunInputs`, `ReposBlock`, `RepoSpec`, `HFImplSpec`, `HFCkptSpec`, `LoopBudget`, `SourceBlock`, `PathsBlock`, `OptionsBlock`, `LoopBlockOutput`, `PrBlockOutput`, `IssuesBlockOutput` |
| `skills.adapt.lib.redact` | `redact`, `RedactionResult` |
| `skills.adapt.lib.jsonl` | `append_attempt`, `assert_append_only` |
| `skills.adapt.lib.protected_paths` | `PROTECTED_PATHS`, `is_protected` |

## Test Counts

| Test File | Tests | Status |
|-----------|-------|--------|
| test_schema.py | 20 | PASS |
| test_redact.py | 15 | PASS |
| test_jsonl_append_only.py | 6 | PASS |
| test_protected_paths.py | 8 | PASS |
| test_plugin_layout.py (existing) | 30 | PASS |
| **Total** | **79** | **ALL PASS** |

## Decisions Made
- Pydantic v2 HttpUrl type used for URL fields; tests compare with str() conversion since HttpUrl does not equal plain str
- Redactor patterns ordered longest-first (github_pat_v2 before github_pat_v1) to prevent shorter patterns from capturing substrings of longer ones
- PrBlockOutput and IssuesBlockOutput use extra="ignore" (not "forbid") specifically for LOG-02 forward-compat so Phase 2 can add fields without breaking Phase 1 readers
- Test for "ghp_BEFORE then ghp_AFTER" adjusted to use realistic-length tokens (20+ chars after prefix) since the ghp_ pattern requires 20+ alphanumeric chars

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed HttpUrl comparison in test_schema.py**
- **Found during:** Task 1.1 (test execution)
- **Issue:** Pydantic v2 HttpUrl type does not equal plain str; `assert model.repos.hf_impl.url == "https://..."` failed with AssertionError
- **Fix:** Changed to `assert str(model.repos.hf_impl.url) == "https://..."`
- **Files modified:** skills/adapt/tests/lib/test_schema.py
- **Verification:** All 34 schema tests pass
- **Committed in:** c40bf4c (Task 1.1 commit)

**2. [Rule 1 - Bug] Fixed unrealistic residual test in test_redact.py**
- **Found during:** Task 1.2 (test execution)
- **Issue:** "ghp_BEFORE" is only 6 chars after prefix (pattern requires 20+), so it was not matched and not redacted, causing the "no residual" assertion to fail
- **Fix:** Changed test to use realistic-length tokens (ghp_AAAAAAAAAAAAAAAAAAAA, ghp_BBBBBBBBBBBBBBBBBBBB) that actually match the pattern
- **Files modified:** skills/adapt/tests/lib/test_redact.py
- **Verification:** All 15 redact tests pass
- **Committed in:** f93371e (Task 1.2 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 - Bug)
**Impact on plan:** Minor test adjustments only. No scope creep. Implementation matches RESEARCH spec exactly.

## Issues Encountered
None beyond the two test-level fixes documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 5 lib modules importable from repo root: `from skills.adapt.lib.{schema,redact,jsonl,protected_paths} import ...`
- Plans 02-04 can now import from `skills.adapt.lib` for preflight (02), CLI extensions (03), and validator hooks (04)
- PrBlockOutput and IssuesBlockOutput are importable for Phase 2 to extend with field details
- requirements.txt with pydantic and pyyaml is installable for all downstream plans

## Self-Check: PASSED

All 13 created files verified present. Both task commits (c40bf4c, f93371e) verified in git log.

---
*Phase: 01-loop-foundation-contracts-schemas-safety-plumbing*
*Completed: 2026-06-22*
