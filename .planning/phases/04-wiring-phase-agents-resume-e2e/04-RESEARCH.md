# Phase 4: Wiring — Phase Agents, Resume & E2E - Research

**Researched:** 2026-06-22
**Domain:** Integration wiring of loop controller into phase agents, resume remote-state reconciliation, end-to-end testing
**Confidence:** HIGH

## Summary

Phase 4 wires the loop-engineering infrastructure built in Phases 1-3 into the existing phase agents and the `--resume` CLI path, and proves the full cycle works via an end-to-end pytest. The core challenge is that phase agents are Markdown instruction files (not Python modules), so wiring means inserting conditional bullet points into `references/phases/phaseN/agent.md` that activate only when `repos:` is present in `run_inputs.yml`. The resume path currently has no remote-reconciliation logic -- `run.py:resume_run_dir` only clears local `phaseN_output.yml` files and has no concept of GitHub PR/issue state. Phase 4 must add a `reconcile_remote_state()` function that verifies every PR/issue recorded in `loop_state.yml` against `gh` and forces `--reset-phase` on mismatches. The e2e test must exercise a full `fail -> diagnose -> issue -> fix-PR -> review -> merge -> pass` cycle against `FakeGhClient`, proving the FSM works end-to-end without mocking the controller itself (only the validator subprocess).

**Primary recommendation:** Wire hooks as conditional bullet sections in agent.md files (gated on `repos:` presence); add `reconcile_remote_state()` as a standalone Python function in `lib/loop_controller.py` (or new `lib/resume.py`); build the e2e test by composing existing test helpers (`_setup_run_dir`, `_write_loop_state`, `FakeGhClient`, mocked `run_validator`/`check_validator_integrity`) into a single test that runs the full cycle on Phase 1.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COMPAT-01 | Existing `loongforge-adapt <hf_path>` invocation without URL flags continues to produce valid run dir; loop engineering is opt-in via `repos:` presence | Legacy invocation path verified in run.py: main() lines 400-453; `repos` key only added when any URL flag provided; run_inputs.yml v1 schema has `repos: Optional[ReposBlock] = None` in schema.py; existing COMPAT-02/03 already validate legacy acceptance |
| RESUME-01 | `--resume <run_dir> [--from-phase N]` reconstructs FSM state from last `attempts.jsonl` row plus `phaseN_output.yml` | LoopState.from_disk() already reconstructs from loop_state.yml + attempts.jsonl tail; run.py:resume_run_dir currently only clears outputs, needs enhancement to read loop_state.yml and feed it to controller |
| RESUME-02 | On resume, controller reconciles every PR/issue id against `gh`; mismatches force `--reset-phase N` | New function needed: reconcile_remote_state() that calls gh.find_by_idempotency_key or gh API for each PR/issue in loop_state.yml; FakeGhClient already supports find methods; need mismatch classification (404, merge SHA drift, force-push) |
| DOC-03 | Each phase's `references/phases/phaseN/agent.md` updated with two new bullets (pre-edit branch, post-edit PR) gated on `repos:` being present | All 6 agent.md files currently have no loop hooks; insertion points identified: after "Input Contract" section for pre-edit, before "Output Contract" section for post-edit |
| TEST-01 | pytest e2e covering `fail -> diagnose -> issue -> fix-PR -> review -> merge -> pass` on Phase 1 with FakeGhClient | TestFullCycle.test_full_cycle_against_fake_gh_client in test_loop_controller.py already exercises VALIDATE->DIAGNOSE->ISSUE->FIX_PR->REVIEW->MERGE_FIX->RERUN->passed; e2e test adds: init_run_dir, preflight, resume, and output validation via validate_phase_output |
| TEST-04 | Resume test: kill mid-Diagnose, re-invoke with `--resume`, assert no duplicate issue/PR created | TestReEntrant.test_re_entrant_from_disk already proves controller picks up from disk state; need additional test: write loop_state at DIAGNOSE, open issue/PR in FakeGhClient store, resume, verify find_by_idempotency_key returns existing artifact (no duplicate created) |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | Schema validation for run_inputs.yml v2, loop_state.yml | Already in use across Phase 1-3; strict mode catches contract drift |
| pyyaml | (stdlib dep) | YAML read/write for all state files | Existing dependency |
| pytest | 9.0.2 | Test framework | Existing; 330 tests passing |
| jinja2 | 3.1.6 | Template rendering for repair.md and any new agent-bullet templates | Already used in Phase 3 for loop_templates |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock | (stdlib) | Patching run_validator, check_validator_integrity in e2e tests | Only for subprocess-based validator calls; never mock GhClient (use FakeGhClient) |
| hashlib | (stdlib) | Idempotency keys, validator hash | Already used across Phase 2-3 |
| tenacity | (not installed) | Retry for transient gh API errors during resume reconciliation | Optional; only if gh API calls during reconciliation need retry logic |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate resume.py module | Add reconcile logic to run.py | run.py is already 460 lines; separation keeps controller concern in lib/ |
| Adding new Python script for phase dispatch | Enhancing SKILL.md dispatch instructions | Python script would be testable; but SKILL.md dispatch is the established pattern and agent dispatch is model-driven, not code-driven |

**Version verification:**
```bash
python3 -c "import pydantic; print(pydantic.__version__)"  # 2.12.5
python3 -c "import pytest; print(pytest.__version__)"      # 9.0.2
python3 -c "import jinja2; print(jinja2.__version__)"     # 3.1.6
```

## Architecture Patterns

### Recommended Project Structure (additions only)
```
skills/adapt/
  lib/
    resume.py              # NEW: reconcile_remote_state(), reconcile_phase_state()
  scripts/
    run.py                 # MODIFY: --resume enhanced with reconciliation
  references/phases/
    phaseN/agent.md        # MODIFY: add pre-edit/post-edit conditional bullets (N=0..5)
  tests/lib/
    test_loop_e2e.py       # NEW: full e2e cycle test (TEST-01)
    test_resume.py          # NEW: resume reconciliation tests (TEST-04, RESUME-01/02)
```

### Pattern 1: Conditional Phase-Agent Hook Bullets (DOC-03)
**What:** Add two new sections to each `references/phases/phaseN/agent.md` that only activate when `repos:` is present in `run_inputs.yml`
**When to use:** Every phase agent that modifies code on external repos
**Example:**
```markdown
## Loop Engineering Hooks

> These steps apply ONLY when `run_inputs.yml` contains a `repos:` block (loop-engineering mode).
> Skip entirely for legacy invocations.

### Pre-Edit: Branch Creation
Before writing any files to the target repository:
1. Read `run_inputs.yml` and check if `repos:` block is present.
2. If present, invoke `gh_helper.create_branch(owner_repo, branch="adapt/<run_id>/phase<N>/attempt<K>", base=<base_ref>)` on each target repo.
3. Record the branch name in `phases/phaseN/attempts.jsonl` as a `kind="branch"` entry.
4. If branch creation fails (already exists, name conflict), check `gh_helper.find_by_idempotency_key` for an existing artifact and reattach.

### Post-Edit: PR Submission
After writing all phase artifacts and before running the validator:
1. If `repos:` block is present, invoke `gh_helper.open_pr(owner_repo, head=<branch>, base=<base_ref>, ...)` with templated title/body.
2. Record the PR number and URL in `phases/phaseN_output.yml` under the `pr:` block.
3. Merge the base PR via `gh_helper.merge_pr(owner_repo, <pr_number>)` before validator runs (PR-02).
4. If the PR touches protected paths (PR-06), the loop controller will handle escalation.
```

### Pattern 2: Resume Remote-State Reconciliation (RESUME-01/02)
**What:** On `--resume`, verify that every PR and issue referenced in `loop_state.yml` still exists and matches expected state on GitHub
**When to use:** Every `--resume` invocation when `repos:` block is present
**Example:**
```python
# Source: derived from RESUME-02 requirements
from skills.adapt.lib.gh_client import GhClient

class ReconciliationMismatch(Exception):
    """Raised when remote state does not match local records."""
    def __init__(self, mismatches: list[dict]):
        self.mismatches = mismatches
        super().__init__(f"State mismatches: {mismatches}")

def reconcile_remote_state(
    run_dir: Path,
    phase: int,
    gh: GhClient,
    repos_info: dict,
) -> list[dict] | None:
    """Verify every PR/issue in loop_state.yml against gh.
    
    Returns list of mismatches (empty = clean), or None if repos not present.
    Each mismatch has: {artifact_type, number, issue, detail}
    """
    state = LoopState.from_disk(run_dir, phase)
    mismatches = []
    
    # Check PR
    if state.pr_number is not None and repos_info:
        owner_repo = repos_info.get("loongforge_repo", "")
        # Verify PR still exists and state matches
        # If merged_sha in loop_state differs from remote, that's a mismatch
        
    # Check issues
    for issue_num in state.issues_opened:
        # Verify issue still exists and is open
        pass
    
    return mismatches if mismatches else None
```

### Pattern 3: E2E Test Composition (TEST-01)
**What:** A single pytest that exercises the complete FSM cycle on Phase 1 against FakeGhClient
**When to use:** Proving the integrated system works before shipping
**Example:**
```python
# Source: derived from existing TestFullCycle in test_loop_controller.py
def test_e2e_fail_diagnose_issue_fix_pr_merge_pass(tmp_path):
    """TEST-01: full cycle against FakeGhClient on Phase 1."""
    from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
    from skills.adapt.lib.validator_wrapper import ValidatorResult, FailureSignature
    from skills.adapt.lib.diagnose_classifier import DiagnoseResult, DiagnoseClassification
    from skills.adapt.lib.schema import LoopBudget
    
    # 1. Init run_dir via init_run_dir (with repos block)
    # 2. Set up FakeGhClient
    # 3. Run run_phase_loop with mocked validators
    # 4. First call fails, second (after fix) passes
    # 5. Assert: issue opened, PR created, merge called, phase_output valid
    # 6. Assert: validate_phase_output passes on the final output
```

### Anti-Patterns to Avoid
- **Mocking FakeGhClient:** The whole point of FakeGhClient is to be the test double. Only mock the validator subprocess (run_validator, check_validator_integrity).
- **Adding Python dispatch code for phase agents:** Phase dispatch is model-driven via SKILL.md; adding a Python phase-dispatch script breaks the existing architecture (ARCHITECTURE.md Section 1.3).
- **Making hooks unconditional:** Legacy runs MUST skip the new bullets. Gating on `repos:` presence is mandatory (COMPAT-01).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Resume reconciliation | Custom git/GitHub state diff logic | `GhClient.find_by_idempotency_key` + `GhClient.repo_view` + LoopState.from_disk | Phase 2 already built find methods; Phase 3 already built from_disk |
| PR/issue creation during resume | Re-creating PRs that already exist | `find_by_idempotency_key` search-before-create (RESUME-03, already in Phase 2) | Idempotency keys prevent duplicate creation |
| Phase-agent hook gating | Custom Python hooks in agent dispatch | Conditional Markdown sections read by the model agent | The architecture is model-driven; Python code cannot modify agent behavior at runtime |
| E2E test framework | New test harness for FSM integration | Existing `_setup_run_dir`, `_write_loop_state`, `FakeGhClient` | Already proven in 270+ tests; reuse reduces risk |

**Key insight:** Phase 4 is an integration phase, not a new-feature phase. Almost all building blocks exist; the work is wiring them together and adding reconciliation logic.

## Common Pitfalls

### Pitfall 1: Resume Forgets Remote State
**What goes wrong:** `--resume` only clears local files and restarts from Phase N, but the loop controller's PR/issue references become stale if GitHub state changed between crash and resume (someone closed the PR, merge SHA drifted).
**Why it happens:** `resume_run_dir` in run.py only handles local file clearing (lines 255-273); it has no awareness of GitHub state.
**How to avoid:** Add `reconcile_remote_state()` that runs BEFORE `run_phase_loop` on resume. If any mismatch, print diagnostic and require `--reset-phase N` rather than silently proceeding.
**Warning signs:** `--resume` succeeds but the controller re-opens a PR for a branch that already exists and was merged.

### Pitfall 2: Agent Hooks Fire on Legacy Runs
**What goes wrong:** Phase agents try to call `gh_helper.create_branch` on a run that has no `repos:` block, causing a crash or no-op confusion.
**Why it happens:** Adding unconditional "branch then PR" steps to agent.md without a gate check.
**How to avoid:** Every hook bullet MUST start with "If `repos:` is present in `run_inputs.yml`" and have an explicit skip path. COMPAT-01 test verifies legacy runs produce no `pr`/`issues`/`loop` blocks.
**Warning signs:** `loongforge-adapt /tmp/model` (no URL flags) fails with `KeyError: 'repos'` or calls `gh` unexpectedly.

### Pitfall 3: E2E Test Mocks Too Much
**What goes wrong:** The e2e test mocks `GhClient` methods instead of using `FakeGhClient`, or mocks `LoopState.from_disk`, making the test prove nothing about the actual integration.
**Why it happens:** Over-application of `unittest.mock.patch` by reflex.
**How to avoid:** ONLY mock `run_validator` and `check_validator_integrity` (subprocess calls). Use `FakeGhClient` for all gh interactions. Use real `LoopState.from_disk` / `persist`. Use real `_write_phase_output`.
**Warning signs:** Tests pass but the real FSM fails because mocked methods don't match actual behavior.

### Pitfall 4: Resume Creates Duplicate Issues
**What goes wrong:** After a crash mid-DIAGNOSE, the controller already opened issue #7. On resume, it opens issue #8 for the same failure signature.
**Why it happens:** The idempotency-key search path in `open_issue` might not find the existing issue if the search index is stale or the key computation differs.
**How to avoid:** (a) Ensure `find_by_idempotency_key` is called before any `open_issue`/`open_pr` on resume. (b) Ensure `loop_state.yml` records the issue_number, and on resume, `reconcile_remote_state` verifies it. (c) TEST-04 explicitly tests this scenario.
**Warning signs:** After `--resume`, `FakeGhClient._issue_store` contains two entries for the same dedup_key.

### Pitfall 5: Phase-Agent Hook Sections Drift Out of Sync
**What goes wrong:** Six agent.md files each get different wording for the same hook, causing inconsistent behavior.
**Why it happens:** Copy-paste editing across 6 files with manual variation.
**How to avoid:** Write a single canonical hook template (either as a reusable Markdown snippet in a shared file or as a very precise template that is copy-pasted verbatim). Test via a doc-consistency assertion in `test_runner.py` (existing pattern at lines 347-377).
**Warning signs:** grep shows different branch-naming patterns across phase agents.

## Code Examples

Verified patterns from existing codebase:

### Existing Resume Flow (run.py:resume_run_dir)
```python
# Source: skills/adapt/scripts/run.py lines 255-273
def resume_run_dir(run_dir: str, from_phase: int | None = None) -> dict:
    """Load run_inputs.yml, optionally backfill from legacy state, and clear phase outputs from from_phase onward."""
    inputs = load_or_backfill_run_inputs(run_dir)
    if from_phase is not None:
        for phase_num in range(from_phase, 6):
            clear_phase_output(run_dir, phase_num)
        # ... update legacy run_state.json ...
    return inputs
```

### Existing LoopState.from_disk (loop_controller.py)
```python
# Source: skills/adapt/lib/loop_controller.py lines 102-166
@classmethod
def from_disk(cls, run_dir: Path, phase: int) -> "LoopState":
    """Reconstruct state from loop_state.yml + attempts.jsonl tail (P1)."""
    state_path = run_dir / "phases" / f"phase{phase}" / "loop_state.yml"
    if state_path.exists():
        data = yaml.safe_load(state_path.read_text()) or {}
        # ... reconstruct all fields ...
    # Also read tail of attempts.jsonl to update attempt counts
    return state
```

### Existing Full-Cycle Test Pattern
```python
# Source: skills/adapt/tests/lib/test_loop_controller.py lines 914-969
class TestFullCycle:
    def test_full_cycle_against_fake_gh_client(self, tmp_path):
        """Full VALIDATE->DIAGNOSE(CODE_BUG)->ISSUE->FIX_PR->REVIEW->MERGE_FIX->RERUN->passed cycle."""
        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()
        repos_info = {
            "loongforge_repo": "Zachary-wW/LoongForge",
            "loongforge_base_ref": "main",
            "megatron_repo": "Zachary-wW/Loong-Megatron",
            "megatron_ref": "loong-main/core_v0.15.0",
            "run_id": "test-run",
        }
        # First validator call fails, second (rerun) passes
        # ... side_effect pattern, patches, assertions ...
```

### Existing Idempotency Search-Before-Create
```python
# Source: skills/adapt/lib/gh_client.py lines 361-387 (RealGhClient)
def find_by_idempotency_key(self, owner_repo: str, kind: str, key: str) -> Optional[int]:
    """Search for PRs or issues containing the idempotency key (RESUME-03)."""
    if kind == "pr":
        r = self._run(["pr", "list", "-R", owner_repo, "--state", "all",
                       "--search", f"adapt-skill-key: {key}", ...])
    # ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `--resume` only clears local phase outputs | `--resume` must reconcile remote PR/issue state | Phase 4 requirement (RESUME-02) | New reconcile_remote_state function needed |
| Phase agents have no GitHub awareness | Phase agents get conditional pre-edit/post-edit hooks | Phase 4 requirement (DOC-03) | Agent.md modifications gated on repos: |
| No e2e test for full FSM cycle | Full cycle e2e against FakeGhClient | Phase 4 requirement (TEST-01) | New test file test_loop_e2e.py |
| Resume has no crash-resume duplicate prevention | Idempotency keys prevent duplicate creation | Phase 2 (RESUME-03) | Already implemented; Phase 4 proves it works end-to-end |

**Deprecated/outdated:**
- `run.py:resume_run_dir` in its current form (no remote reconciliation) -- must be extended

## Open Questions

1. **Should reconcile_remote_state live in lib/resume.py or lib/loop_controller.py?**
   - What we know: LoopState.from_disk is in loop_controller.py; run.py handles CLI resume
   - What's unclear: Whether separation of concerns favors a new module
   - Recommendation: New `lib/resume.py` -- reconciliation is a resume-time concern, distinct from the FSM dispatch logic. Import LoopState from loop_controller.

2. **What mismatch categories force `--reset-phase` vs. allow silent proceed?**
   - What we know: RESUME-02 says "mismatches force --reset-phase N rather than silent proceed"
   - What's unclear: Whether a closed (auto-closed on fix-merge) issue counts as a mismatch or expected state
   - Recommendation: Auto-closed issues from successful fix-PRs are expected (not mismatches). Mismatches are: PR 404, PR merge SHA drift, force-push detected, issue deleted by human, PR state inconsistent (e.g., closed without merge).

3. **Should the e2e test exercise init_run_dir or start from an existing run_dir?**
   - What we know: The e2e test should prove the whole stack from init to pass
   - What's unclear: Whether init_run_dir with repos: block + FakeGhClient is enough setup
   - Recommendation: Yes, start with init_run_dir (repos block present) to prove COMPAT-01 integration; then feed the run_dir into run_phase_loop.

4. **Where in each agent.md should the hook bullets be inserted?**
   - What we know: Phase agents have sections: Role, State Machine, Input Contract, Execution Steps, Output Contract, Error Handling
   - What's unclear: Exact insertion point varies by phase
   - Recommendation: Add a new "Loop Engineering Hooks" section after "Input Contract" and before "Execution Steps" for all 6 agents. This keeps the gate-check-before-work pattern consistent.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | All | Yes | 3.x | -- |
| pydantic | Schema validation | Yes | 2.12.5 | -- |
| pytest | Testing | Yes | 9.0.2 | -- |
| pyyaml | YAML I/O | Yes | (stdlib dep) | -- |
| jinja2 | Templates | Yes | 3.1.6 | -- |
| gh CLI | Resume reconciliation (RealGhClient) | Yes | 2.87.3 | FakeGhClient for tests |
| git | Branch ops in RealGhClient | Yes | (system) | FakeGhClient for tests |

**Missing dependencies with no fallback:** None

**Missing dependencies with fallback:** None

## Sources

### Primary (HIGH confidence)
- Codebase files: run.py, loop_controller.py, gh_client.py, schema.py, validate_phase_completion.py, diagnose_classifier.py, idempotency.py, templates.py
- All 6 phase agent.md files under references/phases/phase{0..5}/
- Existing test files: test_loop_controller.py, test_gh_client_lifecycle.py, test_runner.py, test_run_cli.py
- REQUIREMENTS.md, ROADMAP.md, PROJECT.md, STATE.md
- Phase 3 RESEARCH.md and PLAN files

### Secondary (MEDIUM confidence)
- ARCHITECTURE.md integration point map (IP-4, IP-5, IP-8)
- CLAUDE.md project constraints

### Tertiary (LOW confidence)
- Budget default values (5/25/240) -- heuristic, tune after real runs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all packages verified installed and tested
- Architecture: HIGH - wiring is integration work with existing components; no new patterns needed
- Pitfalls: HIGH - 4 of 5 pitfalls are derived from actual code gaps found during research
- Resume reconciliation: MEDIUM - the exact mismatch taxonomy needs validation during planning
- E2E test approach: HIGH - existing TestFullCycle proves the pattern works; extension is additive

**Research date:** 2026-06-22
**Valid until:** 2026-07-22 (stable codebase; 30 days)
