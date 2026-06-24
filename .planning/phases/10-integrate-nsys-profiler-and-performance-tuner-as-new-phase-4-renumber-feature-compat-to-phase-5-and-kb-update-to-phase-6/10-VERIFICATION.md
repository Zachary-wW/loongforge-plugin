---
phase: 10-integrate-nsys-profiler-and-performance-tuner-as-new-phase-4-renumber-feature-compat-to-phase-5-and-kb-update-to-phase-6
verified: 2026-06-24T23:15:00Z
status: passed
score: 9/9 must-haves verified
gaps:
  - truth: "All renumbered files contain no stale references to old phase numbering"
    status: resolved
    reason: "All 4 stale prose references fixed in commit 46e06e3"
    artifacts:
      - path: "skills/adapt/references/phases/phase3/agent.md"
        issue: "Line 423: data flow arrow says 'Phase 4 feature_compat_report' — should be 'Phase 5 feature_compat_report'"
      - path: "skills/adapt/references/phases/phase5/feature_matrix.yaml"
        issue: "Lines 1-3: header comment says 'Fixed Phase 4 feature compatibility matrix' and 'Phase 4 must read this file' — should say Phase 5"
      - path: "skills/adapt/references/phases/phase6/agent.md"
        issue: "Line 5: 'after the full adaptation (Phase 0~4) completes' should be 'Phase 0~5'; Line 7: 'dispatched after Phase 4 CHECKPOINT' should be 'Phase 5 CHECKPOINT'"
      - path: "skills/adapt/knowledge_base/sources/source_digest_schema.md"
        issue: "Line 152: table row describes Phase 4 as feature-toggle root-cause lookup — should be Phase 5"
    missing:
      - "Update phase3/agent.md line 423: 'Phase 4 feature_compat_report' -> 'Phase 5 feature_compat_report'"
      - "Update feature_matrix.yaml header: 'Phase 4' -> 'Phase 5' in lines 1-3"
      - "Update phase6/agent.md: 'Phase 0~4' -> 'Phase 0~5' and 'Phase 4 CHECKPOINT' -> 'Phase 5 CHECKPOINT'"
      - "Update source_digest_schema.md line 152: 'Phase 4' feature-toggle row -> 'Phase 5'"
---

# Phase 10: Integrate nsys-profiler and performance-tuner as new Phase 4, renumber Feature Compat to Phase 5 and KB Update to Phase 6 Verification Report

**Phase Goal:** Insert a new Phase 4 (Performance Tuning) between Loss Diff (Phase 3) and Feature Compat (now Phase 5), orchestrating nsys-profiler for profiling and performance-tuner for optimization. Renumber the current Phase 4 (Feature Compat) to Phase 5 and current Phase 5 (KB Update) to Phase 6. Update all code, schemas, validators, and tests to reflect the 7-phase structure.
**Verified:** 2026-06-24T23:15:00Z
**Status:** gaps_found
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | New Phase 4 agent.md describes two-stage performance tuning (profiling then optimization) | VERIFIED | agent.md has NSYS_SKILL_DIR (6 refs), TUNER_SKILL_DIR (4 refs), 13 Step references, 5 gate references, 50 state machine references; 350 lines |
| 2 | Phase 5 agent.md identifies as Phase 5 with references/phases/phase5/ paths | VERIFIED | Header says "Phase 5 Dedicated Agent", 4 references to phases/phase5/, Phase 4 handoff note present |
| 3 | Phase 6 agent.md identifies as Phase 6 with phase4_status in adaptation_status_source | VERIFIED | Header says "Phase 6 Dedicated Agent", phase4_status present, adaptation_status_source present, LOG template has P4/P5 rows |
| 4 | agents/adapt-phase4.md references performance-tuning agent.md | VERIFIED | 1 ref to performance-tuning, 1 ref to NSYS_SKILL_DIR, 2 refs to references/phases/phase4/agent.md |
| 5 | agents/adapt-phase5.md references phase5/agent.md (was feature-compat) | VERIFIED | 1 ref to adapt-phase5, 1 ref to feature-compat, 2 refs to references/phases/phase5/agent.md |
| 6 | agents/adapt-phase6.md references phase6/agent.md (was kb-update) | VERIFIED | 1 ref to adapt-phase6, 1 ref to kb-consistency, 2 refs to references/phases/phase6/agent.md |
| 7 | PHASE_VALIDATORS[4]='performance-tuning', [5]='feature-compat', [6]='kb-consistency'; FLAKE_RERUN_PHASES={3,5} | VERIFIED | Python import + assertion test passed; all values correct |
| 8 | validate_phase_completion.py has phase 4/5/6 checks and range(7); run.py creates 7 phase dirs | VERIFIED | if phase==4 at line 309, if phase==5 at line 363, if phase==6 at line 403; choices=range(7); run.py range(7) at line 220 |
| 9 | All renumbered files contain no stale references to old phase numbering | FAILED | 4 files contain stale 'Phase 4 = Feature Compat' references in prose/comments (see Gaps) |

**Score:** 8/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `skills/adapt/references/phases/phase4/agent.md` | Performance Tuning Phase 4 agent manual | VERIFIED | 350 lines, NSYS_SKILL_DIR + TUNER_SKILL_DIR, 12-step table, 4-gate model, state machine |
| `skills/adapt/references/phases/phase4/phase4_output_schema.yaml` | Phase 4 output schema with performance-tuning validator | VERIFIED | 135 lines, phase: 4, validator.name: performance-tuning, profiling/optimization/acceptance_gates/checks sections |
| `skills/adapt/references/phases/phase4/performance_tuning_gate.md` | Phase 4 gate definition document | VERIFIED | 91 lines, 4-gate model (performance/numerical/memory_stability/scope), staged validation, no-candidate pass |
| `skills/adapt/references/phases/phase5/agent.md` | Feature Compat Phase 5 agent manual (renumbered) | VERIFIED | 30700 bytes, "Phase 5 Dedicated Agent", feature-compat validator, Phase 4 handoff note |
| `skills/adapt/references/phases/phase5/phase5_output_schema.yaml` | Phase 5 output schema | VERIFIED | phase: 5, feature-compat validator, phase4_optimization_report/phase4_best_recipe in source |
| `skills/adapt/references/phases/phase5/feature_matrix.yaml` | Feature matrix (renumbered) | VERIFIED | phase5_builtin pattern, no stale phase4_builtin |
| `skills/adapt/references/phases/phase6/agent.md` | KB Update Phase 6 agent manual (renumbered) | VERIFIED | 23444 bytes, "Phase 6 Dedicated Agent", kb-consistency validator, phase4_status in adaptation_status_source |
| `skills/adapt/references/phases/phase6/phase6_output_schema.yaml` | Phase 6 output schema | VERIFIED | phase: 6, kb-consistency validator, phase4_status + phase5_status |
| `skills/adapt/references/phases/phase6/extraction_rules.yaml` | Extraction rules (renumbered) | VERIFIED | phase4_status + phase5_status present, "Phase 0-5 outputs" updated |
| `skills/adapt/references/phases/phase6/source_templates/` | LLM/VLM/Diffusion templates | VERIFIED | llm.yaml, vlm.yaml, diffusion.yaml present |
| `agents/adapt-phase4.md` | Performance Tuning agent | VERIFIED | performance-tuning, NSYS_SKILL_DIR, references/phases/phase4/agent.md |
| `agents/adapt-phase5.md` | Feature Compat agent | VERIFIED | adapt-phase5, feature-compat, references/phases/phase5/agent.md |
| `agents/adapt-phase6.md` | KB Update agent | VERIFIED | adapt-phase6, kb-consistency, references/phases/phase6/agent.md |
| `skills/adapt/lib/validator_wrapper.py` | PHASE_VALIDATORS 7 entries + FLAKE_RERUN_PHASES={3,5} | VERIFIED | Importable, correct values verified by Python assertion |
| `skills/adapt/scripts/validate_phase_completion.py` | Phase 4/5/6 checks, range(7) | VERIFIED | phase==4 with profiling_evidence_present, phase==5 feature-compat, phase==6 kb-consistency, choices=range(7) |
| `skills/adapt/scripts/run.py` | range(7), schema_version="2", choices include "6" | VERIFIED | range(7) at line 220, schema_version at lines 62/66/241/261/263, "6" in choices |
| `skills/adapt/scripts/phase_loop.py` | range(0, 7) | VERIFIED | choices=range(0, 7) at line 83 |
| `skills/adapt/lib/resume.py` | range(7) | VERIFIED | 1 match |
| `skills/adapt/lib/housekeeping_check.py` | range(7) | VERIFIED | 1 match |
| `skills/adapt/lib/summary_generator.py` | range(7) x2 | VERIFIED | 2 matches |
| `skills/adapt/lib/protected_paths.py` | performance_tuning_gate.md entry | VERIFIED | Pattern present |
| `skills/adapt/SKILL.md` | Seven-phase table | VERIFIED | "seven-phase" present, Phase 4 = "Performance profiling and tuning (nsys-profiler + performance-tuner)" |
| `skills/adapt/knowledge_base/schema/EXIT_CONTRACT.md` | Phase 4/5/6 validator mapping | VERIFIED | performance-tuning at Phase 4, feature-compat at Phase 5, kb-consistency at Phase 6, Phase 4->3 fallback |
| `skills/adapt/lib/schema.py` | schema_version field | VERIFIED | `schema_version: Optional[str] = "2"` in RunInputs |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| phase4/agent.md | loongforge-nsys-profiler | NSYS_SKILL_DIR env var | WIRED | 6 references including script invocations (check_nsys_env.py, veloq_quick_scan.sh, nsys_official_stats.sh) |
| phase4/agent.md | loongforge-performance-tuner | TUNER_SKILL_DIR env var | WIRED | 4 references including script invocations (discover_context.py, compare_loss_gate.py) |
| validator_wrapper.py | validate_phase_completion.py | PHASE_VALIDATORS dict | WIRED | Both files have matching validator names at matching phase numbers |
| run.py | validator_wrapper.py | range(7) matches validator count | WIRED | 6 validators in dict (phases 1-6), run.py creates 7 dirs (phases 0-6) |
| test_validator_wrapper.py | validator_wrapper.py | FLAKE_RERUN_PHASES + PHASE_VALIDATORS assertions | WIRED | Test asserts {3,5} and performance-tuning/feature-compat/kb-consistency at 4/5/6 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| validator_wrapper.py | PHASE_VALIDATORS | Module-level dict literal | N/A (config, not runtime data) | VERIFIED |
| validate_phase_completion.py | phase checks | Conditional branches per phase | N/A (validation logic, not data rendering) | VERIFIED |
| run.py | schema_version | _build_run_inputs() | Written to run_inputs.yml | VERIFIED |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| PHASE_VALIDATORS correct mapping | `python3 -c "from ... import PHASE_VALIDATORS; assert PHASE_VALIDATORS[4]=='performance-tuning'"` | All 3 assertions pass | PASS |
| FLAKE_RERUN_PHASES = {3, 5} | `python3 -c "from ... import FLAKE_RERUN_PHASES; assert FLAKE_RERUN_PHASES == {3,5}"` | Assertion pass | PASS |
| Phase 4 NOT in flake rerun | `should_rerun_for_flake(result, phase=4)` | Returns False | PASS |
| Phase 5 IS in flake rerun | `should_rerun_for_flake(result, phase=5)` | Returns True | PASS |
| Full test suite passes | `python3 -m pytest skills/adapt/tests/ -x -q` | 430 passed | PASS |
| All modified Python files compile | `python3 -m py_compile` on 9 files | All OK | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| PH4-01 | 10-01, 10-02 | New Phase 4 agent + schema | SATISFIED | phase4/agent.md (350 lines), phase4_output_schema.yaml (phase: 4, performance-tuning validator), performance_tuning_gate.md; PHASE_VALIDATORS[4]='performance-tuning'; validate_phase_completion.py if phase==4 block; EXIT_CONTRACT.md Phase 4 row |
| PH4-02 | 10-01, 10-02 | performance-tuning validator | SATISFIED | validator_wrapper.py PHASE_VALIDATORS[4]='performance-tuning'; validate_phase_completion.py profiling_evidence_present + 4-gate checks; phase4_output_schema.yaml validator block; test_validator_wrapper.py test_phase4_no_flake_rerun |
| PH4-03 | 10-02 | FLAKE_RERUN_PHASES update | SATISFIED | FLAKE_RERUN_PHASES = {3, 5} (not {3, 4}); test assertion confirmed; behavioral spot-check passed |
| PH5-RENUM | 10-01, 10-02 | Phase 4 -> 5 renumbering | SATISFIED | phase5/agent.md "Phase 5 Dedicated Agent", phase5_output_schema.yaml phase: 5, feature-compat validator, agents/adapt-phase5.md references phase5/, SKILL.md Phase 5 row, EXIT_CONTRACT.md Phase 5 row, feature_matrix.yaml uses phase5_builtin |
| PH6-RENUM | 10-01, 10-02 | Phase 5 -> 6 renumbering + phase4_status | SATISFIED | phase6/agent.md "Phase 6 Dedicated Agent", phase6_output_schema.yaml phase: 6 with phase4_status + phase5_status, extraction_rules.yaml with phase4_status/phase5_status, agents/adapt-phase6.md, SKILL.md Phase 6 row, EXIT_CONTRACT.md Phase 6 row |
| TEST-UPD | 10-03 | Test updates | SATISFIED | 430 tests pass; test_runner.py range(7); test_plugin_layout.py checks Phase 4/5/6 schemas; test_validator_wrapper.py FLAKE_RERUN_PHASES={3,5}; test_compat.py range(7) + phase=[0-6]; no stale range(6) or phase=[0-5] |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| skills/adapt/references/phases/phase3/agent.md | 423 | Stale "Phase 4 feature_compat_report" in data flow | Warning | Misleading documentation; data flow arrow incorrectly labels Phase 5 as Phase 4 |
| skills/adapt/references/phases/phase5/feature_matrix.yaml | 1-3 | Stale "Fixed Phase 4 feature compatibility matrix" header comment | Warning | Misleading comment; file is used by Phase 5, not Phase 4 |
| skills/adapt/references/phases/phase6/agent.md | 5, 7 | Stale "Phase 0~4" and "Phase 4 CHECKPOINT" | Warning | Misleading documentation; should say "Phase 0~5" and "Phase 5 CHECKPOINT" |
| skills/adapt/knowledge_base/sources/source_digest_schema.md | 152 | Stale "Phase 4" row for feature-toggle root cause | Info | Reference table incorrectly labels feature-toggle as Phase 4 scope |

### Human Verification Required

None required -- all functional behavior verified programmatically. The gaps are documentation accuracy issues that can be verified by grep.

### Gaps Summary

The phase achieved its core goal: a new Phase 4 (Performance Tuning) is fully integrated with two-stage orchestration, 4-gate acceptance model, and all code paths (PHASE_VALIDATORS, validate_phase_completion.py, FLAKE_RERUN_PHASES, SKILL.md, EXIT_CONTRACT.md, schema_version migration) correctly reflect the 7-phase structure. All 430 tests pass.

However, 4 files contain stale prose/comment references that describe "Phase 4" as Feature Compat -- these are remnants of the sed renumbering that only targeted programmatic identifiers (YAML keys, path strings, variable names) but missed natural-language descriptions and comments:

1. **phase3/agent.md line 423**: Data flow arrow says "Phase 4 feature_compat_report" instead of "Phase 5 feature_compat_report"
2. **phase5/feature_matrix.yaml lines 1-3**: Header comment says "Fixed Phase 4 feature compatibility matrix" and "Phase 4 must read this file" instead of Phase 5
3. **phase6/agent.md lines 5, 7**: Says "Phase 0~4 completes" and "Phase 4 CHECKPOINT" instead of "Phase 0~5" and "Phase 5 CHECKPOINT"
4. **source_digest_schema.md line 152**: Feature-toggle root-cause row labeled "Phase 4" instead of "Phase 5"

These are documentation accuracy issues, not functional bugs -- the code paths are all correct. But they could confuse users reading the agent manuals, especially the Phase 6 CHECKPOINT reference which implies the wrong dispatch point.

---

_Verified: 2026-06-24T23:15:00Z_
_Verifier: Claude (gsd-verifier)_
