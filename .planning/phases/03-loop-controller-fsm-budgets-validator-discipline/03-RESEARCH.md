# Phase 3: Loop Controller — FSM, Budgets & Validator Discipline - Research

**Researched:** 2026-06-22
**Domain:** Finite-state loop controller, validator discipline, maker-checker separation, structured failure signatures
**Confidence:** HIGH

## Summary

Phase 3 builds the FSM spine of the loop-engineering refactor: a re-entrant Python controller that drives `Probe -> Edit -> PR -> Merge(base) -> Validate -> (Diagnose -> Issue -> Fix-PR -> Review -> Merge -> Rerun)*` per phase, with hard three-axis budgets, maker-checker separation, validator-integrity checks, and structured failure signatures. The controller exits only on a verifiable validator-pass or a bounded escalation -- never on hope.

Phase 1 delivered schemas (`LoopBudget`, `LoopBlockOutput`, `PrBlockOutput`, `IssuesBlockOutput`), append-only JSONL, redactor, protected paths, preflight, `FakeGhClient` interface, and the `_validate_loop_evidence` inert hook. Phase 2 delivered the full `GhClient` lifecycle (`create_branch`, `open_pr`, `merge_pr`, `open_issue`, `close_issue`, `find_by_idempotency_key`, `find_by_dedup_key`), idempotency footers, template rendering, dedup logic, policy exceptions (`ProtectedPathError`, `HumanCommitError`, `DirectPushError`), and a simulated `FakeGhClient` state machine with 170 tests. Phase 3 composes these into a working FSM.

**Primary recommendation:** Build the controller as a pure state machine (`loop_controller.py`) that reads disk state on every entry, dispatches actions through the existing `GhClient` adapter, and writes structured `attempts.jsonl` rows. Separate the Diagnose sub-agent as a read-only classifier. Extend `_validate_loop_evidence` with the three validator-integrity checks (binary hash, log mtime, log presence). Add a `validator_wrapper.py` that normalizes validator output into structured `failure_signature` records.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOOP-01 | Implement explicit FSM `Probe -> Edit -> PR -> Merge(base) -> Validate -> (Diagnose -> Issue -> Fix-PR -> Review -> Merge -> Rerun)*` driven by a Python loop controller, callable per phase | FSM state machine pattern below; re-entrant entrypoint reads disk state; GhClient dispatches actions |
| LOOP-02 | Validator-pass is the only positive exit; FSM exit reasons enumerated: `validator_passed \| validator_passed_after_fix \| exhausted \| escalated \| base_only \| human_needed` | `LoopBlockOutput.exit_reason` Literal already defined in schema.py; controller enforces exit-reason enumeration |
| LOOP-03 | Three-axis termination budget: `max_attempts_per_phase` (default 5), `max_attempts_per_run` (default 25), `max_wallclock_minutes` (default 240); breach forces `autonomous_blocked`/`human_needed` exit, never `passed` | `LoopBudget` Pydantic model already exists with validated ceilings; controller checks all three axes before every transition |
| LOOP-04 | Diagnose step is a separate sub-agent distinct from Edit agent (maker != checker, P16); Diagnose is read-only and emits classification `code-bug \| flaky \| wrong-direction \| needs-human` | Diagnose classifier pattern below; read-only constraint enforced by sub-agent having no write tools; classification enum maps to FSM transitions |
| LOOP-05 | `wrong-direction` classification short-circuits the loop to `human_needed`, writing `phases/phaseN/escalation.md` with blockers + tried fixes | Escalation file pattern below; controller transitions to `human_needed` exit on `wrong-direction` verdict |
| VAL-01 | Validator wrapper calls existing per-phase validators on the merged HEAD; no validator logic is rewritten | Validator wrapper pattern below; wrapper invokes `loongforge-phase-gate` or validator scripts directly on merged HEAD |
| VAL-02 | Validators emit a `failure_signature: {kind, location, expected, actual}` structured record; free-text-only failures cause Diagnose to escalate, not guess | FailureSignature Pydantic model below; wrapper normalizes validator output; Diagnose refuses to classify free-text-only failures |
| VAL-03 | Phase 3/Phase 4 near-threshold failures auto-rerun N times (default 3) before being treated as real failures; `attempts.jsonl` distinguishes `flaky` from `failed` | Flake-rerun pattern below; wrapper tracks rerun count; verdict `flaky` vs `failed` written to attempts.jsonl |
| VAL-04 | Validator integrity check: validator binary hash + log mtime >= attempt timestamp + log present in `phases/phaseN/logs/`; `loongforge-phase-gate` rejects `passed` if any check fails | Integrity check pattern below; extends `_validate_loop_evidence` with three concrete checks; hash comparison via hashlib |
| VAL-05 | Cross-repo coordination: LoongForge PR body must pin Megatron commit SHA; validator records `LOONG_MEGATRON_SHA` and refuses if mismatch | SHA pinning pattern below; PR body template extended; validator wrapper records and asserts SHA |
| LOG-01 | Every loop transition appends one row to `phases/phaseN/attempts.jsonl` with `ts`, `attempt`, `kind`, `pr_url`, `issue_url`, `validator`, `verdict`, `exit_reason`, `event_id` | `append_attempt` from jsonl.py already exists; controller calls it at every FSM transition; `event_id` = `sha256(ts:attempt:kind:phase)` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | Schema validation for `loop_state.yml`, `FailureSignature`, `ValidatorResult` | Already in project; strict mode catches contract drift (P8) |
| pyyaml | 6.0.3 | Read/write `loop_state.yml` and `phaseN_output.yml` | Already in project; stdlib for YAML state |
| tenacity | 9.1.2 | Retry/backoff for transient `gh`/network failures ONLY | Already in project; distinguishes transient from semantic failures (P18) |
| pytest | 9.0.2 | Unit/integration tests for controller and validator wrapper | Already in project; FakeGhClient injection |
| hashlib | stdlib | Validator binary hash for VAL-04 integrity checks | No external dep needed |
| Jinja2 | 3.1.6 | Loop template rendering for Diagnose prompts | Already in project; P6 "prompts are code" |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | FSM state representation, `ValidatorResult`, `FailureSignature` | Pure-Python typed structures without Pydantic overhead for internal models |
| enum | stdlib | `FSMState`, `ExitReason`, `DiagnoseClassification`, `ValidatorVerdict` | Type-safe enumeration of FSM states and classifications |
| datetime | stdlib | Timestamps for `attempts.jsonl`, wall-clock budget tracking | Every attempt row and budget check |
| pathlib | stdlib | File path operations for `loop_state.yml`, `attempts.jsonl` | All disk I/O |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python enum + dataclass FSM | `transitions` library | `transitions` adds a dep for something achievable with 50 lines of enum+match; our FSM is small and fixed |
| Pydantic for internal FSM state | dataclasses | Pydantic adds validation overhead for internal-only models; use dataclasses for FSM state, Pydantic for persisted/disk schemas |
| hashlib for validator binary hash | `xxhash` | xxhash is faster but adds a dep; validator scripts are small (<1MB); hashlib is sufficient |

**Installation:**
No new dependencies required. All libraries are already installed in the project environment.

**Version verification:**
```
pydantic 2.12.5 (installed)
pyyaml 6.0.3 (installed)
tenacity 9.1.2 (installed)
pytest 9.0.2 (installed)
jinja2 3.1.6 (installed)
python 3.12.9 (installed)
```

## Architecture Patterns

### Recommended Project Structure
```
skills/adapt/
  lib/
    loop_controller.py     # NEW - FSM controller (the spine)
    validator_wrapper.py   # NEW - validator invocation + normalization
    diagnose_classifier.py # NEW - Diagnose sub-agent classification logic
    schema.py              # EXTENDED - FailureSignature, ValidatorResult, FSMStateRecord
    gh_client.py           # UNCHANGED (Phase 2 complete)
    idempotency.py         # UNCHANGED
    jsonl.py               # UNCHANGED
    protected_paths.py     # UNCHANGED
    redact.py              # UNCHANGED
    templates.py           # UNCHANGED
    preflight.py           # UNCHANGED
  scripts/
    validate_phase_completion.py  # EXTENDED - _validate_loop_evidence gets real checks
  loop_templates/
    phaseN/
      repair.md            # NEW - Jinja2 repair prompt templates (P6)
  tests/
    lib/
      test_loop_controller.py      # NEW - FSM state machine tests
      test_validator_wrapper.py    # NEW - validator wrapper tests
      test_diagnose_classifier.py  # NEW - Diagnose classification tests
      test_validate_loop_evidence.py  # EXTENDED - VAL-04 integrity checks
```

### Pattern 1: Re-entrant FSM Controller (Ralph Loop P1, P5)
**What:** The controller is a thin re-entrant Python entrypoint. Every invocation reads the full FSM state from disk (`loop_state.yml` + `attempts.jsonl` + `phaseN_output.yml`), decides the next action, dispatches it through `GhClient`, and writes the transition to disk. It never relies on in-memory state across invocations.
**When to use:** This is the core loop controller. Every phase loop invocation follows this pattern.

```python
# Source: rpcx.io/04 (P1, P5) + ARCHITECTURE.md Layer B
from enum import Enum
from dataclasses import dataclass
from pathlib import Path

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

class ExitReason(str, Enum):
    VALIDATOR_PASSED = "validator_passed"
    VALIDATOR_PASSED_AFTER_FIX = "validator_passed_after_fix"
    EXHAUSTED = "exhausted"
    ESCALATED = "escalated"
    BASE_ONLY = "base_only"
    HUMAN_NEEDED = "human_needed"

@dataclass
class LoopState:
    """Full FSM state, re-read from disk every invocation."""
    phase: int
    attempt: int
    current_state: FSMState
    exit_reason: ExitReason | None
    run_start_time: str   # ISO timestamp
    total_attempts_used: int

    @classmethod
    def from_disk(cls, run_dir: Path, phase: int) -> "LoopState":
        """Reconstruct state from loop_state.yml + attempts.jsonl tail."""
        ...
```

### Pattern 2: Maker-Checker Separation (P16)
**What:** The Edit/PR-author agent and the Diagnose agent are distinct sub-agents with distinct prompts and capabilities. Diagnose is read-only: it reads validator output, diff, and `attempts.jsonl`, but never writes code. It emits a classification enum.
**When to use:** After every validator failure, before any fix-PR is created.

```python
# Source: rpcx.io/12 (P16) + REQUIREMENTS.md LOOP-04
from enum import Enum

class DiagnoseClassification(str, Enum):
    CODE_BUG = "code-bug"
    FLAKY = "flaky"
    WRONG_DIRECTION = "wrong-direction"
    NEEDS_HUMAN = "needs-human"

@dataclass
class DiagnoseResult:
    classification: DiagnoseClassification
    rationale: str
    suggested_fix_summary: str | None  # advisory only (P11)
    failure_signature: FailureSignature | None

def classify_failure(
    validator_output: ValidatorResult,
    attempts_history: list[dict],
    diff_summary: str,
) -> DiagnoseResult:
    """Read-only classification. Never writes code or creates artifacts."""
    ...
```

### Pattern 3: Validator Wrapper with Integrity Checks (VAL-01, VAL-02, VAL-04)
**What:** A wrapper around existing per-phase validators that (a) invokes the validator on merged HEAD, (b) normalizes output into structured `FailureSignature`, (c) performs integrity checks (binary hash, log mtime, log presence), (d) auto-reruns near-threshold failures.
**When to use:** Every VALIDATE and RERUN transition in the FSM.

```python
# Source: REQUIREMENTS.md VAL-01, VAL-02, VAL-04
@dataclass
class FailureSignature:
    kind: str        # e.g., "numerical_mismatch", "missing_artifact"
    location: str    # e.g., "phase3/loss_diff.md:L42"
    expected: str    # e.g., "max_diff < 1e-5"
    actual: str      # e.g., "max_diff = 3.2e-4"

@dataclass
class ValidatorResult:
    name: str                    # "phase1-verify", "loss-diff", etc.
    status: str                  # "passed" | "failed" | "flaky"
    failure_signature: FailureSignature | None
    evidence: dict               # raw validator output
    integrity_ok: bool           # VAL-04 check result
    integrity_details: dict      # which checks passed/failed
    rerun_count: int             # VAL-03: how many times rerun
    loong_megatron_sha: str | None  # VAL-05: pinned SHA
```

### Pattern 4: Flake-Rerun with Threshold (VAL-03)
**What:** Phase 3 (loss-diff) and Phase 4 (feature-compat) validators use floating-point thresholds. Near-threshold failures auto-rerun N times (default 3). Only consistent failures are treated as real.
**When to use:** When validator fails for Phase 3 or Phase 4 and the failure is "near threshold" (within 2x of the passing threshold).

```python
# Source: REQUIREMENTS.md VAL-03 + PITFALLS.md Pitfall 3
FLAKE_RERUN_PHASES = {3, 4}
DEFAULT_FLAKE_RERUN_COUNT = 3

def should_rerun_for_flake(result: ValidatorResult, phase: int) -> bool:
    """Decide if a validator failure might be flaky and should be rerun."""
    if phase not in FLAKE_RERUN_PHASES:
        return False
    if result.status != "failed":
        return False
    # Near-threshold heuristic: failure signature indicates numerical
    # comparison that was close, not a hard crash
    if result.failure_signature and result.failure_signature.kind in (
        "numerical_mismatch", "threshold_exceeded",
    ):
        return True
    return False
```

### Pattern 5: Structured attempts.jsonl Row (LOG-01)
**What:** Every FSM transition appends exactly one row with the specified fields. The `event_id` is a deterministic hash of `(ts, attempt, kind, phase)` for traceability.
**When to use:** At every FSM state transition.

```python
# Source: REQUIREMENTS.md LOG-01
import hashlib
from datetime import datetime, timezone

def make_attempt_row(
    attempt: int, kind: str, phase: int,
    pr_url: str = "", issue_url: str = "",
    validator: str = "", verdict: str = "",
    exit_reason: str = "",
) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    event_id = hashlib.sha256(f"{ts}:{attempt}:{kind}:{phase}".encode()).hexdigest()[:16]
    return {
        "ts": ts,
        "attempt": attempt,
        "kind": kind,
        "pr_url": pr_url,
        "issue_url": issue_url,
        "validator": validator,
        "verdict": verdict,
        "exit_reason": exit_reason,
        "event_id": event_id,
    }
```

### Pattern 6: Three-Axis Budget Enforcement (LOOP-03)
**What:** Before every FSM transition, the controller checks three budgets: per-phase attempts, total run attempts, and wall-clock time. Any breach forces a non-passed exit.
**When to use:** At the start of every controller iteration and before every new attempt.

```python
# Source: REQUIREMENTS.md LOOP-03 + schema.py LoopBudget
def check_budget(
    budget: LoopBudget,
    phase_attempts: int,
    total_attempts: int,
    run_start_time: str,  # ISO timestamp
) -> ExitReason | None:
    """Return an ExitReason if any budget axis is breached, else None."""
    from datetime import datetime, timezone

    if phase_attempts >= budget.max_attempts_per_phase:
        return ExitReason.EXHAUSTED
    if total_attempts >= budget.max_attempts_per_run:
        return ExitReason.EXHAUSTED

    start = datetime.fromisoformat(run_start_time)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds() / 60.0
    if elapsed >= budget.max_wallclock_minutes:
        return ExitReason.EXHAUSTED

    return None
```

### Pattern 7: Cross-Repo SHA Pinning (VAL-05)
**What:** When the controller opens a LoongForge PR, it pins the Megatron commit SHA in the PR body. The validator wrapper records `LOONG_MEGATRON_SHA` and refuses validation on mismatch.
**When to use:** Every PR creation and every validator invocation.

```python
# Source: REQUIREMENTS.md VAL-05
def get_megatron_head_sha(gh: GhClient, owner_repo: str, ref: str) -> str:
    """Get the current HEAD SHA of the Megatron repo branch."""
    result = gh._run(["api", f"repos/{owner_repo}/git/ref/heads/{ref}", "--jq", ".object.sha"])
    if result.returncode != 0:
        raise RuntimeError(f"Cannot resolve Megatron SHA for {owner_repo}:{ref}")
    return result.stdout.strip()
```

### Pattern 8: Escalation File on wrong-direction / needs-human (LOOP-05)
**What:** When Diagnose classifies a failure as `wrong-direction` or `needs-human`, the controller writes `phases/phaseN/escalation.md` with blockers, tried fixes, and exit context.
**When to use:** On `wrong-direction` or `needs-human` classification.

```python
# Source: REQUIREMENTS.md LOOP-05 + rpcx.io/04 (P4 escape hatch)
def write_escalation(
    run_dir: Path, phase: int,
    classification: DiagnoseClassification,
    rationale: str,
    attempts_summary: list[dict],
) -> Path:
    path = run_dir / "phases" / f"phase{phase}" / "escalation.md"
    lines = [
        f"# Phase {phase} Escalation\n",
        f"**Classification:** {classification.value}\n",
        f"**Rationale:** {rationale}\n",
        f"\n## Attempts Summary\n",
    ]
    for a in attempts_summary:
        lines.append(f"- Attempt {a['attempt']}: {a.get('verdict', 'N/A')} -- {a.get('kind', 'N/A')}")
    path.write_text("\n".join(lines))
    return path
```

### Anti-Patterns to Avoid
- **Same agent for Edit and Diagnose:** Violates P16. The model that wrote the code is too lenient with itself. Diagnose MUST be a distinct sub-agent with read-only tools.
- **Retrying validator failures as if transient:** Validator failure is signal, not noise (P18). Transient retries (tenacity) are ONLY for `gh` network 502s, never for validator verdicts.
- **Free-form Claude self-report as exit signal:** The only legitimate exit is `loongforge-phase-gate` reading `phaseN_output.yml` with `validator.status == "passed"` (P3, P10).
- **In-memory FSM state across invocations:** State lives on disk (P1). Every controller entry re-reads `loop_state.yml` + `attempts.jsonl` tail.
- **Auto-merging fix-PRs without re-running validator on merged commit:** Validates wrong artifact. Must merge THEN validate on merged HEAD (REQ-RERUN-01).
- **`/loop` invocation from the controller:** The controller is a Python module, never invokes `/loop`. The lint check from Phase 1 already enforces this (SAFE-02).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| FSM state persistence | Custom SQLite or pickle | `loop_state.yml` (YAML) + `attempts.jsonl` (JSONL) | Greppable, diffable, replayable, partial-write safe; already established by Phase 1 |
| PR/issue lifecycle | Raw `subprocess.run(["gh", ...])` | `GhClient` adapter (Phase 2) | Already handles idempotency, dedup, redaction, protected paths, human commit detection |
| Schema validation | Manual dict checks | Pydantic `LoopBudget`, `LoopBlockOutput`, `FailureSignature` | Strict mode catches contract drift; already in project |
| Append-only logging | Custom file writer | `jsonl.append_attempt()` | Already handles O_APPEND + fsync for atomic writes |
| Idempotency on crash-resume | Custom dedup logic | `idempotency.compute_idempotency_key()` + `GhClient.find_by_idempotency_key()` | Already implemented in Phase 2 |
| Issue dedup across attempts | Custom fingerprinting | `idempotency.compute_dedup_key()` + `GhClient.find_by_dedup_key()` | Already implemented in Phase 2 |
| Secret redaction | Custom regex filter | `redact.redact()` | Already handles 10 patterns + YAML-configurable domains |
| Validator output normalization | Ad-hoc string parsing | `validator_wrapper.py` with structured `FailureSignature` Pydantic model | Free-text-only failures are the #1 cause of loop wandering (Pitfall 10) |

**Key insight:** Phase 2 built the entire PR/issue lifecycle as a `GhClient` adapter with a `FakeGhClient` state machine. The controller should NEVER bypass this adapter -- all GitHub interactions go through `GhClient`. This is the "connector" in P15's five essentials.

## Common Pitfalls

### Pitfall 1: Fake or Stale "validator passed" Exit (P0, VAL-04)
**What goes wrong:** Controller accepts `passed` from a stale log, a cached `phaseN_output.yml`, or a validator that was never actually re-run on the merged HEAD.
**Why it happens:** Validator output file mtime predates the attempt; no integrity check on validator binary; merged HEAD not actually validated.
**How to avoid:** Three-part integrity check in `_validate_loop_evidence`: (1) validator script hash matches recorded hash, (2) log mtime >= attempt start time, (3) log file present in `phases/phaseN/logs/`. Reject `passed` if any check fails.
**Warning signs:** `passed` returned in <30s for GPU phases; validator timestamp older than PR merge timestamp; `attempts.jsonl` last row has no validator output.

### Pitfall 2: Budget Breach Exits as "passed" (P0, LOOP-03)
**What goes wrong:** Controller hits max_attempts but still writes `exit_reason: validator_passed` because the last attempt happened to pass after the budget was already exhausted.
**Why it happens:** Budget check and exit decision are not atomic; validator result arrives after budget check.
**How to avoid:** Budget check happens BEFORE processing the validator result. If budget is breached, the exit reason is always `exhausted` or `human_needed`, regardless of validator status. Never overwrite an exhausted exit with passed.
**Warning signs:** `attempts.jsonl` shows `attempt > max_attempts_per_phase` but `exit_reason: validator_passed`.

### Pitfall 3: Diagnose Guesses on Free-Text Failures (P1, VAL-02)
**What goes wrong:** Validator emits only free-text output with no structured signature. Diagnose "guesses" a classification and proposes a fix that addresses the wrong root cause.
**Why it happens:** Some validators (especially Phase 0 checks) produce boolean outputs without structured `{kind, location, expected, actual}` signatures.
**How to avoid:** If `failure_signature` is missing or `kind` is empty, Diagnose MUST classify as `needs-human` and escalate. Never guess from free text.
**Warning signs:** Two consecutive issues for the same phase have very different diagnoses; Diagnose classifications flip between `code-bug` and `flaky` without code changes.

### Pitfall 4: Cross-Repo SHA Mismatch (P0, VAL-05)
**What goes wrong:** LoongForge PR was tested against Megatron SHA `abc123`, but by the time the PR is merged, Megatron has moved to `def456`. Validator runs on the new Megatron HEAD and fails, but the failure is attributed to the LoongForge PR.
**Why it happens:** Megatron PR merges independently; LoongForge PR body does not pin the Megatron SHA.
**How to avoid:** (1) Controller records `LOONG_MEGATRON_SHA` at PR-creation time and embeds it in the PR body. (2) Validator wrapper reads the pinned SHA and asserts it matches the runtime environment. (3) On mismatch, validation is refused (not failed) -- the controller re-pins and re-validates.
**Warning signs:** Validator failure mentions `ImportError`, `undefined symbol`, or version mismatch; the Megatron PR referenced is still open.

### Pitfall 5: Diagnose Same Agent as Edit (P0, LOOP-04)
**What goes wrong:** The same sub-agent that authored the code also classifies the failure, leading to self-serving diagnoses ("my code is correct, the validator is flaky").
**Why it happens:** Convenience; no architectural enforcement of separation.
**How to avoid:** Diagnose is a distinct sub-agent with distinct prompt, no write tools, and a classification enum output. The controller enforces this split structurally.
**Warning signs:** Diagnose consistently classifies as `flaky` rather than `code-bug`; fix-PRs repeat the same pattern that failed before.

### Pitfall 6: Flake Rerun Consuming Budget (P1, VAL-03)
**What goes wrong:** Three flake reruns count as three "attempts" against the budget, exhausting the phase budget on what is actually a single logical attempt.
**Why it happens:** Each rerun appends an `attempts.jsonl` row; budget check counts rows.
**How to avoid:** Flake reruns for the SAME logical attempt share the same `attempt` number. The `kind` field distinguishes `validate` from `validate_rerun`. Budget counts logical attempts (unique `attempt` numbers), not total rows.
**Warning signs:** Phase 3 budget exhausted after only 2 real attempts because each had 3 flake reruns.

### Pitfall 7: Wall-Clock Budget Not Tracking Across Resume (P1, LOOP-03)
**What goes wrong:** After `--resume`, the wall-clock timer restarts from zero instead of continuing from the original run start time.
**Why it happens:** `run_start_time` is not persisted or is overwritten on resume.
**How to avoid:** `run_start_time` is written once to `loop_state.yml` at run init and never overwritten. On resume, the controller reads the original start time and computes elapsed wall-clock from that.
**Warning signs:** After resume, `max_wallclock_minutes` is never breached despite the run having started hours ago.

### Pitfall 8: Controller Inlines Repair Prompts Instead of Using Templates (P2, P6)
**What goes wrong:** Repair prompts are hardcoded strings inside `loop_controller.py`, making them impossible to version, review, or improve without code changes.
**Why it happens:** Convenience; the "prompts are code" discipline is not enforced structurally.
**How to avoid:** All repair/diagnose prompts live under `skills/adapt/loop_templates/phaseN/repair.md` as Jinja2 templates. The controller renders them at runtime. Prompts are versioned in git.
**Warning signs:** Long string literals in `loop_controller.py`; prompt changes require Python file edits.

## Code Examples

### FSM Controller Main Loop (Re-entrant)
```python
# Source: rpcx.io/04 (P1, P2, P5) + ARCHITECTURE.md Layer B
from pathlib import Path
from skills.adapt.lib.gh_client import GhClient
from skills.adapt.lib.schema import LoopBudget
from skills.adapt.lib.jsonl import append_attempt

def run_phase_loop(
    run_dir: Path,
    phase: int,
    gh: GhClient,
    budget: LoopBudget,
    dry_run: bool = False,
) -> ExitReason:
    """Re-entrant phase loop controller. Reads state from disk, dispatches
    actions, writes transitions. Returns only when exit condition met."""

    state = LoopState.from_disk(run_dir, phase)

    # Budget pre-check (LOOP-03)
    budget_breach = check_budget(budget, state.attempt, state.total_attempts_used, state.run_start_time)
    if budget_breach:
        state.exit_reason = budget_breach
        state.persist(run_dir)
        append_attempt(run_dir / "phases" / f"phase{phase}" / "attempts.jsonl",
                       make_attempt_row(state.attempt, "budget_check", phase, exit_reason=budget_breach.value))
        return budget_breach

    # Main FSM dispatch
    match state.current_state:
        case FSMState.PROBE:
            # Phase 0/1 input parsing -- reuse existing phase agents
            ...
        case FSMState.EDIT:
            # Dispatch adapt-phaseN agent for code edits
            ...
        case FSMState.PR:
            # Call gh.open_pr with template
            ...
        case FSMState.MERGE_BASE:
            # Call gh.merge_pr (base PR must merge before validate, PR-02)
            ...
        case FSMState.VALIDATE:
            result = run_validator(run_dir, phase, gh, budget)
            if result.status == "passed":
                state.exit_reason = ExitReason.VALIDATOR_PASSED
                ...
            elif should_rerun_for_flake(result, phase) and result.rerun_count < DEFAULT_FLAKE_RERUN_COUNT:
                state.current_state = FSMState.RERUN
                ...
            else:
                state.current_state = FSMState.DIAGNOSE
                ...
        case FSMState.DIAGNOSE:
            diagnosis = classify_failure(result, read_attempts(run_dir, phase), diff_summary)
            if diagnosis.classification == DiagnoseClassification.WRONG_DIRECTION:
                write_escalation(run_dir, phase, diagnosis.classification, diagnosis.rationale, ...)
                state.exit_reason = ExitReason.HUMAN_NEEDED
                ...
            elif diagnosis.classification == DiagnoseClassification.NEEDS_HUMAN:
                write_escalation(run_dir, phase, diagnosis.classification, diagnosis.rationale, ...)
                state.exit_reason = ExitReason.HUMAN_NEEDED
                ...
            else:
                state.current_state = FSMState.ISSUE
                ...
        case FSMState.ISSUE:
            # Call gh.open_issue with failure_signature
            ...
        case FSMState.FIX_PR:
            # Dispatch adapt-phaseN agent for fix
            ...
        case FSMState.REVIEW:
            # Sub-agent review (maker != checker)
            ...
        case FSMState.MERGE_FIX:
            # Call gh.merge_pr (fix PR)
            ...
        case FSMState.RERUN:
            # Re-run validator on merged HEAD
            ...
        case FSMState.EXIT:
            return state.exit_reason

    state.persist(run_dir)
    return run_phase_loop(run_dir, phase, gh, budget, dry_run)
```

### Validator Integrity Check Extension (VAL-04)
```python
# Source: REQUIREMENTS.md VAL-04
import hashlib
from pathlib import Path
from datetime import datetime

def check_validator_integrity(
    run_dir: Path, phase: int, attempt_start_time: str,
    recorded_hash: str | None = None,
) -> dict:
    """Three-part integrity check: binary hash, log mtime, log presence."""
    results = {"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True}

    # Check 1: Validator binary hash (if recorded)
    if recorded_hash:
        validator_path = run_dir / "bin" / "loongforge-phase-gate"
        if validator_path.exists():
            current_hash = hashlib.sha256(validator_path.read_bytes()).hexdigest()[:16]
            results["binary_hash_ok"] = current_hash == recorded_hash
        else:
            results["binary_hash_ok"] = False

    # Check 2: Log file present
    log_dir = run_dir / "phases" / f"phase{phase}" / "logs"
    if not log_dir.exists() or not any(log_dir.iterdir()):
        results["log_present"] = False

    # Check 3: Log mtime >= attempt timestamp
    if results["log_present"]:
        attempt_time = datetime.fromisoformat(attempt_start_time)
        for log_file in log_dir.iterdir():
            if log_file.stat().st_mtime < attempt_time.timestamp():
                results["log_mtime_ok"] = False
                break

    results["integrity_ok"] = all(results.values())
    return results
```

### Extended _validate_loop_evidence (VAL-04)
```python
# Source: REQUIREMENTS.md VAL-04 + existing validate_phase_completion.py
def _validate_loop_evidence(data: dict[str, Any]) -> None:
    """When loop_engineering: true, validate loop block + integrity checks."""
    if data.get("loop_engineering") is not True:
        return

    loop_block = data.get("loop")
    if loop_block is not None:
        from skills.adapt.lib.schema import LoopBlockOutput
        LoopBlockOutput.model_validate(loop_block)

    # VAL-04: If exit_reason is validator_passed, integrity must hold
    if loop_block and loop_block.get("exit_reason") in (
        "validator_passed", "validator_passed_after_fix",
    ):
        integrity = data.get("validator_integrity", {})
        if not integrity.get("integrity_ok", False):
            raise ValueError(
                "validator_integrity checks failed: "
                f"binary_hash_ok={integrity.get('binary_hash_ok')}, "
                f"log_mtime_ok={integrity.get('log_mtime_ok')}, "
                f"log_present={integrity.get('log_present')}"
            )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| In-memory FSM state | Re-entrant disk-based state (P1) | rpcx.io/04 | State survives crashes; controller is testable |
| Single exit condition | Dual exit: validator-pass OR budget-exhausted (P2) | rpcx.io/04 | No infinite loops; budget breaches are explicit |
| Same agent edits and diagnoses | Maker-checker separation (P16) | rpcx.io/12 | Diagnose is impartial; no self-serving classifications |
| Free-text validator output | Structured `failure_signature: {kind, location, expected, actual}` | REQUIREMENTS.md VAL-02 | Machine-parseable; enables Diagnose classification |
| No validator integrity check | Binary hash + log mtime + log presence (VAL-04) | PITFALLS.md Pitfall 1 | Prevents stale/fake "passed" exits |
| Retry all failures | Flake-rerun only for near-threshold in Phase 3/4 (VAL-03) | PITFALLS.md Pitfall 3 | Distinguishes non-determinism from code regression |

**Deprecated/outdated:**
- In-session loop with context accumulation: replaced by external-process forking (P5). Each attempt is fresh; state lives on disk.
- "Hopeful exit" (exiting loop because "it should work"): replaced by validator-only exit signal (P3, P10).

## Open Questions

1. **Diagnose sub-agent implementation detail**
   - What we know: Must be read-only, distinct from Edit, emits classification enum. The existing code-review tool (`references/tools/code-review/SKILL.md`) could serve as a pattern.
   - What's unclear: Whether Diagnose is a separate Claude Code agent definition (`.md` file) or a Python function that renders a Jinja2 prompt and calls the model. Phase 3 research recommends the latter (Python function + Jinja2 template) for testability, with the option to promote to a standalone agent in Phase 4 wiring.
   - Recommendation: Implement as a Python module (`diagnose_classifier.py`) with Jinja2 templates under `loop_templates/`. This keeps it unit-testable without needing a live agent.

2. **Review step in the FSM**
   - What we know: REVIEW is listed in the FSM. The existing code-review sub-agent (`references/tools/code-review/SKILL.md`) exists and could be reused.
   - What's unclear: Whether REVIEW is a mandatory gate or advisory (P11: "Treat review output as advisory. Never blindly apply it."). Phase 3 should implement REVIEW as advisory -- the controller logs the review result but does not block on it.
   - Recommendation: Advisory review. Controller records review output in `attempts.jsonl` but proceeds to MERGE_FIX unless review explicitly raises `ProtectedPathError` or similar.

3. **Stacked-PR vs Flat-PR model for fix-PRs**
   - What we know: Fix-PRs need a target branch. They could target the base PR's branch (stacked) or the repo default branch (flat).
   - What's unclear: Which model LoongForge/Megatron branch protection allows.
   - Recommendation: Start with flat model (fix-PRs target the repo's base ref directly). Stacked-PR support can be added later. The controller already knows the `base_ref` from `run_inputs.yml`.

4. **Validator script hash recording**
   - What we know: VAL-04 requires checking validator binary hash. The `loongforge-phase-gate` script is in `bin/` of the plugin repo.
   - What's unclear: Whether to hash the script at controller start time or at validator invocation time. Hashing at controller start captures the initial state; hashing at invocation captures any mid-run changes (which would be a red flag).
   - Recommendation: Hash at controller start, record in `loop_state.yml`. Re-check at every VALIDATE transition. If hash changed mid-run, that's a VAL-04 violation.

5. **Budget numbers (5/25/240)**
   - What we know: These are heuristics from CLAUDE.md. The `LoopBudget` Pydantic model already enforces ceilings (le=50, le=500, le=10_080).
   - What's unclear: Whether 5 attempts per phase is sufficient for real adaptation work. LOW confidence per CLAUDE.md.
   - Recommendation: Use the defaults. The `LoopBudget` model allows runtime override via `run_inputs.yml`. Tune after first 2-3 real GPU runs.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Controller runtime | Yes | 3.12.9 | -- |
| pydantic | Schema validation | Yes | 2.12.5 | -- |
| PyYAML | State file I/O | Yes | 6.0.3 | -- |
| tenacity | Transient retry | Yes | 9.1.2 | -- |
| pytest | Test framework | Yes | 9.0.2 | -- |
| Jinja2 | Prompt templates | Yes | 3.1.6 | -- |
| gh CLI | RealGhClient | Yes | 2.87.3 | FakeGhClient for dry-run |
| pytest-mock | Mocking | No | -- | unittest.mock (stdlib) |

**Missing dependencies with no fallback:**
- None. All core dependencies are available.

**Missing dependencies with fallback:**
- `pytest-mock`: Not installed, but `unittest.mock` (stdlib) provides equivalent `patch`, `MagicMock`, and `call` functionality. The existing test suite already uses `FakeGhClient` injection rather than mocking, which is the recommended pattern.

## Sources

### Primary (HIGH confidence)
- `skills/adapt/lib/schema.py` - LoopBudget, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput models (verified in code)
- `skills/adapt/lib/gh_client.py` - GhClient Protocol, RealGhClient, FakeGhClient with full lifecycle (verified in code)
- `skills/adapt/lib/jsonl.py` - append_attempt, assert_append_only (verified in code)
- `skills/adapt/lib/idempotency.py` - compute_idempotency_key, compute_dedup_key, format_footer, parse_footer (verified in code)
- `skills/adapt/lib/templates.py` - PR/issue/comment template rendering (verified in code)
- `skills/adapt/lib/protected_paths.py` - Validator path protection (verified in code)
- `skills/adapt/scripts/validate_phase_completion.py` - _validate_loop_evidence inert hook (verified in code)
- `.planning/REQUIREMENTS.md` - LOOP-01..05, VAL-01..05, LOG-01 (authoritative)
- `.planning/ROADMAP.md` - Phase 3 success criteria (5 items) (authoritative)
- `.planning/PROJECT.md` - Core value, constraints, key decisions (authoritative)
- `CLAUDE.md` - Loop-engineering principles P1..P21, toolchain, hard NOs (authoritative)

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` - Integration points IP-1..IP-10, build order B1..B13, Layer B controller spec
- `.planning/research/PITFALLS.md` - 19 pitfalls keyed to phases; Pitfalls 1, 2, 3, 4, 10, 16 directly relevant
- `.planning/research/FEATURES.md` - Table-stakes TS-05 (loop FSM), TS-09 (validator wrapper), TS-10 (diagnose), TS-15 (attempts.jsonl)
- `skills/adapt/scripts/run.py` - Run init/resume, phase output helpers (integration surface)

### Tertiary (LOW confidence)
- Specific budget values (5/25/240) - heuristic, needs tuning after real runs
- Flake-rerun threshold heuristic - "within 2x of passing threshold" is a reasonable starting point but not verified against actual validator output
- Whether REVIEW step should be mandatory vs advisory - assumed advisory per P11

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all dependencies already installed and verified; no new deps needed
- Architecture: HIGH - FSM pattern is directly specified by REQUIREMENTS; Phase 1/2 code provides all building blocks
- Pitfalls: HIGH - grounded in existing PITFALLS.md and rpcx.io principles; most relevant pitfalls already identified
- Budget numbers: LOW - heuristics; tune after real runs

**Research date:** 2026-06-22
**Valid until:** 2026-07-22 (stable domain; Python/gh/patterns unlikely to change)
