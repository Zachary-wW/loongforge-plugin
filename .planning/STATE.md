---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-06-22T08:13:38.101Z"
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 1
---

# STATE.md — Adapt Skill Loop-Engineering Refactor

> Project memory. Updated at phase transitions, plan completions, and major decisions.

---

## Project Reference

**What This Is**: Refactor `loongforge-plugin/skills/adapt` from a 6-phase HF→LoongForge adaptation skill (whose retries are local, phase-internal) into an explicit loop-engineering workflow where every code change goes through a `Probe → Edit → PR → Merge(base) → Validate → (Diagnose → Issue → Fix-PR → Review → Merge → Rerun)*` cycle against two external GitHub repos (`Zachary-wW/LoongForge` and `Zachary-wW/Loong-Megatron`). Validators are the single source of truth for loop exit.

**Core Value**: The adaptation process MUST be a closed loop — every code change goes through PR → review → merge → validate → (on fail) issue → fix-PR; the loop only exits when all phase validators pass. Everything else (schemas, helpers, docs) serves this loop.

**Current Focus**: Phase 1 — Loop Foundation (contracts, schemas, preflight, redactor, additive validator hooks).

**Working Branch**: `refactor/adapt-loop-engineering` (per PROJECT.md).

---

## Current Position

Phase: 01 (loop-foundation-contracts-schemas-safety-plumbing) — EXECUTING
Plan: 3 of 4

- **Milestone**: Adapt Skill Loop-Engineering Refactor (v1)
- **Phase**: Executing
- **Plan**: 02 (complete)
- **Status**: Plan 02 complete (GhClient + Preflight shipped)
- **Progress**: `[##--------] 1/5 phases complete`

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases planned | 5 |
| Phases complete | 0 |
| Requirements mapped | 43/43 |
| Plans created | 0 |
| Plans complete | 0 |

---
| Phase 01 P01 | 6min | 2 tasks | 13 files |
| Phase 01 P02 | 7min | 2 tasks | 8 files |

## Accumulated Context

### Key Decisions (from PROJECT.md)

- Preserve existing Phase 0–5 as inner steps of the new outer loop; do not re-cut phases.
- **Plan 01-01**: Pydantic v2 models use extra='forbid' except PrBlockOutput/IssuesBlockOutput (extra='ignore') for LOG-02 forward-compat.
- **Plan 01-01**: LoopBudget Field ceilings (le=50, le=500, le=10_080) enforce determinism at parse time, preventing loop runaway before controller runs.
- **Plan 01-01**: Redactor uses 10 hardcoded patterns + YAML-configurable internal domains; residual post-check returns accept=False if any pattern survives.
- **Plan 01-02**: GhClient is typing.Protocol (not ABC) for structural typing; FakeGhClient and RealGhClient are independent classes.
- **Plan 01-02**: dry_run=True skips repo_permissions and branch_protection but keeps auth_status and repo_view; tolerates ckpt URL unreachable.
- **Plan 01-02**: Branch protection checks split into hard-fail (approving reviews, restrictions, lock_branch) and warn-only (status_checks, enforce_admins, linear_history).
- PR/issue loop applies only to the two external repos (LoongForge + Loong-Megatron); plugin itself is not part of the loop.
- Validator set frozen: union of existing per-phase validators (`phase1-verify`, `phase2-conversion`, `loss-diff`, `feature-compat`, `kb-consistency`); no unified validator.
- Skip `/gsd:map-codebase`; researcher targets `skills/adapt/` + se.rpcx.io 04/08/12.
- Mode: yolo + coarse + inherit-model + researcher/plan-checker/verifier all on.

### Active TODOs

- [ ] Run `/gsd:plan-phase 1` to decompose Phase 1 into executable plans.

### Blockers

None.

### Open Questions (from research; resolve during planning)

- Default values for `max_attempts_per_phase` (suggest 5) and `max_attempts_per_run` (suggest 25) — confirm during Phase 3 planning.
- Branch protection rules on `Zachary-wW/LoongForge:main` and `Zachary-wW/Loong-Megatron:loong-main/core_v0.15.0` — probe at preflight in Phase 1.
- Auto-merge vs review-required for base PR — likely review-required for default branches, auto for staging branches; confirm in Phase 2.
- Reviewer sub-agent (`adapt-phaseN-diagnose`): reuse issue-loop reviewer from commit `95c916f` verbatim, or fork? — confirm in Phase 3.
- Whether autonomous mode is allowed to merge to default branch directly, or must always go via `staging/run-<id>` — confirm in Phase 3.

---

## Session Continuity

**Last session ended**: 2026-06-22, after plan 01-02 execution.

**Next session should**:

1. Continue with plan 01-03 (CLI) and plan 01-04 (validator hook + lints) in Phase 1.
2. Run Wave-level invariant: `python3 -m pytest skills/adapt/tests/lib/ -x -q` after all Wave 1 plans complete.

**Files of record**:

- `.planning/PROJECT.md` — vision, constraints, decisions
- `.planning/REQUIREMENTS.md` — REQ-IDs (with traceability table)
- `.planning/ROADMAP.md` — 5 phases + success criteria + coverage
- `.planning/STATE.md` — this file
- `.planning/research/{SUMMARY,STACK,ARCHITECTURE,PITFALLS,FEATURES}.md` — research artifacts

---

*Last updated: 2026-06-22 after plan 01-02 execution.*
