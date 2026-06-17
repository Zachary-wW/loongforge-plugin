---
name: adapt
description: >
  Use when adapting a HuggingFace model to LoongForge, running the six-phase
  model adaptation workflow, resuming adaptation runs, or coordinating
  LoongForge phase agents and validation gates.
---

# /loongforge:adapt — LoongForge Model Adaptation

This is the plugin entrypoint for the LoongForge adaptation workflow.

Invocation:

```text
/loongforge:adapt <hf_path> [options]
/loongforge:adapt --resume <run_dir> [--from-phase <0|1|2|3|4|5>]
```

Plugin CLI wrapper:

```bash
loongforge-adapt <hf_path> [options]
loongforge-adapt --resume <run_dir> [--from-phase <N>]
```

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

- Use `TaskCreate` / `TaskUpdate` to track Phase 0-5 live progress in the current session.
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

## Six Phases

| Phase | Agent | Objective | Exit Gate |
|---|---|---|---|
| 0 | `adapt-phase0` | HF full parsing, reference contract extraction, optional checkpoint slicing | Phase 0 output checks pass |
| 1 | `adapt-phase1` | Omni network construction and random-init sanity verification | `phase1-verify` passes |
| 2 | `adapt-phase2` | Weight conversion and production checkpoint verification | `phase2-conversion` passes |
| 3 | `adapt-phase3` | Real-weight loss diff verification | `loss-diff` passes |
| 4 | `adapt-phase4` | Feature switch and combination verification | `feature-compat` passes |
| 5 | `adapt-phase5` | Knowledge base update | `kb-consistency` passes |

If phase-specific agents are unavailable, fall back to `general-purpose` and include the matching phase manual path plus the exit contract path in the prompt.

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

