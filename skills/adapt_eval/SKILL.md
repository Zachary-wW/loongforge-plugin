---
name: adapt_eval
description: >
  Use when running /loongforge:adapt_eval to qualify a new revision of /loongforge:adapt.
  Backs up an already-adapted family, reruns adapt from scratch, and emits a
  PASS/REGRESSED/INVALID/BASELINE verdict against the prior scoreboard entry.
---

# /loongforge:adapt_eval — LoongForge Adapt Qualification Gate

## Purpose

Each iteration of `/loongforge:adapt` must answer: did this revision get
better than the last? `/loongforge:adapt_eval` enforces that question by:

1. Capturing a 10-step baseline loss curve from the *currently adapted* code.
2. Wiping the family with `backup-model`.
3. Re-running `/loongforge:adapt` from scratch to regenerate the family.
4. Capturing the same 10 steps on the regenerated code.
5. Running `omni-reviewer` for static quality + DIVERGE root cause.
6. Emitting a verdict against the prior `eval/SCOREBOARD.json` entry.

The deterministic transforms (autonomy parsing, loss diff, verdict) live in
`scripts/run.py`. The agent dispatch lives **in this file** and is executed
by the main Claude agent.

## Reading Order

1. This file.
2. `../adapt/references/tools/backup-model/SKILL.md`.
3. `../adapt/references/tools/omni-reviewer/SKILL.md`.
4. `docs/superpowers/specs/2026-06-10-loongforge-adapt-eval-design.md` — design doc.

## Invocation

```text
/loongforge:adapt_eval <family> --hf-path <path> [--steps 10] [--keep-deleted]
```

CLI wrapper: `bin/loongforge-adapt-eval` → `python3 skills/adapt_eval/scripts/run.py`.

## Orchestration

Sub-commands must be invoked in Step order. Calling `compute-verdict` before
the upstream sub-commands have populated `eval_run_inputs.yml` degrades to
INVALID with explicit `verdict_reasons`; it is not enforced as an error.

Each `>>> run` block is a deterministic CLI call. Each `>>> dispatch` block is
a sub-agent invocation. The agent must wait for each call to finish before
proceeding to the next.

### Step 0 — Pre-check

- Confirm `git status --porcelain` is empty. If not, ABORT and ask the user
  to commit or stash.
- Resolve `<plugin_commit>` = `git rev-parse HEAD` from the plugin repo root.

### Step 1 — Init eval run

```text
>>> run
loongforge-adapt-eval init <family> --hf-path <hf_path> --steps <steps> \
                       --plugin-commit <plugin_commit> \
                       --eval-root <plugin_root>/eval
```

Capture the printed `<eval_run_dir>` path.

### Step 2 — Capture baseline loss (BEFORE backup)

Pick `<script>` = first `examples/<family>/pretrain/*.sh` that finishes ≤ N
steps in a reasonable time. The orchestrator runs the script and tees stdout:

```text
>>> bash
bash <script> 2>&1 | tee <eval_run_dir>/baseline_train.log
```

Then record the parsed losses:

```text
>>> run
loongforge-adapt-eval record-loss <eval_run_dir> --label baseline \
                       --log <eval_run_dir>/baseline_train.log
```

If `record-loss` exits non-zero → write an INVALID eval_report (Step 6) and stop.

### Step 3 — Backup + delete

Dispatch `backup-model` as a sub-agent (it lives under
`skills/adapt/references/tools/backup-model/`):

```text
>>> dispatch
agent: general-purpose
prompt: |
  Read skills/adapt/references/tools/backup-model/SKILL.md and execute it
  with these arguments:
    --family <family>
    --backup-root <eval_run_dir>/backup
  Return the manifest.json path on success.
```

Then record the manifest into eval state:

```text
>>> run
loongforge-adapt-eval set-backup-info <eval_run_dir> \
                       --manifest <eval_run_dir>/backup/<family>/<ts>/manifest.json
```

### Step 4 — Run /loongforge:adapt

```text
>>> dispatch
agent: general-purpose (or adapt-phase0..5 chain per skills/adapt/SKILL.md)
prompt: |
  Run /loongforge:adapt with:
    hf_path = <hf_path>
    --run-dir <eval_run_dir>/adapt_run
  Follow skills/adapt/SKILL.md exactly. Return when all phases complete or
  one returns human_needed.
```

Snapshot the autonomy result:

```text
>>> run
loongforge-adapt-eval set-adapt-run <eval_run_dir> \
                       --adapt-run-dir <eval_run_dir>/adapt_run
```

### Step 5 — Capture new loss + omni-reviewer

```text
>>> bash
bash <eval_run_dir>/adapt_run/examples/<family>/pretrain/<same_script> \
    2>&1 | tee <eval_run_dir>/new_train.log
```

(If the regenerated script lives under the repo's `examples/<family>/`
instead of under `adapt_run/`, use that path; the script must be the same
**name** as Step 2.)

```text
>>> run
loongforge-adapt-eval record-loss <eval_run_dir> --label new \
                       --log <eval_run_dir>/new_train.log
```

```text
>>> dispatch
agent: general-purpose
prompt: |
  Read skills/adapt/references/tools/omni-reviewer/SKILL.md and execute:
    --family <family>
    --backup-path <eval_run_dir>/backup/<family>/<ts>/
    --run-dir <eval_run_dir>/adapt_run
  Write the report to <eval_run_dir>/omni_review_report.json.
```

```text
>>> run
loongforge-adapt-eval set-omni-review <eval_run_dir> \
                       --report <eval_run_dir>/omni_review_report.json
```

### Step 6 — Compute verdict + persist

```text
>>> run
loongforge-adapt-eval compute-verdict <eval_run_dir>
```

This writes `eval_report.{json,md}` and (when not INVALID) appends
`eval/SCOREBOARD.{md,json}`.

### Step 7 — Restore

Default:

```text
>>> run
loongforge-adapt-eval restore <eval_run_dir>
```

When the user passed `--keep-deleted`, instead:

```text
>>> run
loongforge-adapt-eval restore <eval_run_dir> --keep-deleted
```

## Failure Handling

| Step | Failure | Action |
|---|---|---|
| Step 0 | Dirty git tree | ABORT immediately, no eval_run_dir created |
| Step 2 | baseline loss < N steps | mark INVALID via compute-verdict (no scoreboard append) |
| Step 3 | backup-model returns non-zero | ABORT, no scoreboard append |
| Step 4 | adapt human_needed | continue; autonomy will reflect it |
| Step 5a | new loss < N steps | mark INVALID via compute-verdict |
| Step 5b | omni-reviewer fails | mark INVALID via compute-verdict |
| Step 7 | git revert leaves dirty tree | warning recorded in eval_run_inputs.yml.restore.warnings, do NOT auto-clean |

## What `/loongforge:adapt_eval` does NOT do

- Does **not** write to `knowledge_base/LOG.md`. SCOREBOARD is the eval log.
- Does **not** modify `phaseN_output.yml` schemas. It is read-only on adapt outputs.
- Does **not** retry on transient GPU failures. The orchestrator surfaces
  the error; the user re-runs.
