# Loop Engineering Reference — Adapt Skill

This document traces the loop-engineering design of the adapt skill to its foundational principles from three articles on se.rpcx.io (04, 08, 12). Each principle is mapped to the concrete implementation in this codebase.

The three source articles:

- **se.rpcx.io/04** — Ralph Loop (execution primitive)
- **se.rpcx.io/08** — Goal Workflow (gate / pipeline discipline)
- **se.rpcx.io/12** — Loop Engineering (system view)

Note: The se.rpcx.io/04, /08, /12 URLs returned 404 as of the research date (2026-06-22). They are cited anyway as the original source locations. The content is preserved in this repo's `.planning/research/STACK.md` and `CLAUDE.md`.

## Three Nested Loops

The adapt skill's loop architecture is organized around three nested loop layers:

| Layer | Scope | Coordination Bus |
|-------|-------|-------------------|
| Inner | Phase-internal self-repair (`attempts.jsonl`) | Disk files |
| Middle | GitHub PR/issue cycle (loop controller) | GitHub (`gh` CLI) |
| Outer | Multi-model replay (future) | Run directory |

The **Inner loop** handles retries within a single phase execution: the phase agent writes to `attempts.jsonl` and the step gate enforces completion before exit. The **Middle loop** spans GitHub: the loop controller drives PR creation, merge, validation, diagnose, issue, fix-PR, review, merge-fix, and rerun as a closed cycle. The **Outer loop** is reserved for future multi-model replay scenarios where the same adapt skill runs across different model families.

Key insight: "The plugin itself is what the loop fixes." The loop doesn't adapt the model; it adapts the plugin's own bugs out.

---

## Principles from se.rpcx.io/04 — Ralph Loop

### P1

**"Ralph is a Bash loop." Same prompt re-injected; state lives on disk, not in context.**

**Source:** se.rpcx.io/04 (Ralph Loop)

**Implementation:** `skills/adapt/lib/loop_controller.py` — `LoopState.from_disk(run_dir, phase)` reconstructs FSM state from `loop_state.yml` + `attempts.jsonl` tail every invocation. No in-memory conversation state persists across iterations. The re-entrant `run_phase_loop()` entrypoint reloads state from disk at the start of every call.

### P2

**Two exit conditions in OR: explicit promise match AND a hard max-iterations safety net.**

**Source:** se.rpcx.io/04 (Ralph Loop)

**Implementation:** `skills/adapt/lib/loop_controller.py` — `check_budget(budget, phase_attempts, total_attempts, run_start_time)` enforces all three budget axes (`max_attempts_per_phase`, `max_attempts_per_run`, `max_wallclock_minutes`). Returns `ExitReason.EXHAUSTED` when any axis is breached, ensuring the loop always has a hard upper bound.

### P3

**Honesty constraint: completion only when "completely and unequivocally TRUE."**

**Source:** se.rpcx.io/04 (Ralph Loop)

**Implementation:** `skills/adapt/lib/validator_wrapper.py` — `run_validator()` result is the only legitimate exit signal. `loongforge-phase-gate` reading `phaseN_output.yml` is the gate. Free-form Claude verdicts are forbidden as exit signals. The FSM only transitions to EXIT with a `validator_passed` or `validator_passed_after_fix` reason when the validator has confirmed passage.

### P4

**Prompt 4 principles: clear completion, phased goals, self-correction, escape hatch.**

**Source:** se.rpcx.io/04 (Ralph Loop)

**Implementation:** `skills/adapt/loop_templates/phaseN/repair.md` — every repair prompt template includes an `## Escape Hatch` paragraph instructing the agent to write `phases/phaseN/escalation.md` and exit `human_needed` after 3 attempts with no progress. `skills/adapt/lib/diagnose_classifier.py` — `write_escalation(run_dir, phase, classification, rationale, attempts_summary)` writes the escalation file.

### P5

**Two architectures: in-session (Stop Hook, ralph-wiggum) vs external bash fork (frankbria). Chosen: external-process forking.**

**Source:** se.rpcx.io/04 (Ralph Loop)

**Implementation:** `skills/adapt/lib/loop_controller.py` — `run_phase_loop()` is a single-process, re-entrant Python entrypoint. Each iteration forks `gh` CLI calls via `GhClient`. `skills/adapt/lib/gh_client.py` — `RealGhClient._run()` wraps `subprocess.run(["gh", ...])` for every GitHub API call. State is reloaded from disk, not held in memory across iterations.

### P6

**"Operator skill matters. Success depends on writing good prompts, not just having a good model."**

**Source:** se.rpcx.io/04 (Ralph Loop)

**Implementation:** `skills/adapt/loop_templates/phaseN/repair.md` — versioned Jinja2 template under `loop_templates/`. Prompts are code, not inline strings. The template includes structured fields (phase, attempt, failure signature, previous attempts, diff summary, escape hatch) that are filled at runtime, ensuring consistency and traceability across iterations.

### P7

**Loop bloat: "max-iterations limits cycles, but cannot prevent moving in the wrong direction."**

**Source:** se.rpcx.io/04 (Ralph Loop)

**Implementation:** `skills/adapt/lib/diagnose_classifier.py` — `classify_failure(validator_output, attempts_history, diff_summary)` is mandatory before every Fix-PR. It classifies failures into `DiagnoseClassification` enum values: `CODE_BUG`, `FLAKY`, `WRONG_DIRECTION`, `NEEDS_HUMAN`. `WRONG_DIRECTION` (3+ consecutive attempts with same failure signature kind + location) short-circuits to `human_needed` and writes `escalation.md`.

---

## Principles from se.rpcx.io/08 — Goal Workflow

### P8

**Pipeline thinking: "no seams between stages." Each stage has explicit input/output contracts.**

**Source:** se.rpcx.io/08 (Goal Workflow)

**Implementation:** `skills/adapt/lib/loop_controller.py` — `_transition(state, new_state, run_dir, kind, **attempt_fields)` writes typed artifacts (`loop_state.yml` and appends to `attempts.jsonl`) on every FSM state transition. The next state reads them back from disk. `skills/adapt/lib/schema.py` — Pydantic models (`LoopBlockOutput`, `PrBlockOutput`, `IssuesBlockOutput`) enforce typed contracts in `phaseN_output.yml`.

### P9

**"Steps are auto inside, gated between."**

**Source:** se.rpcx.io/08 (Goal Workflow)

**Implementation:** Phase-internal repair loop (`run_phase_loop`) is fully autonomous: the FSM drives PROBE through EXIT without human intervention within a single phase. Cross-phase transition stays gated by the user via the `[CHECKPOINT]` protocol documented in `skills/adapt/SKILL.md` Checkpoint Protocol section. Only proceed to the next phase after user confirmation unless `options.autonomous_mode: true`.

### P10

**Acceptance criteria must be objectively testable.**

**Source:** se.rpcx.io/08 (Goal Workflow)

**Implementation:** `skills/adapt/lib/validator_wrapper.py` — `ValidatorResult.status == "passed"` is the only positive exit condition. `ExitReason` references a specific validator name and status. Free-form Claude verdicts are forbidden as exit signals. The validator result is normalized into a structured `ValidatorResult` with `name`, `status`, `failure_signature`, and `evidence` fields — no subjective assessment.

### P11

**"Treat review output as advisory. Never blindly apply it."**

**Source:** se.rpcx.io/08 (Goal Workflow)

**Implementation:** `skills/adapt/lib/diagnose_classifier.py` — `DiagnoseResult.suggested_fix_summary` goes into the fix-PR body as advisory text, not into the diff. The Edit agent (loop controller PR/FIX_PR states) decides what to change. The diagnose agent is explicitly read-only and cannot write code; its suggestions are recommendations, not instructions.

### P12

**Issue-granularity: one Issue = one session. Decompose if acceptance > 5 items.**

**Source:** se.rpcx.io/08 (Goal Workflow)

**Implementation:** One GitHub issue = one validator failure = one fix-PR (ISSUE-02). `skills/adapt/lib/gh_client.py` — `open_issue()` creates one issue per failure, with `Fixes #N` linkage in every fix-PR body. Multiple distinct failures produce multiple issues, each linked to its own fix-PR. The dedup key (`compute_dedup_key`) prevents duplicate issues for the same failure across attempts.

### P13

**Decision-record value: capture "what alternatives existed and why we didn't pick them."**

**Source:** se.rpcx.io/08 (Goal Workflow)

**Implementation:** After each successful loop, `phases/phaseN/decision_log.md` is written (1-3 bullets) and linked from the merged PR body. This captures the reasoning behind each repair, including what alternatives were considered and why the chosen fix was selected.

---

## Principles from se.rpcx.io/12 — Loop Engineering

### P14

**"Stop prompting agents. Design loops that prompt your agents."**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:** This refactor produces a loop-controller specification — `skills/adapt/lib/loop_controller.py` `run_phase_loop()` — not a smarter Phase-N prompt. The skill author is the loop author. The FSM drives the agent through states; the agent responds to the structured context provided by each state transition, not to an ever-growing conversation.

### P15

**Five essentials: Automations, Worktrees, Skills, Plugins/Connectors, Sub-agents, State.**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:**

| Essential | Mapping |
|-----------|---------|
| Automations | `--resume` re-entry (`skills/adapt/scripts/run.py` `resume_run_dir()`) |
| Worktrees | N/A (single-run architecture) |
| Skills | `adapt` skill itself |
| Connectors | `gh` CLI (`skills/adapt/lib/gh_client.py`) |
| Sub-agents | Phase-N edit agent + Diagnose agent (`skills/adapt/lib/diagnose_classifier.py`) |
| State | `attempts.jsonl` + `loop_state.yml` (`skills/adapt/lib/jsonl.py` `append_attempt()`, `LoopState.persist()`) |

### P16

**Maker-checker separation: "the model that writes code is too lenient with itself."**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:** `skills/adapt/lib/diagnose_classifier.py` — `classify_failure()` is read-only: it reads validator output and attempts history, but never writes code or calls `gh` methods (except `write_escalation` for the human-needed path). The Edit agent (`loop_controller.py` PR and FIX_PR states) does the writing: it creates branches, opens PRs, and submits diffs. The Diagnose agent classifies; the Edit agent acts.

### P17

**Hill-climbing formula: goal + metric + change + measure = autonomous improvement.**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:** Each phase loop enumerates all four elements:
- **Goal:** validator pass (`ValidatorResult.status == "passed"`)
- **Metric:** `ValidatorResult.status` and structured `FailureSignature` (kind, location, expected, actual)
- **Change:** fix-PR diff submitted by the Edit agent
- **Measure:** re-run validator after merge (`RERUN` state in `run_phase_loop`)

If any of the four is missing, the loop refuses to proceed — there is no hill to climb.

### P18

**"A loop without a gate is not autonomous, it's a token bonfire."**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:** `skills/adapt/lib/loop_controller.py` — `check_budget()` is called before processing validator results (Pitfall 2). If the budget is breached, the exit reason is always `EXHAUSTED` or `HUMAN_NEEDED`, never `VALIDATOR_PASSED`. There is no "hopeful exit" — if the validator failed but the budget is exhausted, the loop exits with a non-passed reason. The validator IS the gate; without it, the loop burns tokens without making progress.

### P19

**AlphaSignal 4-condition test: repetition, validator automatable, token budget tolerates waste, agent has senior-engineer tooling.**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:** All four conditions are met for HF to LoongForge adaptation:
1. **Repetition:** Each new model requires the same adaptation process
2. **Validator automatable:** Phase validators (`phase1-verify`, `phase2-conversion`, `loss-diff`, `feature-compat`, `kb-consistency`) are subprocess-invocable
3. **Token budget tolerates waste:** GPU compute dominates cost; loop iteration overhead is marginal
4. **Senior-engineer tooling:** `gh` CLI + Python + `attempts.jsonl` + structured logging = professional-grade toolchain

The loop is justified.

### P20

**Three responsibilities Loop cannot replace: human verification on accept; comprehension debt; cognitive surrender.**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:** Cross-phase checkpoint stays gated (SKILL.md Checkpoint Protocol) — the loop does not auto-advance between phases without user confirmation (unless `autonomous_mode: true`). `comprehension_summary.md` (produced by `skills/adapt/lib/summary_generator.py` at run end) addresses comprehension debt by providing a <=1 page human-readable summary of what the loop did and why. Cognitive surrender is mitigated by the `decision_log.md` per phase.

### P21

**Stage-5: "the laptop is closed" assumption replaces "terminal is open."**

**Source:** se.rpcx.io/12 (Loop Engineering)

**Implementation:** This refactor is single-laptop-open architecture. `--resume` (`skills/adapt/scripts/run.py` `resume_run_dir()`) is sufficient for re-entry after a terminal disconnect. No daemon, supervisor, or systemd service is used. The loop state lives on disk in `loop_state.yml` and `attempts.jsonl`, so any session can pick up where the last one left off.

---

## Synthesized FSM

```
                 ┌──────────────────────────────────────┐
                 ▼                                      │
INIT → PROBE → EDIT → PR → MERGE(base) → VALIDATE       │
                                            │           │
                              ┌─────────────┴──────────┐│
                              │                        ││
                       all_pass=true            all_pass=false
                              │                        ││
                              ▼                        ▼│
                          EXIT(passed)            DIAGNOSE
                                                       │
                                       ┌───────────────┼───────────────┐
                                       │               │               │
                                  code-bug         flaky         wrong-direction
                                       │               │               │
                                       ▼               ▼               ▼
                                   ISSUE → FIX-PR    RERUN-ONLY    EXIT(human_needed)
                                       │               │
                                       ▼               │
                                    MERGE ─────────────┘
                                       │
                                       └── budget? ── exhausted ─→ EXIT(autonomous_blocked)
                                                  │
                                                  remaining → VALIDATE (loop)
```

---

## Hard Do Not Use List

Key prohibitions derived from loop-engineering principles and project constraints:

| Don't | Why | Source |
|-------|-----|--------|
| Webhooks / GitHub App / push receivers | Out of scope; introduces inbound endpoints, hosting | PROJECT.md |
| GitHub Actions to host the loop | Couples loop lifecycle to CI minutes; cannot run GPU validators | PROJECT.md |
| `asyncio` / async `gh` client | Single-run, single-phase-at-a-time; concurrency adds testability cost without benefit | P5, STACK |
| SQLite or any DB for state | Defeats greppability/diffability of `attempts.jsonl` | P1, STACK |
| Retrying validator failures | Validator failure is signal, not transient. Retrying = ignoring signal = "loop without a gate" (P18) | P18 |
| Free-form Claude self-report as exit signal | Violates P3, P10 — only validator output is legitimate | P3, P10 |
| Same sub-agent for Edit and Diagnose | Violates P16 — maker-checker separation is mandatory | P16 |
| Auto-merging fix-PRs without re-running validator | Validates wrong artifact; must rerun on merged commit | REQ-RERUN-01 |
| `/loop` for phase-internal repair | Already forbidden in SKILL.md; phase agents own internal loops | SKILL.md |
| `requests` + raw GitHub REST | Reinvents `gh api`; loses ambient auth | STACK |
| Daemon / supervisor / systemd | Over-engineers laptop-open assumption (P21) | P21 |
| Inline Python repair prompts | Violates P6 (prompts are code); use versioned templates | P6 |
| PyGithub as primary | Heavier dependency; parallel auth to `gh` | STACK |
| Adding "unified validator" | Out of scope per PROJECT.md; existing validator set is sufficient | PROJECT.md |
