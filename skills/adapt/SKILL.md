---
name: adapt
description: >
  Use when adapting a HuggingFace model to LoongForge, running the seven-phase
  model adaptation workflow with optional loop-engineering mode (repos: gated
  closed-loop PR/issue/merge/validate cycle on external GitHub repos until all
  phase validators pass), resuming adaptation runs, or coordinating LoongForge
  phase agents and validation gates.
---

# /loongforge:adapt — LoongForge Model Adaptation

This skill operates in two modes. When `repos:` is present in `run_inputs.yml`, it runs as a loop-engineering system: every code change goes through a closed loop on external GitHub repos until all phase validators pass. When `repos:` is absent, legacy behavior runs unchanged (COMPAT-01).

## Loop-First Architecture

When `repos:` is present in `run_inputs.yml`, the skill operates as a loop-engineering system: every code change goes through a closed loop on external GitHub repos (LoongForge and Loong-Megatron) until all phase validators pass. The loop does not adapt the model — it adapts the plugin's own bugs out.

### Three Nested Loops

| Layer | Scope | Coordination Bus |
|-------|-------|-------------------|
| Inner | Phase-internal self-repair (`attempts.jsonl`) | Disk files |
| Middle | GitHub PR/issue cycle (loop controller) | GitHub (`gh` CLI) |
| Outer | Multi-model replay (future) | Run directory |

### 12-State FSM

The loop controller (`loop_controller.py`) drives the following state machine:

```
PROBE -> EDIT -> PR -> MERGE_BASE -> VALIDATE
    -> (DIAGNOSE -> ISSUE -> FIX_PR -> REVIEW -> MERGE_FIX -> RERUN)*
    -> EXIT
```

FSMState values (from `loop_controller.py`):

- `probe` -- initial state, reads run state from disk
- `edit` -- agent performs code changes
- `pr` -- create branch and open base PR
- `merge_base` -- merge the base PR
- `validate` -- run the phase validator
- `diagnose` -- classify the validator failure (read-only)
- `issue` -- open a GitHub issue for the failure
- `fix_pr` -- advance attempt, create fix branch and fix-PR
- `review` -- advisory review of fix-PR
- `merge_fix` -- merge the fix-PR
- `rerun` -- re-run the phase validator after fix merge
- `exit` -- loop terminates

ExitReason values (from `loop_controller.py`):

- `validator_passed` -- validator passed on first attempt (no fix needed)
- `validator_passed_after_fix` -- validator passed after one or more fix cycles
- `exhausted` -- budget exhausted before validator passed
- `escalated` -- loop escalated to human (wrong-direction or needs-human)
- `base_only` -- loop completed with only a base PR (no fix-PR cycle)
- `human_needed` -- human intervention required (wrong-direction, needs-human, or budget escalation)

### Maker-Checker Split

Edit/PR-author agent and Diagnose agent are distinct sub-agents (P16). The Diagnose agent is read-only: it reads validator output, attempts history, and diff summaries, but never writes code. It classifies failures as one of four categories (from `diagnose_classifier.py` DiagnoseClassification):

- `code-bug` -- structured failure with identifiable root cause
- `flaky` -- validator result inconsistent across reruns
- `wrong-direction` -- 3+ consecutive attempts with same failure signature; short-circuits to `human_needed`
- `needs-human` -- free-text-only failure or unclassifiable; requires human intervention

`wrong-direction` short-circuits to `human_needed` and writes `phases/phaseN/escalation.md`.

### Three-Axis Budget

The loop enforces a three-axis termination budget (from `schema.py` LoopBudget):

| Axis | Default | Ceiling | Enforcement |
|------|---------|---------|-------------|
| `max_attempts_per_phase` | 5 | 50 | Per-phase attempt count |
| `max_attempts_per_run` | 25 | 500 | Total attempts across all phases |
| `max_wallclock_minutes` | 240 | 10,080 | Elapsed wall-clock time since run start |

Any axis tripping forces exit reason `exhausted` or `human_needed`, never `passed`. Budget is checked before processing validator results (Pitfall 2). The loop never exits with a "hopeful pass" -- if the validator failed but the budget is exhausted, the exit is always a non-passed reason (P3, P18).

### GitHub as Coordination Bus

PRs, issues, and merges coordinate the loop across processes and sessions. This is NOT an in-session agent loop. Each attempt is a fresh `gh`-driven invocation; state is reloaded from disk (`loop_state.yml` + `attempts.jsonl`) every iteration (P1, P5). The loop controller is a single-process, re-entrant Python entrypoint that forks `gh` CLI calls via `GhClient`.

## When NOT to Use This Loop

The loop-engineering mode adds overhead (PR/issue creation, merge cycles, validator reruns). Do not activate it when:

- **Trivial fixes**: one-line config changes with known validators that always pass
- **No validator exists**: the target phase has no phase validator to serve as the loop gate (P18)
- **Single-run, no-replay**: scenarios where manual commit-and-push suffices and no closed-loop verification is needed
- **Full local write access**: cases where the model adapter has full local write access to the target repo and does not need PR-based coordination

In these cases, run without `repos:` in `run_inputs.yml` to use legacy behavior.

## Loop Invocation

### repos: Gated Behavior

When `repos:` is present in `run_inputs.yml`, loop engineering is active. When absent, legacy behavior runs unchanged (COMPAT-01). The four URL inputs activate the loop:

```bash
loongforge-adapt <hf_path> \
  --hf-impl-url <url> --hf-impl-ref <ref> --hf-impl-subpath <path> \
  --hf-ckpt-url <url> --hf-ckpt-revision <rev> \
  --loongforge-repo <url> --loongforge-base-ref <ref> \
  --megatron-repo <url> --megatron-base-ref <ref>
```

All four URL flags (`--hf-impl-url`, `--hf-ckpt-url`, `--loongforge-repo`, `--megatron-repo`) must be provided together, or none at all.

### --dry-run Flag

When `--dry-run` is specified, `FakeGhClient` is selected. No live `gh` calls are made, no real PRs or issues are created, and no GPU validators run. This mode validates URL shape, schema, and preflight checks without side effects.

### --resume Flag

When `--resume <run_dir>` is specified, the controller reconstructs FSM state from disk (`LoopState.from_disk` reads `loop_state.yml` + `attempts.jsonl` tail) and reconciles remote PR/issue state against `gh` (RESUME-01, RESUME-02). Use `--from-phase <N>` to reset from a specific phase and skip reconciliation.

## End-of-Run Housekeeping

At run end, the following steps MUST be performed in order:

### 1. Summary Generation (DOC-04)

Invoke summary generation BEFORE any label verification:

```bash
python3 skills/adapt/lib/summary_generator.py --run-dir <run_dir>
```

This produces:
- `<run_dir>/comprehension_summary.md` -- per-run summary (<=1 page) addressing comprehension debt (P20)
- `<run_dir>/phases/phaseN/phaseN_summary.md` -- per-executed-phase summary

This step is mandatory per DOC-04. It runs in both normal and `--dry-run` modes since it reads disk state only.

### 2. Close Auxiliary Issues

On run completion, all auxiliary bot-created issues should be closed with a summary comment linking the run digest. Use the `close_issue` method with a closing summary comment.

### 3. Label Verification (ROADMAP Criterion 4)

Bot PRs/issues must consistently carry labels: `loongforge-adapt`, `run-<id>`, `phase-<N>`. Run an end-of-run housekeeping verification:

```bash
python3 skills/adapt/lib/housekeeping_check.py --run-dir <run_dir> --repo <loongforge_repo>
```

This exits 0 if every bot-created PR and issue has the required labels and no stranded issues remain. It exits 1 on any failure (unlabeled artifacts or stranded issues). This satisfies ROADMAP success criterion 4 ("exits non-zero on any unlabeled or stranded artifact").

**In `--dry-run` mode, skip the housekeeping verification step** since no real GitHub artifacts exist (FakeGhClient PR/issue numbers are not real). When running from a dry-run session, pass `--dry-run` to `housekeeping_check.py`:

```bash
python3 skills/adapt/lib/housekeeping_check.py --run-dir <run_dir> --repo <loongforge_repo> --dry-run
```

Summary generation still runs in dry-run mode since it reads disk state only.

### 4. Close Stranded Issues

Close any stranded auxiliary issues identified by the housekeeping check that were not already closed in step 2.

## Reading Order

1. This file.
2. `knowledge_base/schema/EXIT_CONTRACT.md` and `knowledge_base/schema/STEP_GATE.md`.
3. The current phase manual under `references/phases/phaseN/agent.md`.
4. Phase validator sub-docs on demand:
   - Phase 1: `references/phases/phase1/verify.md`
   - Phase 2: `references/phases/phase2/verify.md`
   - Phase 3: `references/phases/phase3/loss_diff.md`
5. `knowledge_base/INDEX.md` for domain references, templates, traps, and QRH docs.

## Claude Code Harness Reuse

- Use `TaskCreate` / `TaskUpdate` to track Phase 0-6 live progress in the current session.
- Use phase-specific plugin agents when available; fallback to `general-purpose` only when needed.
- `/loop` may be used only for coarse external waiting such as K8s/GPU jobs or remote CI-like validation.
- Do not use /loop for phase-local repair loops; active phase agents own those loops and must write `phases/phaseN/attempts.jsonl`.

## Input Schema Markers

- Passed field: `options.gpu_execution_mode` (`"local_gpu"` | `"k8s"`)
- K8s fields live under `options.k8s_yaml_path` and `options.k8s_launch_cmd`.

## State Source of Truth

Authoritative state:

```text
run_inputs.yml
phases/phaseN_output.yml
phases/phaseN/attempts.jsonl
```

Legacy compatibility only:

```text
run_state.json
phases/phaseN/output.yml
```

Do not add new orchestration fields to `run_state.json` unless needed for backward compatibility. Legacy `phases/phaseN/output.yml` may be read for status display, but `loongforge-phase-gate` requires the authoritative `phases/phaseN_output.yml` handoff.

## Startup Runner

The runner initializes or resumes a durable run directory. It does not execute phase agents.

```bash
loongforge-adapt <hf_path> [--model-name <name>] [--run-dir <dir>]
loongforge-adapt --resume <run_dir> [--from-phase <N>]
```

## Seven Phases

| Phase | Agent | Objective | Exit Gate |
|---|---|---|---|
| 0 | `adapt-phase0` | Dual-Reference Bridge Analysis and Checkpoint Slicing | Phase 0 output checks pass |
| 1 | `adapt-phase1` | Omni network construction and random-init sanity verification | `phase1-verify` passes |
| 2 | `adapt-phase2` | Weight conversion and production checkpoint verification | `phase2-conversion` passes |
| 3 | `adapt-phase3` | Real-weight loss diff verification | `loss-diff` passes |
| 4 | `adapt-phase4` | Performance profiling and tuning (nsys-profiler + performance-tuner) | `performance-tuning` passes |
| 5 | `adapt-phase5` | Feature switch and combination verification | `feature-compat` passes |
| 6 | `adapt-phase6` | Knowledge base update | `kb-consistency` passes |

If phase-specific agents are unavailable, fall back to `general-purpose` and include the matching phase manual path plus the exit contract path in the prompt.

### Phase 0 Detail

Phase 0 produces three core deliverables: `hf_analysis.yaml` (HF side), `reference_impl_analysis.yaml` (Megatron side), `bridge_mapping.yaml` (component bridge mapping with weight maps and gap detection). These replace the former single `model_spec.yaml` output. The `bridge_mapping.yaml` is the primary artifact consumed by downstream phases 1-6.

Phase 0 does NOT use the Loop FSM — it runs a quality inner loop (max 3 rounds) instead.

## Phase Dispatch Rules

For each phase:

1. Create or update a Claude Code task for live progress tracking.
2. Dispatch the matching phase agent, passing `run_dir` and required fields from `run_inputs.yml` and prior `phaseN_output.yml` files.
3. The phase agent reads its `references/phases/phaseN/agent.md` manual, `knowledge_base/schema/EXIT_CONTRACT.md`, and `knowledge_base/schema/STEP_GATE.md`.
4. The phase agent runs its validator or output contract check internally.
5. Final phase.status: `passed` or `human_needed` in normal mode.
6. Internal attempt.status: `passed`, `failed`, or `human_needed`; validator.status uses the same values.
7. `failed` is a repair-loop signal, not a final checkpoint status.
8. Logs stay under `phases/phaseN/logs/` where applicable.
9. Attempts stay under `phases/phaseN/attempts.jsonl`.
10. Write `phases/phaseN_output.yml` before reporting a phase checkpoint.

## Phase-internal Step Enforcement

Do not create top-level Claude Code tasks for every phase-internal step by default. Use the task list for user-visible orchestration (`Phase N`, `Phase N gate`, cross-phase blockers). Inside a phase, the active `adapt-phaseN` subagent owns its checklist.

Each phase agent reads `knowledge_base/schema/STEP_GATE.md`, executes mandatory steps from its phase manual, records retries in `phases/phaseN/attempts.jsonl`, and writes `step_gate` / `steps` evidence into `phases/phaseN_output.yml`.

A phase must not return top-level `passed` unless all mandatory internal steps are complete and the authoritative validator/checks pass. `loongforge-phase-gate` blocks completion when step evidence is missing or incomplete.

## Validation Hook Concept

Validators run inside phase agents. Hooks only enforce that the step gate and validator evidence exist and passed.

Use `loongforge-phase-gate` as a deterministic gate:

```bash
loongforge-phase-gate --run-dir <run_dir> --phase <N>
```

The gate checks `phases/phaseN_output.yml` for passed phase completion only. It does not run GPU jobs or agentic reviews, and it should not be invoked for `human_needed` or `autonomous_blocked` checkpoints.

Hook docs and a `TaskCompleted` example are provided at:

```text
hooks/README.md
hooks/task_completed_phase_gate.example.json
```

Do not enable them blindly. First standardize how phase tasks record `run_dir` and phase number in your Claude Code setup.

## `/loop` Boundary

Use `/loop` only for coarse external waiting, such as K8s/GPU jobs or remote CI-like validation that Claude Code cannot observe directly.

Do not use /loop for phase-local repair loops. Phase-local loops are owned by the active phase agent and must record attempts in `phases/phaseN/attempts.jsonl`.

Do not use `/loop` to poll Claude Code background tasks; the harness notifies when tracked tasks complete.

## Bulk Log Externalization (SAFE-03)

Phase agents MUST externalize bulk log content (validator stdout/stderr, training logs, NCCL traces) to files under `phases/phaseN/logs/`, and quote only the relevant **excerpts** (last 50-200 lines or matched regex windows) into chat context. Reason: in-session context bloat (PITFALLS.md #19) degrades agent quality on long runs. Reference logs by relative path; never paste multi-MB blobs.

## Checkpoint Protocol

After a phase returns final `passed` or `human_needed`, summarize:

```text
[CHECKPOINT] Phase N -- <Phase Name>
Status: PASSED / HUMAN_NEEDED
Artifact: <run_dir>/phases/phaseN_output.yml
Validator: <name/status or Phase 0 checks>
Next: continue | pause | abort
```

Only proceed to the next phase after user confirmation unless `options.autonomous_mode: true`.

## Autonomous Mode

When `options.autonomous_mode: true`, phase agents return only `passed` or `autonomous_blocked`, never final `human_needed` or `failed`. They exhaust repair budgets internally and record deferred issues in their phase output.
