---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-06-22T10:58:14.083Z"
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 6
  completed_plans: 6
---

# STATE.md — Adapt Skill Loop-Engineering Refactor

> Project memory. Updated at phase transitions, plan completions, and major decisions.

---

## Project Reference

**What This Is**: Refactor `loongforge-plugin/skills/adapt` from a 6-phase HF→LoongForge adaptation skill (whose retries are local, phase-internal) into an explicit loop-engineering workflow where every code change goes through a `Probe → Edit → PR → Merge(base) → Validate → (Diagnose → Issue → Fix-PR → Review → Merge → Rerun)*` cycle against two external GitHub repos (`Zachary-wW/LoongForge` and `Zachary-wW/Loong-Megatron`). Validators are the single source of truth for loop exit.

**Core Value**: The adaptation process MUST be a closed loop — every code change goes through PR → review → merge → validate → (on fail) issue → fix-PR; the loop only exits when all phase validators pass. Everything else (schemas, helpers, docs) serves this loop.

**Current Focus**: Phase 2 complete — ready for Phase 3 (loop controller).

**Working Branch**: `refactor/adapt-loop-engineering` (per PROJECT.md).

---

## Current Position

Phase: 02 (github-helpers-pr-issue-lifecycle) — COMPLETE
Plan: 2 of 2 (both plans complete)

- **Milestone**: Adapt Skill Loop-Engineering Refactor (v1)
- **Phase**: Complete
- **Plan**: Both plans complete (idempotency + templates + lifecycle methods + state machine)
- **Status**: Phase 2 fully complete, ready for Phase 3
- **Progress**: `[==--------] 2/5 phases, 6/6 plans complete`

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases planned | 5 |
| Phases complete | 0 |
| Requirements mapped | 43/43 |
| Plans created | 4 |
| Plans complete | 4 |

---
| Phase 01 P01 | 6min | 2 tasks | 13 files |
| Phase 01 P02 | 7min | 2 tasks | 8 files |
| Phase 01 P03 | 6min | 1 tasks | 2 files |
| Phase 01 P04 | 3min | 2 tasks | 4 files |
| Phase 02 P01 | 6min | 2 tasks | 4 files |
| Phase 02 P02 | 7min | 3 tasks | 2 files |

## Accumulated Context

### Key Decisions (from PROJECT.md)

- Preserve existing Phase 0–5 as inner steps of the new outer loop; do not re-cut phases.
- **Plan 01-01**: Pydantic v2 models use extra='forbid' except PrBlockOutput/IssuesBlockOutput (extra='ignore') for LOG-02 forward-compat.
- **Plan 01-01**: LoopBudget Field ceilings (le=50, le=500, le=10_080) enforce determinism at parse time, preventing loop runaway before controller runs.
- **Plan 01-01**: Redactor uses 10 hardcoded patterns + YAML-configurable internal domains; residual post-check returns accept=False if any pattern survives.
- **Plan 01-02**: GhClient is typing.Protocol (not ABC) for structural typing; FakeGhClient and RealGhClient are independent classes.
- **Plan 01-02**: dry_run=True skips repo_permissions and branch_protection but keeps auth_status and repo_view; tolerates ckpt URL unreachable.
- **Plan 01-02**: Branch protection checks split into hard-fail (approving reviews, restrictions, lock_branch) and warn-only (status_checks, enforce_admins, linear_history).
- **Plan 01-03**: 8 explicit per-field CLI flags instead of combined URL@ref:subpath syntax (shell quoting of @/: is fragile).
- **Plan 01-03**: All-or-nothing URL validation post-parse (not argparse required=) to keep legacy positional hf_path working alone.
- **Plan 01-03**: Module-level imports of run_preflight/FakeGhClient/RealGhClient for monkey-patchability (W5).
- **Plan 01-04**: LoopBlockOutput import kept local (inside _validate_loop_evidence) so legacy code path never loads pydantic.
- **Plan 01-04**: First /loop lint regex tightened to ^/loop\b (line-start) to avoid false-flagging SKILL.md prose.
- **Plan 02-01**: Visible [adapt-skill-key: hex] fallback line before HTML comment addresses GitHub search indexing uncertainty for HTML comments.
- **Plan 02-01**: Idempotency key and dedup key use different input tuples and serve different purposes -- must never be conflated (run_id:phase:attempt:action_kind vs phase:validator:kind:location).
- **Plan 02-02**: Protocol signatures for open_pr/open_issue changed to template-driven params; callers cannot bypass template constraints.
- **Plan 02-02**: find_by_dedup_key and find_by_idempotency_key are separate methods: dedup key for cross-attempt issue dedup, idempotency key for crash-resume.
- **Plan 02-02**: Human commit detection uses git log --format=%ae per D-01; open_pr posts /agent-resume comment on existing PR before raising HumanCommitError.
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

**Last session ended**: 2026-06-22, after Phase 2 Plan 02 complete (lifecycle methods + state machine).

**Next session should**:

1. Execute Phase 3 (loop controller) after running `/gsd:plan-phase 3`.
2. Run invariant: `python3 -m pytest skills/adapt/tests/lib/ -x -q` (170 tests should pass).

**Files of record**:

- `.planning/PROJECT.md` — vision, constraints, decisions
- `.planning/REQUIREMENTS.md` — REQ-IDs (with traceability table)
- `.planning/ROADMAP.md` — 5 phases + success criteria + coverage
- `.planning/STATE.md` — this file
- `.planning/research/{SUMMARY,STACK,ARCHITECTURE,PITFALLS,FEATURES}.md` — research artifacts

---

*Last updated: 2026-06-22 after Phase 2 Plan 02 complete.*
