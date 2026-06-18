# Claude LoongForge Plugin

Claude Code plugin namespace: `loongforge`.

## Skills

- `/loongforge:adapt` — LoongForge HuggingFace-to-LoongForge model adaptation workflow.
- `/loongforge:adapt_eval` — Qualification-gate eval: backup → re-adapt → verdict against `eval/SCOREBOARD`.
- `/loongforge:adapt_issue_loop` — Local-first issue-driven Phase 0-2 adapt iteration loop with GitHub Issue/PR handoff.

## CLI Wrappers

When the plugin is enabled, use the bundled wrappers from `bin/`:

```bash
loongforge-adapt <hf_path> [options]
loongforge-adapt --resume <run_dir> [--from-phase <N>]
loongforge-phase-gate --run-dir <run_dir> --phase <N>
loongforge-adapt-eval <family> --hf-path <path> [--steps 10] [--keep-deleted]
loongforge-issue-loop init --target ds-v4 --repo Zachary-wW/loongforge-plugin
loongforge-issue-loop compare-phase --phase 0 --run-dir <run_dir>
loongforge-issue-loop sync-issue --issue-spec <issue.yml> --dry-run
```

## Issue-Driven Adapt Loop

`/loongforge:adapt_issue_loop` is a local-first iteration loop for Phase 0-2 DS V4 adaptation. It runs in two gates per phase: first the phase agent's own verify gate (`loongforge-phase-gate`), then the static comparator against DS V4 groundtruth. A comparator mismatch on a verify-passed run indicates a **plugin defect** — the loop writes IssueSpec files and creates or updates GitHub Issues against the plugin repo.

For DS V4, the original unadapted input code lives under `~/workspace/agent_skills/tmp/baidu/hac-aiacc/`. The static comparator groundtruth is the already-adapted code under `~/workspace/debug/0616/baidu/hac-aiacc/`; generated code should stay structurally close to that groundtruth.

Dry-run example:

```bash
loongforge-issue-loop run-dry \
  --plugin-root . \
  --repo Zachary-wW/loongforge-plugin \
  --phase 0 \
  --generated-root <run_dir>/phases/phase0 \
  --baseline-root ~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Megatron \
  --baseline-root ~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Training-Omni
```

For DS V4, treat `https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base` as the checkpoint/tokenizer reference URL only. Do not download the large checkpoint weights; use static metadata/source references and the HF/Megatron reference URLs instead.

Real issue sync example:

```bash
loongforge-issue-loop sync-issue \
  --repo Zachary-wW/loongforge-plugin \
  --issue-spec .loongforge/issue-loop/issue_specs/<issue>.yml \
  --apply
```

## Phase Agents

The plugin provides phase-specific agents:

| Phase | Agent |
|---|---|
| 0 | `adapt-phase0` |
| 1 | `adapt-phase1` |
| 2 | `adapt-phase2` |
| 3 | `adapt-phase3` |
| 4 | `adapt-phase4` |
| 5 | `adapt-phase5` |

Each agent is a thin role wrapper around `skills/adapt/references/phases/phaseN/agent.md`. Phase manuals remain the detailed source of truth.

## Validation Gate

`bin/loongforge-phase-gate` checks whether a phase has a passed output artifact:

```bash
claude-loongforge-plugin/bin/loongforge-phase-gate --run-dir <run_dir> --phase <N>
```

The gate is deterministic and checks passed phase completion only. It does not run runtime validators or agentic validators. Phase agents run the validators and write `phaseN_output.yml`; the gate only checks those artifacts. Do not invoke it for `human_needed` or `autonomous_blocked` checkpoints.

Hook docs and an example are provided at:

```text
hooks/README.md
hooks/task_completed_phase_gate.example.json
```

They are not enabled by default. Enable them only after deciding how phase tasks encode `run_dir` and `phase` in your local Claude Code setup.

## State Files

Authoritative state:

```text
run_inputs.yml
phases/phaseN_output.yml
phases/phaseN/attempts.jsonl
```

Legacy run-dir compatibility:

```text
run_state.json
phases/phaseN/output.yml
```

`run_state.json` is supported only to resume older run directories and backfill `run_inputs.yml`; it is not the plugin orchestration source of truth. Legacy `phases/phaseN/output.yml` may be read for status display, but `loongforge-phase-gate` requires the authoritative `phases/phaseN_output.yml` handoff.
