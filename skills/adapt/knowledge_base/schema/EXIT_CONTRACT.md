# LoongForge Adaptation Phase Exit Contract

## Purpose

This document defines how LoongForge adaptation phases exit. Phase completion is determined by each phase's authoritative validator action, not by the agent's subjective judgment that the phase steps look complete.

The contract applies to Phase 1, Phase 2, Phase 3, and Phase 4. Phase 5 uses a lightweight knowledge-base consistency check. Phase 0 does not get a separate exit validator, but later phases may request fallback to Phase 0 when they discover upstream model-analysis defects.

## Authoritative Validator Mapping

| Phase | Authoritative validator | Phase can pass when |
|---|---|---|
| Phase 1 | `phase1-verify` | Trimmed random-init HF vs LoongForge loss alignment passes, and trainability sanity is healthy. Defined by `references/phases/phase1/verify.md` |
| Phase 2 | `phase2-conversion` | Online conversion / bridge roundtrip, offline HF->mcore, offline mcore->HF, and HF roundtrip comparison all pass. Defined by `references/phases/phase2/agent.md` Step 5 |
| Phase 3 | `loss-diff` | Real-weight step-1 forward loss and step 2..N train-step losses align. Defined by `references/phases/phase3/loss_diff.md` |
| Phase 4 | `feature-compat` | All applicable runtime switches and required combinations pass; skipped/non-runtime rows are justified. Defined by `references/phases/phase4/agent.md` Steps 2-7 |
| Phase 5 | `kb-consistency` | Sources YAML, INDEX, and LOG are consistent with the completed run |

## Internal Step Gate

Each phase has mandatory internal steps defined by its phase manual. The active `adapt-phaseN` subagent must enumerate those steps, execute mandatory steps, and record evidence before it can claim top-level `passed`.

See `knowledge_base/schema/STEP_GATE.md` for the required `step_gate` / `steps` fields and enforcement rules.

## Phase Loop

Each validated phase follows this loop:

```text
attempt = 1
while attempt <= max_iterations:
  execute phase work or repair
  run the phase authoritative validator

  if validator.status == passed:
    phase.status = passed
    stop phase loop

  if validator.status == failed:
    repair according to validator failure_gate and diagnosis
    attempt += 1
    continue

  if validator.status == human_needed:
    phase.status = human_needed
    stop and report reason, evidence, and re-entry point

attempt > max_iterations:
  phase.status = human_needed
  reason = exceeded max_iterations
```

A phase must not return top-level `passed` unless its authoritative validator returned `passed` in the latest iteration.

## Status Semantics

Status levels are intentionally separated:

- `phase.status`: terminal phase outcome, only `passed` or `human_needed` in normal mode.
- `attempt.status`: per-repair attempt outcome, one of `passed`, `failed`, or `human_needed`.
- `validator.status`: authoritative validator outcome, one of `passed`, `failed`, or `human_needed`.
- `autonomous_blocked` (autonomous mode only): terminal phase outcome replacing `human_needed` when the agent exhausted all autonomous resolution options.

Semantics:
- `passed`: the authoritative validator action actually passed.
- `failed`: the current attempt/validator can continue repairing and rerun the validator.
- `human_needed`: the agent should stop because the issue requires human input, upstream fallback, external resources, unsupported architecture, or the phase exceeded its iteration budget.

`failed` is a loop signal, not a final phase status or checkpoint signal. The main agent should checkpoint only `passed` and `human_needed` (or `autonomous_blocked` in autonomous mode) phase outcomes.

## Autonomous Mode Phase Loop

When `options.autonomous_mode: true`, the phase loop changes its `human_needed` handling:

```text
attempt = 1
while attempt <= max_iterations:
  execute phase work or repair
  run the phase authoritative validator

  if validator.status == passed:
    phase.status = passed
    stop phase loop

  if validator.status == failed:
    repair according to validator failure_gate and diagnosis
    attempt += 1
    continue

  if validator.status == human_needed:
    attempt autonomous resolution:
      - best-guess fix based on failure_gate and diagnosis
      - degrade to standalone/skip mode when applicable
      - cross-phase local fix if within scope
    if autonomous resolution succeeded:
      attempt += 1
      continue (rerun validator)
    else:
      phase.status = autonomous_blocked
      record evidence, deferred_issues, and blocked reason
      stop phase loop

attempt > max_iterations:
  phase.status = autonomous_blocked
  reason = exceeded max_iterations after autonomous attempts
```

A phase must not return `human_needed` in autonomous mode. The only terminal non-pass status is `autonomous_blocked`.

## Evidence Recording

Evidence supports debugging, reproducibility, and resume. Evidence is not the pass condition by itself; the pass condition is the validation action and its metrics.

Each phase should record validator evidence in its phase result, preferably under `details.validator` or in the validator's existing report:

```json
{
  "validator": {
    "name": "phase1-verify|phase2-conversion|loss-diff|feature-compat|kb-consistency",
    "status": "passed|failed|human_needed",
    "attempt": 1,
    "failure_gate": null,
    "metrics": {},
    "commands": [],
    "logs": [],
    "artifacts": [],
    "diagnosis": null,
    "fallback_phase": null
  }
}
```

Minimum expectations:

- Record the metrics used by the validator.
- Record commands actually executed when practical.
- Record logs or diagnostic paths on failure.
- Record artifacts needed for resume or manual reproduction when practical.
- Set `fallback_phase` explicitly when the current phase cannot safely continue.

## Stale Evidence Rule

If code, configuration, conversion rules, checkpoint output, scripts, or validator inputs change, the affected validator must be rerun. The latest validator result is the only result allowed to determine phase status.

The first implementation enforces this as a process rule. Hash-based input fingerprints may be added later if stale evidence becomes a recurring issue.

## Fallback Semantics

Fallback means the current phase found evidence that an earlier phase must be redone or repaired. Fallback is reported as `human_needed` with `fallback_phase` set to the earlier phase.

Common fallback cases:

- Phase 1 -> Phase 0: `model_spec.yaml` is incomplete or structurally wrong.
- Phase 2 -> Phase 1: generated model code must change to make conversion valid.
- Phase 3 -> Phase 1 or Phase 2: random-init structure validation or conversion validation is no longer valid.
- Phase 4 -> Phase 1, Phase 2, or Phase 3: feature validation exposes model-code, conversion, or baseline precision issues.

### Fallback in Autonomous Mode

In autonomous mode, fallback cannot wait for a human. The subagent must:

1. If the fix is local (e.g., a missing key in convert YAML that this phase can edit), apply it directly and continue.
2. If the fix requires re-running an earlier phase, record it as a `deferred_issue` with the would-be `fallback_phase` and evidence, then continue with remaining non-dependent steps.
3. Return `autonomous_blocked` only when all remaining steps depend on the unresolved fallback.
