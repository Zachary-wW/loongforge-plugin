# HANDOFF -- Local to GPU Machine Portability

## What to Copy

- Git branch: `refactor/adapt-loop-engineering`
- Repository: full `loongforge-plugin` repo (the skill code is all under `skills/adapt/`)
- Planning directory: `.planning/` (contains ROADMAP.md, REQUIREMENTS.md, STATE.md, research/, phases/)
- Run directory (if resuming): the entire `adaptation_run_*` directory from local if a dry-run was already executed

## Environment Setup on GPU Box

- Clone loongforge-plugin: `git clone -b refactor/adapt-loop-engineering <repo-url>`
- Install dependencies: `pip install -e .` (or equivalent for the project)
- Verify `gh auth status` shows `repo` and `workflow` scopes
- Set environment variable `HF_HOME` or `TRANSFORMERS_CACHE` if HF cache is on a non-default path
- Set `LOONGFORGE_REPO_PATH` pointing to the local LoongForge clone (if needed by validators)
- Set `MEGATRON_REPO_PATH` pointing to the local Loong-Megatron clone (if needed by validators)
- Ensure the HF checkpoint is downloaded and accessible at the local path specified in `<hf_ckpt_local_path>`

## How to Resume

First run on GPU box: use the full invocation command from ds_v4_runbook.md.

If interrupted, resume with:
```bash
loongforge-adapt --resume <run_dir>
```

If resuming after a reconciliation mismatch, use:
```bash
loongforge-adapt --resume <run_dir> --from-phase <N>
```

`--from-phase` clears stale phase outputs from Phase N onward and restarts from there. On first resume, `reconcile_remote_state()` verifies every PR/issue id against GitHub; mismatches cause `SystemExit(3)` with hint to use `--from-phase`. On subsequent resume, the same reconciliation applies; idempotency keys prevent duplicate PRs/issues.

## Checkpoint Path Expectations

The HF checkpoint path passed as positional `hf_path` argument must point to a directory containing the model files on the GPU machine's local filesystem. The path is stored in `run_inputs.yml` under `source.hf_ckpt_path`. If resuming from a run directory that was created on a different machine, the checkpoint path may need updating in `run_inputs.yml` manually.

## Acceptance Status

- ACC-01 (local): PASSED (all pytest green, test_loop_e2e.py proves full FSM cycle)
- ACC-02 (GPU runbook): ds_v4_runbook.md
- ACC-03 (handoff): This document
