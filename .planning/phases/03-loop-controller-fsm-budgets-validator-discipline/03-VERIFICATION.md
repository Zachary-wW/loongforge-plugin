---
phase: 03-loop-controller-fsm-budgets-validator-discipline
verified: 2026-06-22T14:04:05Z
status: passed
score: 13/13 must-haves verified
re_verification: false
---

# Phase 3: Loop Controller FSM, Budgets & Validator Discipline Verification Report

**Phase Goal:** A Python loop controller drives Probe -> Edit -> PR -> Merge(base) -> Validate -> (Diagnose -> Issue -> Fix-PR -> Review -> Merge -> Rerun)* per phase with hard budgets, maker-checker separation, validator-integrity checks, and structured failure signatures -- exiting only on a verifiable validator-pass or a bounded escalation. This is the FSM spine.
**Verified:** 2026-06-22T14:04:05Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

Truths derived from the two PLAN frontmatters' must_haves (Plan 01: 6 truths, Plan 02: 7 truths), combined and deduplicated into 13 distinct truths aligned with ROADMAP success criteria.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | When a validator fails, the system produces a structured failure signature (not just free text) that downstream repair can act on | VERIFIED | `FailureSignature` dataclass in validator_wrapper.py (L50-61) with kind/location/expected/actual fields; `run_validator` extracts from phaseN_output.yml validator block (L117-131); `failure_signature=None` for free-text-only |
| 2 | When a validator passes but the evidence is stale or tampered, the system catches it and blocks the false-positive exit | VERIFIED | `check_validator_integrity` (L189-232) performs 3 checks (binary_hash_ok, log_mtime_ok, log_present); `_validate_loop_evidence` in validate_phase_completion.py (L82-90) rejects passed exits when integrity_ok=False; `_compute_validator_hash` in loop_controller.py (L246-251) records hash at loop start |
| 3 | When Phase 3/4 validators show near-threshold failures, the system automatically reruns before escalating | VERIFIED | `should_rerun_for_flake` (L165-182) returns True for Phase 3/4 with numerical_mismatch/threshold_exceeded kinds; `FLAKE_RERUN_PHASES={3,4}`, `DEFAULT_FLAKE_RERUN_COUNT=3`; VALIDATE state dispatches to RERUN with same attempt number (L483-487) |
| 4 | When LoongForge PR pins a Megatron commit that does not match the actual HEAD, the system refuses validation | VERIFIED | `get_megatron_head_sha` (L239-245) retrieves SHA via gh api; VALIDATE and RERUN states pass megatron_repo/megatron_ref to run_validator (L438-440, L570-572); loong_megatron_sha stored in LoopState (L448-449, L594-595) and last_validator_summary |
| 5 | When failures repeat at the same location 3+ times, the system stops attempting fixes and escalates to the human | VERIFIED | `classify_failure` (L59-135) counts consecutive same kind+location entries from reversed attempts_history (L88-96); returns WRONG_DIRECTION when count>=3 (L97-103); `write_escalation` creates escalation.md (L142-182); loop_controller DIAGNOSE exits HUMAN_NEEDED (L509-515) |
| 6 | The repair prompt template includes an escape-hatch instruction so agents know when to stop retrying | VERIFIED | repair.md (L21-23) has "## Escape Hatch" section with instruction: "If after 3 attempts no progress is observed, write escalation.md and exit human_needed" |
| 7 | A phase loop that starts with a validator failure ends only when the validator passes or the budget is exhausted, never on a hunch | VERIFIED | ExitReason enum has only 2 positive exits (VALIDATOR_PASSED, VALIDATOR_PASSED_AFTER_FIX); all other exits are EXHAUSTED/ESCALATED/BASE_ONLY/HUMAN_NEEDED; budget check at entry (L374), after VALIDATE (L467), after RERUN (L598); Pitfall 2 discipline enforced |
| 8 | When any budget axis is exceeded, the loop exits as exhausted, never as passed | VERIFIED | `check_budget` (L195-214) returns EXHAUSTED for any axis breach; called at entry (L374-381), after VALIDATE (L467-474), after RERUN (L598-605); all budget-breach paths set exit_reason=EXHAUSTED and never passed |
| 9 | Every state transition in the loop produces one auditable row in attempts.jsonl with all required fields | VERIFIED | `_transition` (L226-231) calls `make_attempt_row` and `append_attempt`; make_attempt_row produces all 9 LOG-01 fields (ts, attempt, kind, pr_url, issue_url, validator, verdict, exit_reason, event_id); verified programmatically |
| 10 | After a crash or interrupt, re-running the controller on the same run directory picks up exactly where it left off | VERIFIED | `LoopState.from_disk` (L101-166) reads loop_state.yml + attempts.jsonl tail; `test_re_entrant_from_disk` test exists; 270 total tests pass |
| 11 | When the loop exits validator_passed or validator_passed_after_fix, phaseN_output.yml contains validator_integrity, loop, pr, and issues blocks so validate_phase_completion accepts it | VERIFIED | `_write_phase_output` (L254-311) writes loop_engineering=True, loop, validator_integrity, pr, issues blocks; called on ALL terminal exits (8 call sites verified: L379, L472, L479, L501, L513, L603, L610, L632); EXIT state has safety-net write (L620-633); test_full_cycle_phase_output_passes_validation test confirms |
| 12 | When repos_info includes megatron_repo and megatron_ref, run_validator receives them and loong_megatron_sha is stored | VERIFIED | VALIDATE state (L438-440) and RERUN state (L570-572) extract megatron_repo/megatron_ref from repos_info and pass to run_validator; loong_megatron_sha stored in state (L448-449, L594-595) and last_validator_summary (L463, L591) |
| 13 | validator_hash is computed from the validator binary and passed to check_validator_integrity as recorded_hash | VERIFIED | `_compute_validator_hash` (L246-251) computes sha256[:16]; recorded at first entry (L368-371); passed as recorded_hash to check_validator_integrity in VALIDATE (L443) and RERUN (L575) |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Exists | Substantive | Wired | Status |
|----------|----------|--------|-------------|-------|--------|
| `skills/adapt/lib/validator_wrapper.py` | FailureSignature, ValidatorResult, run_validator, should_rerun_for_flake, check_validator_integrity, get_megatron_head_sha, make_attempt_row | Yes (279 lines) | Yes - all exports present, class FailureSignature at L50 | Yes - imported by diagnose_classifier.py and loop_controller.py | VERIFIED |
| `skills/adapt/lib/diagnose_classifier.py` | DiagnoseClassification, DiagnoseResult, classify_failure, write_escalation | Yes (182 lines) | Yes - 4-member enum, classify_failure with all 4 classification paths, write_escalation with escalation.md format | Yes - imported by loop_controller.py; imports from validator_wrapper.py | VERIFIED |
| `skills/adapt/loop_templates/phaseN/repair.md` | Jinja2 repair prompt template (P6) | Yes (23 lines) | Yes - has {{ phase }}, {{ attempt }}, {{ validator_name }}, {{ failure_kind }}, {{ failure_location }}, {{ expected }}, {{ actual }}, {{ attempts_summary }}, {{ diff_summary }} variables; escape_hatch section | Used as template by future repair agent | VERIFIED |
| `skills/adapt/lib/loop_controller.py` | FSMState, ExitReason, LoopState, check_budget, _compute_validator_hash, _write_phase_output, run_phase_loop | Yes (640 lines) | Yes - 12 FSM states, 6 exit reasons, full match/case dispatch, re-entrant from_disk/persist | Yes - imports from validator_wrapper, diagnose_classifier, gh_client, jsonl, schema; all 5 key links verified | VERIFIED |
| `skills/adapt/scripts/validate_phase_completion.py` | VAL-04 integrity hook in _validate_loop_evidence | Yes (163 lines) | Yes - validator_integrity check at L82-90 | Yes - reads phaseN_output.yml written by loop_controller._write_phase_output | VERIFIED |
| `skills/adapt/tests/lib/test_validator_wrapper.py` | 31 validator wrapper tests | Yes (19370 bytes) | Yes | Yes - all passing | VERIFIED |
| `skills/adapt/tests/lib/test_diagnose_classifier.py` | 19 diagnose classifier tests | Yes (10477 bytes) | Yes | Yes - all passing | VERIFIED |
| `skills/adapt/tests/lib/test_loop_controller.py` | 44 controller tests including full-cycle | Yes (59996 bytes) | Yes - full cycle, budget, re-entrancy, safety tests | Yes - all 107 phase-03 tests passing, 270 total | VERIFIED |
| `skills/adapt/tests/lib/test_validate_loop_evidence.py` | VAL-04 integrity hook tests | Yes (10278 bytes) | Yes - 6 VAL-04 specific tests | Yes - all passing | VERIFIED |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| loop_controller.py | validator_wrapper.py | `from skills.adapt.lib.validator_wrapper import` (L35-38) | WIRED | Imports: ValidatorResult, FailureSignature, run_validator, should_rerun_for_flake, check_validator_integrity, make_attempt_row, DEFAULT_FLAKE_RERUN_COUNT |
| loop_controller.py | diagnose_classifier.py | `from skills.adapt.lib.diagnose_classifier import` (L40-43) | WIRED | Imports: DiagnoseClassification, DiagnoseResult, classify_failure, write_escalation |
| loop_controller.py | gh_client.py | `from skills.adapt.lib.gh_client import GhClient` (L32) | WIRED | GhClient used for PR/issue dispatch in PR, MERGE_BASE, ISSUE, MERGE_FIX states |
| loop_controller.py | jsonl.py | `from skills.adapt.lib.jsonl import append_attempt` (L33) | WIRED | append_attempt called in _transition for LOG-01 writes |
| loop_controller.py | schema.py | `from skills.adapt.lib.schema import LoopBudget, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput` (L34) | WIRED | Used in check_budget and _write_phase_output |
| loop_controller.py | validate_phase_completion.py | _write_phase_output writes phaseN_output.yml consumed by _validate_loop_evidence | WIRED | Data flow: _write_phase_output -> phaseN_output.yml -> _validate_loop_evidence reads validator_integrity, loop blocks |
| diagnose_classifier.py | validator_wrapper.py | `from skills.adapt.lib.validator_wrapper import FailureSignature, ValidatorResult` (L21) | WIRED | Uses FailureSignature and ValidatorResult as input types for classify_failure |
| validate_phase_completion.py | validator_wrapper.py | Dict-based data flow via phaseN_output.yml | WIRED | _validate_loop_evidence reads validator_integrity dict written by _write_phase_output |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| loop_controller.py VALIDATE state | result (ValidatorResult) | run_validator() returns ValidatorResult | Yes - calls loongforge-phase-gate subprocess, parses PASSED/BLOCKED output | FLOWING |
| loop_controller.py DIAGNOSE state | reconstructed_result | _reconstruct_validator_result(last_validator_summary) | Yes - reconstructs from disk-persisted state, not in-memory | FLOWING |
| loop_controller.py _write_phase_output | loop_block, validator_integrity, pr_block, issues_block | LoopState + ValidatorResult | Yes - all blocks populated from live state | FLOWING |
| validate_phase_completion.py _validate_loop_evidence | integrity dict | phaseN_output.yml -> data.get("validator_integrity") | Yes - reads file written by _write_phase_output | FLOWING |
| diagnose_classifier.py classify_failure | validator_output + attempts_history | ValidatorResult + _read_attempts_history() | Yes - reads from attempts.jsonl via _read_attempts_history | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All phase-03 tests pass | `python3 -m pytest skills/adapt/tests/lib/test_validator_wrapper.py skills/adapt/tests/lib/test_diagnose_classifier.py skills/adapt/tests/lib/test_validate_loop_evidence.py skills/adapt/tests/lib/test_loop_controller.py -x -q` | 107 passed in 0.77s | PASS |
| All project tests pass (no regressions) | `python3 -m pytest skills/adapt/tests/lib/ -x -q` | 270 passed in 4.60s | PASS |
| validator_wrapper exports loadable | `python3 -c "from skills.adapt.lib.validator_wrapper import FailureSignature, ValidatorResult, run_validator, should_rerun_for_flake, check_validator_integrity, get_megatron_head_sha, make_attempt_row"` | No error | PASS |
| diagnose_classifier exports loadable | `python3 -c "from skills.adapt.lib.diagnose_classifier import DiagnoseClassification, DiagnoseResult, classify_failure, write_escalation"` | No error | PASS |
| loop_controller exports loadable | `python3 -c "from skills.adapt.lib.loop_controller import FSMState, ExitReason, LoopState, check_budget, _compute_validator_hash, _write_phase_output, run_phase_loop"` | No error | PASS |
| FSMState has 12 members | `python3 -c "from skills.adapt.lib.loop_controller import FSMState; print(len(FSMState))"` | 12 | PASS |
| ExitReason has 6 members with correct values | `python3 -c "from skills.adapt.lib.loop_controller import ExitReason; print([e.value for e in ExitReason])"` | ['validator_passed', 'validator_passed_after_fix', 'exhausted', 'escalated', 'base_only', 'human_needed'] | PASS |
| make_attempt_row produces all 9 LOG-01 fields | Python check: required_fields = {ts, attempt, kind, pr_url, issue_url, validator, verdict, exit_reason, event_id} | All present: True | PASS |
| FLAKE_RERUN_PHASES={3,4}, DEFAULT_FLAKE_RERUN_COUNT=3 | Python check | {3, 4}, 3 | PASS |
| No /loop invocation in controller | `grep -n "/loop" loop_controller.py` | No matches | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOOP-01 | 03-02 | FSM controller drives full Probe->Edit->PR->Merge(base)->Validate->(Diagnose->Issue->Fix-PR->Review->Merge->Rerun)* cycle | SATISFIED | FSMState 12-member enum, run_phase_loop with full match/case dispatch; test_full_cycle_against_fake_gh_client passes |
| LOOP-02 | 03-02 | Validator-pass is the only positive exit; FSM exit reasons enumerated | SATISFIED | ExitReason 6 members: validator_passed, validator_passed_after_fix, exhausted, escalated, base_only, human_needed |
| LOOP-03 | 03-02 | Three-axis termination budget (5/phase, 25/run, 240min wallclock) | SATISFIED | check_budget enforces all three axes; budget-before-validator discipline (Pitfall 2) |
| LOOP-04 | 03-01 | Diagnose step is separate read-only sub-agent (maker != checker, P16) | SATISFIED | diagnose_classifier.py is read-only (no gh calls, no code writing); classify_failure emits 4-class classification |
| LOOP-05 | 03-01 | wrong-direction classification short-circuits to human_needed with escalation.md | SATISFIED | classify_failure counts consecutive same-failure entries; write_escalation creates escalation.md; loop_controller DIAGNOSE exits HUMAN_NEEDED |
| VAL-01 | 03-01 | Validator wrapper calls existing per-phase validators on merged HEAD | SATISFIED | run_validator invokes loongforge-phase-gate subprocess; never rewrites validator logic |
| VAL-02 | 03-01 | Validators emit structured failure_signature; free-text-only -> failure_signature=None | SATISFIED | FailureSignature dataclass; run_validator parses structured failure from phaseN_output.yml; None for free-text |
| VAL-03 | 03-01 | Phase 3/4 near-threshold failures auto-rerun N=3 times | SATISFIED | should_rerun_for_flake gates Phase 3/4 numerical/threshold; DEFAULT_FLAKE_RERUN_COUNT=3; same attempt number |
| VAL-04 | 03-01 | Validator integrity check: binary hash + log mtime + log present | SATISFIED | check_validator_integrity performs 3 checks; _validate_loop_evidence rejects passed when integrity_ok=False; _compute_validator_hash records hash at loop start |
| VAL-05 | 03-01 | Cross-repo coordination: Megatron SHA pinning | SATISFIED | get_megatron_head_sha via gh api; VALIDATE and RERUN states pass megatron_repo/megatron_ref to run_validator; loong_megatron_sha stored in LoopState |
| LOG-01 | 03-02 | Every loop transition appends one row to attempts.jsonl with all required fields | SATISFIED | _transition calls append_attempt(make_attempt_row(...)); 9 fields verified programmatically: ts, attempt, kind, pr_url, issue_url, validator, verdict, exit_reason, event_id |

No orphaned requirements found -- all 11 Phase-3-mapped REQ-IDs (LOOP-01..05, VAL-01..05, LOG-01) are covered by at least one plan and verified against code.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| loop_controller.py | 164 | `pass` in except block | Info | Legitimate exception suppression for corrupted JSONL read -- graceful fallback to defaults |
| loop_controller.py | 541 | `pass` in except block | Info | Legitimate exception suppression for PR number parsing -- non-critical |
| loop_controller.py | 630 | `pass` in except block | Info | Legitimate exception suppression for YAML read in safety-net check -- fallback to needs_write=True |

No blocker or warning anti-patterns found. All `pass` statements are in legitimate exception-handling blocks, not stub implementations.

### Human Verification Required

| # | Test | Expected | Why Human |
|---|------|----------|-----------|
| 1 | Full cycle with real loongforge-phase-gate binary | Controller should drive actual validator subprocess and correctly parse PASSED/BLOCKED output | Requires actual validator binary and GPU environment; tests mock subprocess |
| 2 | Re-entrancy after actual process kill | Controller should resume from disk state without data loss | Cannot programmatically simulate real process crash with partial writes |
| 3 | Megatron SHA pinning with live gh api | get_megatron_head_sha should resolve actual SHA from GitHub | Requires live gh auth and network access; tests use FakeGhClient |

These are all Phase 4+ concerns (wiring and e2e), not blockers for the FSM spine deliverable.

### Gaps Summary

No gaps found. All 13 observable truths verified against the codebase with positive evidence:

- FSM controller (640 lines) implements the full 12-state dispatch cycle with recursive match/case architecture
- Budget enforcement is strict: check_budget called at entry, after VALIDATE, and after RERUN; always returns EXHAUSTED on breach, never passed
- Maker-checker separation is structural: diagnose_classifier.py is read-only, imports from but never modifies validator_wrapper.py
- Validator integrity is end-to-end wired: _compute_validator_hash records at loop start -> check_validator_integrity verifies with recorded_hash -> _validate_loop_evidence rejects passed exits when integrity fails
- _write_phase_output is called on ALL 8 terminal exit paths, ensuring the VAL-04 hook always has data
- 270 total tests pass (107 new for phase 03), 9 commit hashes verified in git log

---

_Verified: 2026-06-22T14:04:05Z_
_Verifier: Claude (gsd-verifier)_
