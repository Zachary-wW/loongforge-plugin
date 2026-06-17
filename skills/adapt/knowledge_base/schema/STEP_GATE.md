# LoongForge Adaptation Step Gate

## Purpose

This contract makes phase-internal steps enforceable without expanding the Claude Code top-level task list. The top-level task list tracks user-visible phases and gates; each `adapt-phaseN` subagent owns its internal checklist.

## Required Phase Output

Every passed `phases/phaseN_output.yml` must include:

```yaml
step_gate:
  mandatory_steps_complete: true
steps:
  step1:
    status: passed
    evidence: "<artifact, command, or log path>"
  optional_step:
    status: skipped
    required: false
    reason: "not applicable for this model"
```

## Rules

- Mandatory steps come from `references/phases/phaseN/agent.md`.
- Mandatory steps must have `status: passed` and non-empty `evidence`.
- Optional or conditional steps may be skipped only with YAML boolean `required: false` and a concrete `reason`.
- Retries belong in `phases/phaseN/attempts.jsonl`, not in `run_inputs.yml` or `run_state.json`.
- A phase cannot claim top-level `passed` unless `step_gate.mandatory_steps_complete: true` and the phase validator/checks pass.

## Gate Enforcement

`loongforge-phase-gate` enforces this contract for passed phase completion. It does not run the step work, GPU jobs, or agentic validators; it only checks evidence already written by the phase agent.
