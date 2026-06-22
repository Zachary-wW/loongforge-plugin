---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
plan: 03
subsystem: cli
tags: [argparse, pydantic, preflight, gh-client, dry-run, loop-engineering]

# Dependency graph
requires:
  - phase: 01-loop-foundation-contracts-schemas-safety-plumbing/01
    provides: Pydantic schema models (RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget)
  - phase: 01-loop-foundation-contracts-schemas-safety-plumbing/02
    provides: GhClient Protocol + FakeGhClient + RealGhClient, run_preflight + PreflightResult + format_failures
provides:
  - "8 URL CLI flags + --dry-run on loongforge-adapt"
  - "repos: and loop: blocks in run_inputs.yml when loop-engineering mode active"
  - "Preflight check invoked from init_run_dir (skipped on --resume)"
  - "All-or-nothing URL validation (partial flags rejected)"
  - "COMPAT-02: run_state.json legacy schema unchanged"
affects: [phase-02-loop-controller, phase-03-loop-implementation]

# Tech tracking
tech-stack:
  added: []
  patterns: [module-level-imports-for-monkeypatch, all-or-nothing-cli-flags, dry-run-aware-client-selection]

key-files:
  created:
    - skills/adapt/tests/lib/test_run_cli.py
  modified:
    - skills/adapt/scripts/run.py

key-decisions:
  - "8 explicit per-field flags instead of combined URL@ref:subpath syntax (shell quoting of @/: is fragile)"
  - "All-or-nothing URL validation post-parse (not argparse required=) to keep legacy positional hf_path working alone"
  - "Module-level imports of run_preflight/FakeGhClient/RealGhClient for monkey-patchability (W5)"
  - "Preflight called only from init_run_dir when repos is not None; --resume intentionally skips it"

patterns-established:
  - "Module-level imports for testability: run_preflight imported at module scope so monkeypatch.setattr intercepts calls"
  - "Dry-run-aware client selection: FakeGhClient() if dry_run else RealGhClient()"

requirements-completed: [INPUT-01, INPUT-02, INPUT-04, COMPAT-02]

# Metrics
duration: 6min
completed: 2026-06-22
---

# Phase 01 Plan 03: CLI Extension Summary

**8 URL flags + --dry-run wired to repos/loop blocks + preflight; legacy positional invocation unchanged; W5 monkey-patch proves v2-init calls preflight and --resume does not**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-22T08:21:15Z
- **Completed:** 2026-06-22T08:27:09Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Extended `run.py` with 8 URL flags (`--hf-impl-url`, `--hf-impl-ref`, `--hf-impl-subpath`, `--hf-ckpt-url`, `--hf-ckpt-revision`, `--loongforge-repo`, `--loongforge-base-ref`, `--megatron-repo`, `--megatron-base-ref`) and `--dry-run`
- `repos:` and `loop:` blocks emitted to `run_inputs.yml` when all 4 URL flags provided (loop-engineering mode)
- All-or-nothing validation: partial URL flags trigger `parser.error` with precise message
- Preflight invoked from `init_run_dir` when `repos is not None`, with `FakeGhClient` for `--dry-run`
- `--resume` intentionally skips preflight (comment added in code)
- Legacy `run_state.json` schema unchanged (no `repos`/`loop` top-level keys)
- W5 runtime-traced test proves monkey-patching `skills.adapt.scripts.run.run_preflight` works

## Task Commits

1. **Task 3.1 (RED): Add failing CLI tests** - `232dcb4` (test)
2. **Task 3.1 (GREEN): Implement 8 URL flags + --dry-run + repos/loop blocks + preflight** - `a899d37` (feat)

## Files Created/Modified
- `skills/adapt/scripts/run.py` - Extended CLI: 8 URL flags + --dry-run; _build_run_inputs accepts repos/loop kwargs; init_run_dir invokes preflight (skipped on --resume)
- `skills/adapt/tests/lib/test_run_cli.py` - 11 CLI round-trip tests: legacy invocation, v2 invocation, partial-flags rejection, resume-skip-preflight, W5 monkey-patch tracing, COMPAT-02 legacy state

## run.py Edit Diff Regions

| Region | Lines (approx) | Change |
|--------|----------------|--------|
| Imports | 32-36 | Added schema/preflight/gh_client imports |
| `_build_run_inputs` | 41-80 | Added `repos`/`loop` kwargs; conditional injection |
| `init_run_dir` | 199-245 | Added `repos`/`loop`/`dry_run` params; preflight call |
| Argparse repos_group | 346-360 | 8 URL flags in "repos (loop engineering)" group |
| Argparse dryrun_group | 362-364 | --dry-run flag |
| All-or-nothing validation | 376-383 | URL flags validation |
| --resume branch | 385-386 | Added preflight-skip comment |
| Init branch repos/loop build | 416-428 | Build repos_dict and loop_dict from Pydantic |
| init_run_dir call site | 430-446 | Pass repos/loop/dry_run to init_run_dir |

## New CLI Flag List

| Flag | Default | Help |
|------|---------|------|
| `--hf-impl-url` | None | HF model impl repo URL |
| `--hf-impl-ref` | "main" | HF impl branch/tag/sha |
| `--hf-impl-subpath` | None | Path within HF impl repo |
| `--hf-ckpt-url` | None | HF Hub ckpt URL |
| `--hf-ckpt-revision` | "main" | HF ckpt revision |
| `--loongforge-repo` | None | LoongForge repo URL |
| `--loongforge-base-ref` | "main" | LoongForge base branch |
| `--megatron-repo` | None | Loong-Megatron repo URL |
| `--megatron-base-ref` | "loong-main/core_v0.15.0" | Megatron base branch |
| `--dry-run` | False | Use FakeGhClient; skip live gh writes |

## Preflight NOT Called from --resume

```python
    if args.resume:
        # Preflight is intentionally skipped on --resume; the original init already passed it.
        from_phase = int(args.from_phase) if args.from_phase is not None else None
        inputs = resume_run_dir(args.resume, from_phase=from_phase)
```

## Test Counts and Pass Status

| Test class | Count | Status |
|------------|-------|--------|
| TestLegacyInvocation | 3 | PASS |
| TestV2Invocation | 3 | PASS |
| TestPartialURLFlagsRejected | 2 | PASS |
| TestResumeSkipsPreflight | 1 | PASS |
| TestW5PreflightTracing | 1 | PASS |
| TestLegacyStateCompat | 1 | PASS |
| **Total new** | **11** | **ALL PASS** |
| Existing tests (test_plugin_layout + lib/) | 113 | ALL PASS |
| **Grand total** | **124** | **ALL PASS** |

## Decisions Made
- 8 explicit per-field flags instead of combined URL@ref:subpath syntax (shell quoting of @/: is fragile; --help lists them clearly)
- All-or-nothing URL validation post-parse (not argparse required=) to keep legacy positional hf_path working alone
- Module-level imports of run_preflight/FakeGhClient/RealGhClient for monkey-patchability (W5 requirement)
- Preflight called only from init_run_dir when repos is not None; --resume intentionally skips it

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Worktree was initially based on a commit before plans 01/02 were merged. Resolved by merging `refactor/adapt-loop-engineering` branch into the worktree (fast-forward). No code impact.

## Next Phase Readiness
- CLI surface complete: 8 URL flags + --dry-run + all-or-nothing validation
- Preflight wired from init path only (not --resume)
- Legacy compat maintained (run_state.json unchanged)
- Ready for plan 04 (validator hook + lints) which operates on validate_phase_completion.py, not run.py

## Self-Check: PASSED

- FOUND: skills/adapt/scripts/run.py
- FOUND: skills/adapt/tests/lib/test_run_cli.py
- FOUND: .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/03-SUMMARY.md
- FOUND: 232dcb4 (RED test commit)
- FOUND: a899d37 (GREEN feat commit)
- 154 tests passed (0 failed)

---
*Phase: 01-loop-foundation-contracts-schemas-safety-plumbing*
*Completed: 2026-06-22*
