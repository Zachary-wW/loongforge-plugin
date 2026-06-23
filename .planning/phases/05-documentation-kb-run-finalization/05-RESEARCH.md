# Phase 5: Documentation, KB & Run Finalization - Research

**Researched:** 2026-06-23
**Domain:** Documentation authoring, run finalization, acceptance handoff
**Confidence:** HIGH

## Summary

Phase 5 is a documentation-and-finalization phase with no new runtime behavior or FSM states. It covers six requirements (DOC-01, DOC-02, DOC-04, ACC-01, ACC-02, ACC-03) that make the loop-engineering refactor self-describing and ready for GPU-handoff. The implementation work is primarily Markdown file creation/rewrite, one Python helper for comprehension_summary generation, and two acceptance artifacts.

The existing codebase provides all source material: `loop_controller.py` (12-state FSM, ExitReason, LoopState), `diagnose_classifier.py` (maker-checker split), `validator_wrapper.py` (integrity checks, flake rerun), `resume.py` (reconciliation), `schema.py` (LoopBudget, ReposBlock), `run.py` (CLI entry), and `gh_client.py` (Protocol, FakeGhClient, RealGhClient). The SKILL.md currently describes the legacy 6-phase workflow without loop-engineering framing. The new `references/loop_engineering/` and `references/acceptance/` directories do not exist yet. The `.planning/HANDOFF.md` file does not exist yet.

**Primary recommendation:** Write documentation that is surgically grafted onto the existing structure: preserve SKILL.md mechanics sections (D-01), add loop-first architecture framing, create loop_engineering/README.md with P1-P21 principle-to-implementation mapping, generate comprehension_summary from existing disk state (loop_state.yml + attempts.jsonl), and produce two handoff artifacts (ds_v4_runbook.md + HANDOFF.md). ACC-01 requires no new code -- 371 green tests plus test_loop_e2e.py already prove the full FSM cycle against FakeGhClient.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Preserve existing "how each phase runs" sections in SKILL.md (Reading Order, Phase Dispatch Rules, Checkpoint Protocol, Bulk Log Externalization, Autonomous Mode). Rewrite the top-level framing to surface the loop-first architecture: 12-state FSM, repos: gated behavior, maker-checker split, three-axis budget, GitHub as coordination bus, "When NOT to use" guard. The rewrite is surgical: keep phase mechanics, replace architecture framing.
- **D-02:** Medium depth for comprehension_summary.md: commit list + FSM path summary (states visited, attempt count per phase, which validator failed/passed). Derivable from disk state (loop_state.yml + attempts.jsonl). Per-phase phaseN_summary.md follows same template: phase number, validator outcome, attempts count, key decision log.
- **D-03:** ACC-01 met by: (a) all pytest green (311+ tests already prove full FSM cycle against FakeGhClient), (b) test_loop_e2e.py IS the proof. Adding a separate dry-run integration test is redundant. No code changes needed to validator_wrapper.py for ACC-01.
- **D-04:** DS V4 runbook is a narrative document with structured invocation command + expected output + pass criteria. Community-version diff target URL left as TODO placeholder. Known URLs: HF impl transformers/models/deepseek_v4, ckpt deepseek-ai/DeepSeek-V4-Flash-Base, LoongForge Zachary-wW/LoongForge, Loong-Megatron Zachary-wW/Loong-Megatron branch loong-main/core_v0.15.0.
- **D-05:** The user has drafted docs/loop-engineering-in-practice.md -- a three-layer loop framing (Inner: phase-internal self-repair, Middle: GitHub PR/issue cycle, Outer: multi-model replay). Content should be integrated into DOC-01 (SKILL.md) framing and DOC-02 (loop_engineering/README.md). The doc is NOT yet on disk -- treat user's shared content as canonical.

### Claude's Discretion
- Exact SKILL.md section ordering and heading names
- Template strings for comprehension_summary.md and phaseN_summary.md
- Label color schemes for bot PRs/issues (already established in Phase 2)
- HANDOFF.md formatting and env var naming
- Whether to create docs/loop-engineering-in-practice.md as a separate file or merge its content entirely into SKILL.md + loop_engineering/README.md

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DOC-01 | SKILL.md rewritten to describe the loop FSM, the four user inputs, the maker-checker split, termination budgets, and the "When NOT to use this loop" guard | D-01 prescribes surgical rewrite; existing SKILL.md 164 lines with preserved sections identified; loop_controller.py provides FSM states/ExitReason; schema.py provides ReposBlock/LoopBudget; diagnose_classifier.py provides maker-checker split |
| DOC-02 | New loop_engineering/README.md cites se.rpcx.io/04, /08, /12 and maps each principle P1-P21 to implementation | STACK.md Part 1 has complete P1-P21 table with Application column; CLAUDE.md lines 8-120 have identical mapping; source URLs verified as 404 (content preserved in repo); D-05 three-layer loop framing integrates here |
| DOC-04 | End-of-run mandatory phaseN_summary.md plus per-run comprehension_summary.md (1 page) listing merged commits and one-line rationale | D-02 prescribes medium depth; loop_state.yml + attempts.jsonl are data sources; loop_controller.py LoopState.from_disk + jsonl.py provide read helpers; decision_log.md if exists per phase |
| ACC-01 | Local milestone exit criterion: all pytest green + loongforge-adapt --dry-run drives full FSM against FakeGhClient | D-03: 371 tests green (as of Phase 4); test_loop_e2e.py covers full fail->diagnose->issue->fix-PR->merge->pass cycle; test_compat.py covers legacy invocation; no new code needed |
| ACC-02 | ds_v4_runbook.md captures GPU-machine invocation for DS V4 acceptance | D-04 prescribes narrative format with structured command + pass criteria; known URLs from PROJECT.md; community diff target as TODO placeholder |
| ACC-03 | .planning/HANDOFF.md lists what to copy to GPU box and how to resume there | New file at .planning/HANDOFF.md; --resume semantics documented in run.py; env vars/ckpt path expectations to enumerate |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyYAML | >=6.0 | Read loop_state.yml, phaseN_output.yml for summary generation | Already in project; used by loop_controller.py and run.py |
| Python stdlib | 3.12+ | File I/O, Path, datetime for summary generation | Project constraint: no new languages/services |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Jinja2 | >=3.1,<4 | Template rendering for comprehension_summary.md and phaseN_summary.md | CONTEXT.md Claude's discretion area; could also use f-strings for simpler templates |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Jinja2 templates for summaries | f-string templates in Python helper | Jinja2 is already listed in STACK.md Part 2 as the tool for loop_templates; consistent to reuse. But f-strings are simpler for the 1-page summary and avoid a dependency. Use f-strings for Phase 5 summaries (simpler, fewer deps); Jinja2 is for loop repair templates (Phase 3 concern). |

**Installation:**
No new packages required. PyYAML and Python stdlib already in project.

## Architecture Patterns

### Recommended Project Structure
```
skills/adapt/
  SKILL.md                          # DOC-01: surgical rewrite
  references/
    loop_engineering/
      README.md                     # DOC-02: new file, P1-P21 mapping
    acceptance/
      ds_v4_runbook.md              # ACC-02: new file
  lib/
    summary_generator.py            # DOC-04: new helper (optional, Claude's discretion)
  knowledge_base/
    INDEX.md                        # May need loop_engineering reference added
    LOG.md                          # Append-only event log (pattern for summary timestamps)

.planning/
  HANDOFF.md                        # ACC-03: new file

<run_dir>/phases/
  phaseN_summary.md                 # DOC-04: per-phase summary (generated per run)
  comprehension_summary.md          # DOC-04: per-run 1-page summary (generated per run)
```

### Pattern 1: Surgical SKILL.md Rewrite (D-01)
**What:** Keep existing mechanics sections verbatim, replace top-level architecture framing with loop-first description.
**When to use:** DOC-01 rewrite
**Example:**
```markdown
# /loongforge:adapt -- LoongForge Model Adaptation

## Loop-First Architecture

When `repos:` is present in `run_inputs.yml`, the skill operates as a loop-engineering
system: every code change goes through a closed loop on external GitHub repos
until all phase validators pass.

### Three Nested Loops

| Layer | Scope | Coordination Bus |
|-------|-------|-------------------|
| Inner | Phase-internal self-repair (attempts.jsonl) | Disk files |
| Middle | GitHub PR/issue cycle (loop controller) | GitHub (`gh` CLI) |
| Outer | Multi-model replay (future) | Run directory |

### 12-State FSM

PROBE -> EDIT -> PR -> MERGE_BASE -> VALIDATE
  -> (DIAGNOSE -> ISSUE -> FIX_PR -> REVIEW -> MERGE_FIX -> RERUN)*
  -> EXIT

### When NOT to Use This Loop

- Trivial fixes (one-line config changes with known validators that always pass)
- No validator exists for the target phase
- Single-run, no-replay scenarios where manual commit-and-push suffices

## Reading Order       <!-- preserved from existing -->
...
## Phase Dispatch Rules <!-- preserved from existing -->
...
```

### Pattern 2: Principle-to-Implementation Mapping (DOC-02)
**What:** For each P1-P21, cite the principle, quote the source, and point to the concrete file/function that implements it.
**When to use:** loop_engineering/README.md creation
**Example:**
```markdown
### P1: "State lives on disk, not in context"
**Source:** se.rpcx.io/04 (Ralph Loop)
**Implementation:** `lib/loop_controller.py` -- `LoopState.from_disk(run_dir, phase)` reconstructs
FSM state from `loop_state.yml` + `attempts.jsonl` tail on every invocation; no in-memory
conversation state persists across iterations.
```

### Pattern 3: Comprehension Summary Generation (DOC-04)
**What:** Python helper or template reads loop_state.yml + attempts.jsonl per phase, produces markdown summaries.
**When to use:** End-of-run comprehension_summary.md
**Example:**
```python
# Pseudocode for summary generation (derivable from existing helpers)
from skills.adapt.lib.loop_controller import LoopState
from skills.adapt.lib.jsonl import read_jsonl  # or inline file read

def generate_comprehension_summary(run_dir: Path) -> str:
    """Generate 1-page comprehension_summary.md from disk state."""
    phases_run = []
    for phase in range(6):
        state = LoopState.from_disk(run_dir, phase)
        if state.attempt > 1 or state.exit_reason is not None:
            phases_run.append({
                "phase": phase,
                "attempts": state.attempt,
                "exit_reason": state.exit_reason.value if state.exit_reason else "in_progress",
                "states_visited": _extract_states_from_attempts(run_dir, phase),
                "validator": state.last_validator_summary,
            })
    # Format as markdown table + commit list
    ...
```

### Anti-Patterns to Avoid
- **Rewriting SKILL.md from scratch (violates D-01):** The existing mechanics sections (Reading Order, Phase Dispatch, Checkpoint Protocol, Bulk Log Externalization, Autonomous Mode) describe behavior that has not changed. Replacing them risks losing precision and introducing inconsistencies with the actual implementation.
- **Making comprehension_summary.md too narrative:** D-02 explicitly warns that richer narrative ("what was wrong and how fixed") risks exceeding 1-page limit for multi-phase runs. Stick to: commit list + FSM path summary + attempt counts.
- **Writing new acceptance tests for ACC-01:** D-03 declares the existing 371-test suite plus test_loop_e2e.py as sufficient proof. Adding redundant tests wastes effort.
- **Hardcoding community-repo URL in ds_v4_runbook.md:** D-04 says leave as TODO placeholder; user will fill in when available.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Summary data reading | Custom YAML/JSONL parser | `LoopState.from_disk()` + `jsonl.append_attempt()` patterns | loop_controller.py already implements disk reconstruction; reuse its reading logic |
| Principle mapping content | Write P1-P21 from memory | Copy from STACK.md Part 1 table + CLAUDE.md lines 8-120 | The mapping was already researched and validated in earlier phases; do not re-derive |
| Exit reason enumeration | Re-describe in docs | Reference `ExitReason` enum from loop_controller.py | Code is the source of truth; docs must cite it |
| FSM state list | Manually enumerate in README | Reference `FSMState` enum from loop_controller.py | Same; docs derive from code, not vice versa |

**Key insight:** This phase is documentation-only with one optional Python helper. The "don't hand-roll" principle means: derive doc content from existing code and research artifacts, not from re-investigation or memory.

## Common Pitfalls

### Pitfall 1: SKILL.md Rewrite Scope Creep
**What goes wrong:** Rewriting more of SKILL.md than D-01 allows, causing inconsistencies with existing behavior.
**Why it happens:** It is tempting to "improve" mechanics sections while rewriting architecture framing.
**How to avoid:** Keep a strict list of preserved sections; diff the rewrite against original to verify only framing changed.
**Warning signs:** Post-rewrite SKILL.md describes behavior that differs from what loop_controller.py implements.

### Pitfall 2: comprehension_summary Exceeds 1-Page Limit
**What goes wrong:** Multi-phase runs with many attempts produce verbose summaries that no one reads.
**Why it happens:** Including full decision logs, error messages, or diff summaries per attempt.
**How to avoid:** D-02 prescribes medium depth: commit list + FSM path summary (states visited, attempt count per phase, which validator failed/passed). Per-phase summaries follow the same template. Maximum 1 page.
**Warning signs:** Summary exceeds ~60 lines for a 6-phase run.

### Pitfall 3: DOC-02 Content Drift From Code
**What goes wrong:** The P1-P21 mapping references code that has been refactored or renamed since the doc was written.
**Why it happens:** Documentation written at the end of a project can reference intermediate artifacts.
**How to avoid:** Map principles to stable public interfaces (LoopState.from_disk, run_phase_loop, classify_failure, check_budget, ExitReason enum), not to internal helper functions (_transition, _advance_attempt, _reconstruct_validator_result).
**Warning signs:** README.md references a function name that does not exist in the codebase.

### Pitfall 4: ACC-01 Over-Engineering
**What goes wrong:** Building a new dry-run integration test or modifying validator_wrapper.py to "prove" ACC-01, when existing tests already suffice.
**Why it happens:** Misunderstanding ACC-01 as requiring a new test rather than declaring existing tests as proof.
**How to avoid:** D-03 is explicit: 371 green tests + test_loop_e2e.py = ACC-01 met. No new code needed.
**Warning signs:** Tasks in the plan that modify runtime Python files for acceptance testing purposes.

### Pitfall 5: HANDOFF.md Missing Resume Semantics
**What goes wrong:** HANDOFF.md lists files to copy but does not explain how --resume works on the GPU box, causing user confusion.
**Why it happens:** Resume semantics are subtle (reconciliation, from-phase, state reconstruction).
**How to avoid:** Include exact --resume command, expected env vars, ckpt path expectations, and what happens on first resume vs subsequent resume. Reference run.py resume_run_dir() behavior.
**Warning signs:** HANDOFF.md says "copy these files" but has no --resume command example.

### Pitfall 6: Three-Layer Loop Framing Lost
**What goes wrong:** The user's three-layer framing (Inner/Middle/Outer) from D-05 gets buried or omitted.
**Why it happens:** It is easier to describe only the middle layer (GitHub PR/issue cycle) since that is what the code implements.
**How to avoid:** Make the three-layer table a prominent section in both SKILL.md (DOC-01) and loop_engineering/README.md (DOC-02). The "plugin itself is what the loop fixes" insight is the key mental model.
**Warning signs:** SKILL.md describes FSM mechanics but never mentions the inner loop (attempts.jsonl) or outer loop (multi-model replay).

## Code Examples

Verified patterns from existing codebase:

### LoopState.from_disk -- disk-state reconstruction (P1)
```python
# Source: skills/adapt/lib/loop_controller.py lines 104-172
state = LoopState.from_disk(run_dir, phase)
# Re-reads loop_state.yml + attempts.jsonl tail every invocation
# Never relies on in-memory state across iterations
```

### ExitReason enum -- exit reasons for DOC-01
```python
# Source: skills/adapt/lib/loop_controller.py lines 66-73
class ExitReason(str, Enum):
    VALIDATOR_PASSED = "validator_passed"
    VALIDATOR_PASSED_AFTER_FIX = "validator_passed_after_fix"
    EXHAUSTED = "exhausted"
    ESCALATED = "escalated"
    BASE_ONLY = "base_only"
    HUMAN_NEEDED = "human_needed"
```

### FSMState enum -- 12-state FSM for DOC-01/DOC-02
```python
# Source: skills/adapt/lib/loop_controller.py lines 50-63
class FSMState(str, Enum):
    PROBE = "probe"
    EDIT = "edit"
    PR = "pr"
    MERGE_BASE = "merge_base"
    VALIDATE = "validate"
    DIAGNOSE = "diagnose"
    ISSUE = "issue"
    FIX_PR = "fix_pr"
    REVIEW = "review"
    MERGE_FIX = "merge_fix"
    RERUN = "rerun"
    EXIT = "exit"
```

### DiagnoseClassification -- maker-checker split for DOC-01/DOC-02
```python
# Source: skills/adapt/lib/diagnose_classifier.py lines 28-33
class DiagnoseClassification(str, Enum):
    CODE_BUG = "code-bug"
    FLAKY = "flaky"
    WRONG_DIRECTION = "wrong-direction"
    NEEDS_HUMAN = "needs-human"
```

### LoopBudget -- three-axis budget for DOC-01
```python
# Source: skills/adapt/lib/schema.py lines 49-54
class LoopBudget(BaseModel):
    max_attempts_per_phase: int = Field(5, ge=1, le=50)
    max_attempts_per_run: int = Field(25, ge=1, le=500)
    max_wallclock_minutes: int = Field(240, ge=10, le=10_080)
    escalation: Literal["human_needed", "autonomous_blocked"] = "human_needed"
```

### attempts.jsonl row format -- for DOC-04 summary generation
```python
# Source: skills/adapt/lib/validator_wrapper.py make_attempt_row
# Row fields: ts, attempt, kind, pr_url, issue_url, validator, verdict, exit_reason, event_id
# Read via: skills/adapt/lib/jsonl.py append_attempt (append-only, O_APPEND + fsync)
```

### run.py --resume CLI -- for ACC-03 HANDOFF.md
```bash
# Source: skills/adapt/scripts/run.py
loongforge-adapt --resume <run_dir> [--from-phase <N>]
# On resume: loads run_inputs.yml, reconciles remote PR/issue state,
# clears phase outputs from --from-phase onward if specified
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SKILL.md describes 6-phase linear workflow | SKILL.md describes loop-first architecture with repos:-gated behavior | Phase 5 (this phase) | Users understand the closed-loop nature before starting |
| No principle-to-implementation traceability | loop_engineering/README.md maps P1-P21 to code | Phase 5 (this phase) | Future maintainers can understand WHY each design choice was made |
| No end-of-run comprehension summary | comprehension_summary.md + phaseN_summary.md | Phase 5 (this phase) | Users understand what merged and why without reading raw JSONL |
| No GPU handoff procedure | HANDOFF.md + ds_v4_runbook.md | Phase 5 (this phase) | GPU acceptance can be driven by a separate session |

**Deprecated/outdated:**
- SKILL.md current "Claude Code Harness Reuse" section mentions `/loop` for coarse external waiting -- this stays (it describes the inner-loop constraint, not the middle-loop GitHub cycle)

## Open Questions

1. **Whether to create docs/loop-engineering-in-practice.md as a separate file**
   - What we know: D-05 says the user's draft content should be integrated into DOC-01 and DOC-02; Claude's discretion on whether it also lives as a separate file
   - What's unclear: Whether the user wants the three-layer framing documentable as a standalone reference or only as sections within SKILL.md + README.md
   - Recommendation: Do NOT create a separate file. Integrate the three-layer framing directly into SKILL.md (DOC-01) as a prominent section and into loop_engineering/README.md (DOC-02) as the organizing principle. This avoids content duplication and maintenance burden. If the user later wants a standalone doc, it can be extracted.

2. **comprehension_summary generation: Python helper vs manual template**
   - What we know: D-02 says derivable from disk state; data sources are loop_state.yml + attempts.jsonl; Claude's discretion on implementation
   - What's unclear: Whether a Python helper (summary_generator.py) or a markdown template with manual fill-in is better
   - Recommendation: Create a lightweight Python helper (`lib/summary_generator.py`) that reads loop_state.yml and attempts.jsonl and generates the markdown. Reason: (a) the data is structured, (b) the generation should be repeatable across runs, (c) manual template fill-in risks inconsistent formatting. Keep the helper under 80 lines.

3. **Bot artifact housekeeping scope**
   - What we know: ROADMAP success criterion 4 mentions closing auxiliary issues and verifying labels; ISSUE-04 requires label bootstrapping
   - What's unclear: Whether Phase 5 includes a housekeeping pass script or just documents the procedure
   - Recommendation: Document the procedure in SKILL.md (end-of-run housekeeping section) and loop_engineering/README.md. The actual label closure happens at run completion time via the existing gh_client.open_issue/close_issue methods. No new Python code needed for housekeeping -- it is a SKILL.md instruction to the agent, not an automated script.

## Environment Availability

Step 2.6: SKIPPED (no external dependencies identified). This phase is purely Markdown documentation + one optional Python helper + acceptance artifacts. All dependencies (PyYAML, Python 3.12, Path, datetime) are already in the project.

## Sources

### Primary (HIGH confidence)
- `skills/adapt/SKILL.md` (164 lines) -- existing structure, sections to preserve
- `skills/adapt/lib/loop_controller.py` (673 lines) -- FSM states, ExitReason, LoopState, run_phase_loop
- `skills/adapt/lib/diagnose_classifier.py` (183 lines) -- DiagnoseClassification, classify_failure
- `skills/adapt/lib/validator_wrapper.py` -- ValidatorResult, FailureSignature, PHASE_VALIDATORS
- `skills/adapt/lib/schema.py` -- LoopBudget, ReposBlock, RunInputs
- `skills/adapt/scripts/run.py` (483 lines) -- CLI entry, --resume, --dry-run
- `skills/adapt/lib/jsonl.py` -- append_attempt, assert_append_only
- `skills/adapt/lib/gh_client.py` (720 lines) -- GhClient Protocol, FakeGhClient
- `skills/adapt/lib/resume.py` -- reconcile_remote_state, ReconciliationMismatch
- `.planning/research/STACK.md` -- P1-P21 principle-to-implementation mapping table
- `CLAUDE.md` lines 8-120 -- identical P1-P21 mapping
- `.planning/REQUIREMENTS.md` -- DOC-01, DOC-02, DOC-04, ACC-01, ACC-02, ACC-03 definitions
- `.planning/ROADMAP.md` -- Phase 5 success criteria

### Secondary (MEDIUM confidence)
- CONTEXT.md D-05 user draft content (not on disk, described in context) -- three-layer loop framing
- `.planning/PROJECT.md` -- DS V4 model URLs, acceptance two-layer model
- `skills/adapt/knowledge_base/LOG.md` (41 lines) -- append-only event log format pattern
- `skills/adapt/knowledge_base/INDEX.md` (136 lines) -- KB index structure

### Tertiary (LOW confidence)
- se.rpcx.io/04, /08, /12 -- URLs return 404 as of 2026-06-23; content preserved in STACK.md and CLAUDE.md

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; existing Python + YAML sufficient
- Architecture: HIGH -- all source files read; pattern is documentation-only with surgical rewrite
- Pitfalls: HIGH -- derived from CONTEXT.md decisions and existing codebase structure; 6 specific pitfalls identified

**Research date:** 2026-06-23
**Valid until:** 2026-07-23 (stable; no fast-moving dependencies)
