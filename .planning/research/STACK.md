# STACK.md — Adapt Skill Loop-Engineering Refactor

Project: loongforge-plugin / `skills/adapt` refactor
Mode: Methodology + Tooling (brownfield, single-skill scope)
Researched: 2026-06-22
Overall confidence: HIGH

---

## Part 1 — Loop-Engineering Principles → Design Heuristics

All three rpcx.io articles fetched and quoted; each principle has a one-line application to THIS refactor.

### From `04.html` — Ralph Loop (execution primitive)

| # | Principle | Application |
|---|---|---|
| P1 | "Ralph is a Bash loop." Same prompt re-injected; **state lives on disk, not in context**. | Loop controller is a thin re-entrant Python entrypoint. Re-read `phases/phaseN/attempts.jsonl` + `run_state.json` every iteration; never rely on Claude conversation memory across attempts. |
| P2 | Two exit conditions in OR: explicit `<promise>` match AND a hard `--max-iterations` safety net. | REQ-LOOP-03: every loop has BOTH `validators_all_pass == true` AND `max_attempts_per_phase` (default 5) AND `max_total_attempts` (default 25). |
| P3 | Honesty constraint: completion only when "completely and unequivocally TRUE." | The promise is the validator verdict file, not Claude self-report. `loongforge-phase-gate` reading `phaseN_output.yml` is the only legitimate exit signal. |
| P4 | Prompt 4 principles: clear completion, phased goals, self-correction, escape hatch. | Each phase's loop prompt MUST include `escape_hatch:` — when `attempt_count >= 3 AND no_progress_signal`, write `phases/phaseN/escalation.md` and exit `human_needed`. |
| P5 | Two architectures: in-session (Stop Hook, ralph-wiggum) vs external bash fork (frankbria). | Choose **external-process forking** architecture. Each attempt = fresh `gh`-driven invocation, state reloaded from disk. |
| P6 | "Operator skill matters. Success depends on writing good prompts, not just having a good model." | Phase repair prompts are versioned templates under `skills/adapt/loop_templates/phaseN/repair.md`. Treat prompts as code. |
| P7 | Loop bloat: "max-iterations limits cycles, but cannot prevent moving in the wrong direction." | Diagnose step is mandatory before every Fix-PR. Separate `diagnose` sub-agent classifies as `code-bug | flaky | wrong-direction | needs-human` BEFORE any fix-PR. `wrong-direction` short-circuits to `human_needed`. |

### From `08.html` — Goal Workflow (gate / pipeline discipline)

| # | Principle | Application |
|---|---|---|
| P8 | Pipeline thinking: "no seams between stages." Each stage has explicit input/output contracts. | Loop transitions are **data contracts**, not control flow. Every state transition writes a typed YAML/JSON artifact; next state reads it. Extend existing `phaseN_output.yml` with `loop_state.yml` per phase. |
| P9 | "Steps are auto inside, gated between." | Phase-internal repair loop is fully autonomous. Cross-phase transition stays gated by user (existing `[CHECKPOINT]` protocol). |
| P10 | Acceptance criteria must be objectively testable. | Loop exit promises must reference a specific validator name + status field, e.g. `phase2-conversion.status == "passed" AND phase2-conversion.evidence.numerical_diff < 1e-5`. Free-form Claude verdicts forbidden. |
| P11 | "Treat review output as advisory. Never blindly apply it." | When diagnose sub-agent suggests a fix, the fix-PR template puts the suggestion in the body, not the diff. The Edit agent decides what to change. |
| P12 | Issue-granularity: one Issue = one session. Decompose if acceptance > 5 items. | One GitHub issue = one validator failure = one fix-PR. Multiple distinct failures → multiple issues. (REQ-ISSUE-02.) |
| P13 | Decision-record value: capture "what alternatives existed and why we didn't pick them." | After each successful loop, write `phases/phaseN/decision_log.md` (1–3 bullets) and link from merged PR body. |

### From `12.html` — Loop Engineering (system view)

| # | Principle | Application |
|---|---|---|
| P14 | "Stop prompting agents. Design loops that prompt your agents." | This refactor produces a **loop-controller spec**, not a smarter Phase-N prompt. Skill author = loop author. |
| P15 | Five essentials: Automations · Worktrees · Skills · Plugins/Connectors · Sub-agents · State. | Map: Automations = `--resume` re-entry; Worktrees = N/A (single-run); Skills = `adapt` itself; Connectors = `gh` CLI; Sub-agents = phase-N + diagnose (maker-checker); State = `attempts.jsonl` + `loop_state.yml`. |
| P16 | **Maker-checker separation**: "the model that writes code is too lenient with itself." | Edit/PR-author agent and Diagnose agent are distinct sub-agents with distinct prompts. Diagnose reads validator output + diff + attempts.jsonl; **never writes code**. |
| P17 | Hill-climbing formula: `goal + metric + change + measure = autonomous improvement`. | Each phase loop spec must enumerate all four. Refuse to enter loop if any is missing. |
| P18 | "A loop without a gate is not autonomous, it's a token bonfire." | Validator IS the gate. No "hopeful exit" — if validator failed but `attempt_budget_exhausted`, exit must be `autonomous_blocked`/`human_needed`, NEVER `passed`. |
| P19 | AlphaSignal 4-condition test: repetition, validator automatable, token budget tolerates waste, agent has senior-engineer tooling. | All four met for HF→LoongForge: repeats per new model, validators exist, GPU dominates cost, `gh`+Python+logs = senior-engineer toolchain. **Loop is justified.** |
| P20 | Three responsibilities Loop cannot replace: human verification on accept; comprehension debt; cognitive surrender. | Cross-phase checkpoint stays gated. Output includes a per-run `comprehension_summary.md` (1 page). |
| P21 | Stage-5: "the laptop is closed" assumption replaces "terminal is open." | This refactor is single-laptop-open. Don't over-build for unattended. `--resume` is enough. |

### Synthesized Loop State Machine

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

## Part 2 — 2025/2026 Toolchain Recommendations

### Core Stack

| Concern | Recommendation | Version | Confidence | Rationale |
|---|---|---|---|---|
| GitHub CLI | `gh` CLI as primary driver | `gh >= 2.55.0` | HIGH | Sync model fits "merge then validate"; ambient auth |
| GitHub low-level | `gh api` subcommand for JSON; PyGithub only as escape hatch | PyGithub 2.6.x if needed | HIGH | `gh api graphql` covers PR review state, mergeable, check-runs without Python dep |
| Auth | Re-use ambient `gh auth status`; require `repo` + `workflow` scopes; fail-fast at startup | n/a | HIGH | Preflight `gh auth status` and `gh api repos/Zachary-wW/LoongForge --jq .permissions` |
| Schema validation | Pydantic v2 for `run_inputs.yml`, `phaseN_output.yml`, new `loop_state.yml` | `pydantic>=2.9,<3` | HIGH | Strict mode catches contract drift between phases (P8) |
| Retry/backoff | Tenacity for transient `gh`/network only; NO retry on validator failures | `tenacity>=9.0,<10` | HIGH | Distinguishing transient (network 502) from semantic (validator no) is core to P18 |
| State / durability | Append-only JSONL for `attempts.jsonl` + typed YAML for `loop_state.yml`. **No SQLite.** | stdlib | HIGH | Greppable, diffable, replayable, partial-write safe |
| Process model | Single-process, re-entrant Python entrypoint, fork/exec `gh` per call | n/a | HIGH | Matches Ralph Loop external-process architecture (P5) |
| Sub-agent split | `adapt-phaseN-edit` (existing) + new `adapt-phaseN-diagnose` | n/a | HIGH | Direct application of P16. Diagnose agent has read-only tools + issue-template tool; cannot edit code |
| Loop control templates | Markdown templates with Jinja2 substitution | `Jinja2>=3.1,<4` | MEDIUM | Codifies P6 ("prompts are code") |
| Test framework | pytest + pytest-mock, mock `gh` via `FakeGhClient` | `pytest>=8`, `pytest-mock>=3.14` | HIGH | Inject `GhClient` interface; tests substitute fake; do NOT mock subprocess directly |
| Logging | stdlib `logging` + JSONL audit log per run | n/a | HIGH | One human `loop.log` + one machine `loop_events.jsonl` per run dir |

### Specific Patterns

| Pattern | Where | Confidence |
|---|---|---|
| **GhClient adapter class** wrapping all `subprocess.run(["gh", ...])` | `skills/adapt/lib/gh_client.py` | HIGH |
| **Idempotency keys on PRs/issues**: include `run_id` + `phase` + `attempt` in title; hidden `<!-- adapt-skill: run=... phase=... attempt=... -->` footer | All PR/issue creation paths | HIGH |
| **PR labels**: `adapt-skill`, `phase-N`, `auto-fix`, `auto-base`, `needs-human` | At creation | MEDIUM |
| **Branch naming**: `adapt/<run_id>/phase<N>/attempt<K>` | Both external repos | HIGH |
| **`Fixes #N` linkage** in every fix-PR body | Mandatory | HIGH |
| **Validator-output normalization**: `{status, evidence, diagnostics, suggested_classification}` | `phaseN/validators/` | HIGH |
| **Diagnose classifier output**: enum `{code-bug, flaky, wrong-direction, needs-human}` | `adapt-phaseN-diagnose` | HIGH |
| **Loop budget at TWO levels**: per-phase (`max_attempts_per_phase=5`) + per-run (`max_total_attempts=25`) | `loop_state.yml` | HIGH |
| **`run_inputs.yml` v2 fields**: `hf_impl_url`, `hf_ckpt_url`, `loongforge_repo`, `loong_megatron_repo` | New | HIGH |

---

## Part 3 — Hard "Do Not Use" List

| Don't | Why | Confidence |
|---|---|---|
| Webhooks / GitHub App / push receivers | PROJECT.md Out-of-Scope; introduces inbound endpoints, hosting | HIGH |
| GitHub Actions to host the loop | Couples loop's lifecycle to CI minutes; can't run GPU validators | HIGH |
| `asyncio` / async `gh` client | Single-run, single-phase-at-a-time; concurrency adds testability cost without benefit | HIGH |
| SQLite or any DB for state | Defeats greppability/diffability of `attempts.jsonl` | HIGH |
| **Retrying validator failures** | Validator failure is signal, not transient. Retrying = ignoring signal = "loop without a gate" (P18) | HIGH |
| Free-form Claude self-report as exit signal | Violates P3, P10 | HIGH |
| Same sub-agent for Edit and Diagnose | Violates P16 | HIGH |
| Auto-merging fix-PRs without re-running validator on merged commit | Validates wrong artifact (REQ-RERUN-01) | HIGH |
| `/loop` for phase-internal repair | Already forbidden in current SKILL.md | HIGH |
| `requests` + raw GitHub REST | Reinvents `gh api`; loses ambient auth | HIGH |
| Daemon / supervisor / systemd | Over-engineers laptop-open assumption (P21) | HIGH |
| Inline Python repair prompts | Violates P6 (prompts are code) | MEDIUM |
| PyGithub as primary | Heavier dep, parallel auth | MEDIUM |
| Adding "unified validator" | Out-of-Scope per PROJECT.md | HIGH |

---

## Part 4 — Confidence Summary

| Area | Confidence |
|---|---|
| Loop-engineering principles | HIGH (3 articles fetched; quoted with attribution) |
| Mapping principles → refactor | HIGH (PROJECT.md REQs line up 1:1) |
| Core toolchain (gh, pydantic, tenacity, pytest) | HIGH (stable 2026-06 versions) |
| Architecture (external-process, JSONL state, no SQLite) | MEDIUM-HIGH |
| Sub-agent split (Edit vs Diagnose) | MEDIUM (new to codebase; first iteration needs calibration) |
| Specific budget numbers (5/phase, 25/run) | LOW (heuristic; tune after first 2–3 real runs) |

---

## Part 5 — Roadmap Implications

Suggested refactor phases:

1. **R-Phase 1 — Loop contract & state types** (HIGH). Pydantic models for `run_inputs.yml v2`, `loop_state.yml`, normalized validator output. No behavior. Maps: REQ-INPUT-01/02, P8.
2. **R-Phase 2 — `GhClient` adapter + tests** (HIGH). Subprocess wrapper, idempotency keys, fake client. Maps: REQ-PR-01/02, REQ-ISSUE-01/02, REQ-TEST-01.
3. **R-Phase 3 — Loop controller + state machine** (HIGH). Probe→Edit→PR→Merge→Validate→Diagnose→… with budgets and exits. Maker-checker split. Maps: REQ-LOOP-01/02/03, P2/P16/P18.
4. **R-Phase 4 — Phase template re-author** (MEDIUM). Move repair prompts to `loop_templates/phaseN/`; add escape-hatch sections. Maps: REQ-DOC-01/02, P4/P6.
5. **R-Phase 5 — `--resume` end-to-end + e2e on DeepSeek-V4-Flash** (MEDIUM). Maps: REQ-COMPAT-01.

Phase-ordering rationale: state types must precede controller; GhClient must precede controller; template re-author can ship after controller.

**Open questions for orchestrator:**
- Branch protection / required reviewers on the two external repos?
- Is the "base PR" ever empty (no-op base) or always carrying real code?
- Should fix-PRs target the base PR's branch, or the repo default branch? (Stacked-PR vs flat model.)

---

## Sources

| Source | Type | Confidence |
|---|---|---|
| https://se.rpcx.io/04.html (Ralph Loop) | Article, fetched 2026-06-22 | HIGH |
| https://se.rpcx.io/08.html (Goal Workflow) | Article, fetched 2026-06-22 | HIGH |
| https://se.rpcx.io/12.html (Loop Engineering) | Article, fetched 2026-06-22 | HIGH |
| `.planning/PROJECT.md` | In-repo | HIGH |
| `skills/adapt/SKILL.md` | In-repo | HIGH |
