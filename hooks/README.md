# LoongForge Adapt Hook Examples

The files in this directory are examples, not enabled plugin hooks.

## Phase Completion Gate

`task_completed_phase_gate.example.json` shows how to call:

```bash
loongforge-phase-gate --run-dir "$LOONGFORGE_ADAPT_RUN_DIR" --phase "$LOONGFORGE_ADAPT_PHASE"
```

Use it only after your local Claude Code task naming or hook adapter can provide:

- `LOONGFORGE_ADAPT_RUN_DIR`: adaptation run directory containing `run_inputs.yml`.
- `LOONGFORGE_ADAPT_PHASE`: phase number `0` through `5`.

The hook is a pass gate only. Invoke it when a phase task is being marked complete as `passed`; do not use it for `human_needed` or `autonomous_blocked` checkpoints.

Recommended task naming convention for an adapter:

```text
LoongForge adapt phase <N> [run_dir=<path>]
```

The adapter should extract `<N>` and `<path>`, set the environment variables above, then run the gate command.
