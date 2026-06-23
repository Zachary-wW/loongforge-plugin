# DS V4 Acceptance Runbook

This runbook drives the DS V4 (DeepSeek-V4) acceptance run on the GPU machine. It is the second layer of the two-layer acceptance model: local acceptance (ACC-01) is already met; GPU acceptance verifies real validators with real GPU.

## Prerequisites

- GPU machine with CUDA access
- loongforge-plugin repository at branch `refactor/adapt-loop-engineering` checked out
- LoongForge and Loong-Megatron repos cloned with the correct branches
- `gh auth status` OK with `repo` and `workflow` scopes
- Python 3.12+ environment with project dependencies

## Invocation

```bash
loongforge-adapt \
    --hf-impl-url https://github.com/huggingface/transformers \
    --hf-impl-ref main \
    --hf-impl-subpath src/transformers/models/deepseek_v4 \
    --hf-ckpt-url https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base \
    --loongforge-repo https://github.com/Zachary-wW/LoongForge \
    --loongforge-base-ref main \
    --megatron-repo https://github.com/Zachary-wW/Loong-Megatron \
    --megatron-base-ref loong-main/core_v0.15.0 \
    --model-name DeepSeek-V4-Flash-Base \
    <hf_ckpt_local_path>
```

Note: `<hf_ckpt_local_path>` is the local path to the downloaded HF checkpoint on the GPU machine.

## Expected Output

- Run directory created under `adaptation_run_YYYYMMDD_HHMMSS/`
- `run_inputs.yml` with `repos:` and `loop:` blocks
- Preflight passes (gh auth, repo permissions, ckpt reachability)
- Each phase proceeds through the FSM, creating branches, PRs, and issues on LoongForge repo
- `comprehension_summary.md` generated at run completion listing all merged commits (merge_commit_sha per phase)

## Pass Criteria

- All 6 phase validators pass: phase1-verify, phase2-conversion, loss-diff, feature-compat, kb-consistency, plus Phase 0 checks
- Each phase `phaseN_output.yml` contains `status: passed`
- `comprehension_summary.md` generated at run completion listing all merged commits (merge_commit_sha per phase)
- No `escalation.md` files in any phase directory

## Community Version Diff

- Diff target: `TODO: <community-repo-URL>` (placeholder)
- Purpose: compare adaptation output against a known-good community version to catch regressions
