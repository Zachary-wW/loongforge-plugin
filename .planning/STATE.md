---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-06-24T14:48:09.340Z"
progress:
  total_phases: 10
  completed_phases: 8
  total_plans: 26
  completed_plans: 24
---

# STATE.md — Adapt Skill Loop-Engineering Refactor

> Project memory. Updated at phase transitions, plan completions, and major decisions.

---

## Project Reference

**What This Is**: Refactor `loongforge-plugin/skills/adapt` from a 6-phase HF→LoongForge adaptation skill (whose retries are local, phase-internal) into an explicit loop-engineering workflow where every code change goes through a `Probe → Edit → PR → Merge(base) → Validate → (Diagnose → Issue → Fix-PR → Review → Merge → Rerun)*` cycle against two external GitHub repos (`Zachary-wW/LoongForge` and `Zachary-wW/Loong-Megatron`). Validators are the single source of truth for loop exit.

**Core Value**: The adaptation process MUST be a closed loop — every code change goes through PR → review → merge → validate → (on fail) issue → fix-PR; the loop only exits when all phase validators pass. Everything else (schemas, helpers, docs) serves this loop.

**Current Focus**: Phase 7 Plan 3 complete — all Phase 7 plans executed, phase ready for verification.

**Working Branch**: `refactor/adapt-loop-engineering` (per PROJECT.md).

---

## Current Position

Phase: 10 (integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6) — EXECUTING
Plan: 3 of 3

- **Milestone**: Adapt Skill Loop-Engineering Refactor (v1)
- **Phase**: 08 - Phase 2+3 Redesign
- **Status**: Plan 01 complete, Plan 02 next (Phase 3 agent.md rewrite)
- **Progress**: `[█████████░] 87%, 20/23 plans complete`

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
| Phase 03 P01 | 7 | 3 tasks | 6 files |
| Phase 03 P02 | 9 | 2 tasks | 2 files |
| Phase 04 P01 | 9min | 2 tasks | 6 files |
| Phase 04 P02 | 16min | 2 tasks | 9 files |
| Phase 05 P01 | 4min | 2 tasks | 2 files |
| Phase 05 P02 | 371s | 2 tasks | 6 files |
| Phase 06-phase0-redesign P02 | 8min | 2 tasks | 5 files |
| Phase 06 P01 | 12min | 2 tasks | 6 files |
| Phase 06-phase0-redesign P03 | 686s | 2 tasks | 7 files |
| Phase 07-phase1-redesign P02 | 5min | 2 tasks | 3 files |
| Phase 07 P01 | 7min | 2 tasks | 2 files |
| Phase 07-phase1-redesign P03 | 2min | 2 tasks | 2 files |
| Phase 09 P01 | 2min | 2 tasks | 3 files |
| Phase 08 P01 | 4min | 2 tasks | 2 files |
| Phase 08 P02 | 4min | 2 tasks | 2 files |
| Phase 09 P02 | 5min | 2 tasks | 7 files |
| Phase 10 P01 | 12min | 3 tasks | 12 files |
| Phase 10 P02 | 7min | 3 tasks | 11 files |

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
- **Plan 03-01**: FakeGhClient._run added with _sha_store for simulated SHA lookups.
- **Plan 03-01**: FailureSignature/ValidatorResult use @dataclass not Pydantic per RESEARCH: internal-only models.
- **Plan 03-01**: classify_failure counts consecutive same-kind+location from tail of attempts_history (reversed).
- **Plan 04-01**: Force-push detection subsumed by SHA drift check; dedicated force_push mismatch type reserved for v1 when commit-author timestamps are available.
- **Plan 04-01**: reconcile_remote_state only checks loongforge_repo (both PRs and issues opened there); megatron_repo not reconciled.
- **Plan 04-02**: FIX_PR state creates fix-PR branch + open_pr with kind="fix" and fixes_issue linkage (ISSUE-02); MERGE_FIX merges fix-PR (fix_pr_number) not base PR.
- **Plan 04-02**: fix_pr_number is a separate LoopState field from pr_number to track two distinct PRs in the cycle.
- **Plan 04-02**: Test repos use non-default staging base_ref to satisfy PR-01 (create_branch refuses default branch base).
- **Plan 04-01**: Reconciliation skipped when --from-phase specified (explicit reset takes precedence over stale state detection).
- **Plan 06-01**: HfAnalysis uses ConfigDict(extra='forbid') consistent with existing schema.py pattern; all model_spec_llm.yaml fields preserved.
- **Plan 06-01**: BridgeMapping.component_bridge.megatron uses Optional[List[str]] (null for gaps) per D-09.
- **Plan 06-01**: BridgeMapping absorbs reference_contract.yml fields (implementation_contract, conversion_requirements, phase3_reference_requirements) as Optional[Dict[str,Any]] for forward-compat per D-05.
- **Plan 06-01**: ReferenceEntry model uses string-typed fields (type, priority, trust_level) rather than Literal enums for reference_contract_schema.yaml compat.
- **Plan 06-01**: Phase 0 quality inner loop uses max 3 rounds (per D-15), not the 12-state Loop FSM.
- **Plan 06-03**: Phase 0 validation gate replaces model_spec_exists with three-document checks (hf_analysis_exists, reference_impl_analysis_exists, bridge_mapping_exists, bridge_mapping_component_bridge_non_empty, bridge_mapping_gaps_have_guidance); Phase 1/2 use bridge_mapping_path as primary input with model_spec_path as deprecated fallback.
- **Plan 07-02**: Shared-seed initialization tightens tolerance from 1e-2 to 1e-3 (identical params eliminate init noise); gap components (weight_map=null) skipped during parameter mapping with explicit report.
- **Plan 07-02**: All perf rules P1-P8 are violation_severity: blocking per D-03; HF Sanity Run is separate Step 0B for early failure detection; PHASE1_VERIFY hook fixes all four input tensors.
- **Plan 07-01**: Phase 1 agent.md uses bridge_mapping_path as PRIMARY input; model_spec_path is legacy fallback only (per D-09).
- **Plan 07-01**: Step 2c depth gated by confidence level: high skips, medium simplified, low full, gap goes to Step 2d (per D-07).
- **Plan 07-01**: Step 2d designs Megatron gap modules for megatron=null components; Step 3 generates code for both LoongForge and Megatron repos (per D-01).
- **Plan 07-01**: perf_lint_executed field in output contract completes validation chain: agent.md -> phase1_output_schema.yaml -> validate_phase_completion.py.
- **Plan 07-03**: Phase 1 validation checks are conditional (if X is not None) for backward compatibility with legacy runs; bridge_mapping consumption helper verifies file exists and component_bridge non-empty; valid Megatron prefixes: megatron/ and loongforge/models/common/experimental_attention_variant/.
- **Plan 07-03**: megatron_preread_checklist.yaml v2 adds confidence_driven_reading section (high/medium/low/gap) delegating component-specific reading to reference_impl_analysis.yaml; assembly-flow sources marked always_required.
- **Plan 08-01**: Phase 2 agent.md uses bridge_mapping_path as PRIMARY input for weight mapping; model_spec_path is legacy fallback only (per D-01).
- **Plan 08-01**: Phase 2 reads generated_loongforge_files + generated_megatron_files from Phase 1 output; generated_files is LEGACY fallback (per D-02).
- **Plan 08-01**: Phase 2 Step 0 reads bridge_mapping.conversion_requirements; reference_contract_path is DEPRECATED, absorbed into bridge_mapping (per D-03).
- **Plan 08-01**: Phase 2 Step 1 uses bridge_mapping.component_bridge[].weight_map as AUTHORITATIVE name map; source discovery overrides on conflict.
- **Plan 08-01**: phase2_output_schema.yaml adds source.bridge_mapping_path, checks.bridge_mapping_consumed, artifacts.generated_megatron_files.

### Roadmap Evolution

- Phase 10 added: Integrate nsys-profiler and performance-tuner as new Phase 4, renumber Feature Compat to Phase 5 and KB Update to Phase 6

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

**Last session ended**: 2026-06-24, after Phase 8 Plan 01 complete. Stopped at: Completed 08-01-PLAN.md.

**Next session should**:

1. Execute Phase 8 Plan 02: Rewrite Phase 3 agent.md with bridge_mapping consumption.
2. Execute Phase 8 Plan 03: Update validate_phase_completion.py with Phase 2+3 checks.
3. Verify Phase 8 consistency across all modified files.

**Files of record**:

- `.planning/PROJECT.md` — vision, constraints, decisions
- `.planning/REQUIREMENTS.md` — REQ-IDs (with traceability table)
- `.planning/ROADMAP.md` — 5 phases + success criteria + coverage
- `.planning/STATE.md` — this file
- `.planning/research/{SUMMARY,STACK,ARCHITECTURE,PITFALLS,FEATURES}.md` — research artifacts

---

*Last updated: 2026-06-24 after Phase 8 Plan 01 complete.*
