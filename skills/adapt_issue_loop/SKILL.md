---
name: adapt_issue_loop
description: >
  Use when running the local-first issue-driven LoongForge adapt iteration loop.
  After a phase actually passes its own verify gate, compare its generated code
  against DS V4 groundtruth; any remaining diff is a *plugin* defect — file a
  GitHub Issue, drive repair PRs against the plugin, review, merge, rerun the
  phase, until the diff is empty.
---

# /loongforge:adapt_issue_loop — Issue-Driven Adapt Loop

This skill coordinates the local-first issue loop for `/loongforge:adapt`. The loop has **two gates** in fixed order:

- **Gate 1 — Phase verify gate** (`phase1-verify` / `phase2-conversion` / ... ; deterministic post-check via `loongforge-phase-gate`). Grades *this run's output*. Owned by the phase agent's internal repair loop. Never fixed by an issue-loop PR.
- **Gate 2 — Static comparator vs groundtruth**. Runs only after Gate 1 has passed for the phase. A residual diff here means the **plugin** — not the run — is wrong. Mismatches become GitHub Issues against the plugin repo; repair PRs change `skills/adapt/...`, `agents/`, or `bin/`, never the run directory.

Invocation:

```text
/loongforge:adapt_issue_loop --target ds-v4 --run-dir <adapt_run_dir> [--dry-run|--apply]
```

CLI wrapper:

```bash
loongforge-issue-loop <subcommand> [options]
```

## Scope

The MVP is a **static-comparison loop**: it owns **Gate 2 only** (the static comparator) and observes Gate 1 as a precondition. It validates Phase 0-2:

- Phase 0: static artifact completeness against DS V4 baseline facts.
- Phase 1: generated code structure/signature/config/native integration against DS V4 baseline code.
- Phase 2: conversion/tensor mapping coverage against DS V4 baseline conversion facts.

Phase 3 and Phase 4 are deferred in this MVP and must not be reported as passed.

A passing comparator therefore means: the run's verify gate passed, *and* the generated artifacts match groundtruth. A failing comparator with a passing Gate 1 always points to a plugin defect.

## Inputs and Groundtruth

Default target case `ds-v4` uses this original, unadapted base code as the adaptation target input:

```text
~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Megatron      @ 12713af0
~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Training-Omni @ 04500dd5
```

The static comparator groundtruth is the already-adapted DS V4 code:

```text
~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Megatron      @ e5b77017
~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Training-Omni @ 3a16d140
```

Generated code should stay structurally close to this groundtruth while preserving compatibility with the original base code layout.

Additional DS V4 inputs are references only:

```text
checkpoint/tokenizer: https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base
HF code:              https://github.com/huggingface/transformers/tree/main/src/transformers/models/deepseek_v4
Megatron tracker:     https://github.com/NVIDIA/Megatron-LM/issues/4468
```

Do not download checkpoint weights or other large artifacts; use metadata, source paths, and static references only.

## Orchestration Rules

1. Initialize `.loongforge/issue-loop/state.yml` and `phase_goal_contract.yml`.
2. Run or resume `/loongforge:adapt` locally for the enabled phase. The phase agent owns Gate 1: it must reach `phases/phaseN_output.yml` with `status: passed` and pass `loongforge-phase-gate --run-dir <run> --phase <N>`. **Do not run `compare-phase` until Gate 1 has passed for that phase** — comparing an unverified run conflates run-defects with plugin-defects.
3. With Gate 1 green, run `loongforge-issue-loop compare-phase` for the current phase. This is Gate 2.
4. If Gate 2 fails, the defect is in the **plugin**, not in the run. Run `issue-from-report` and `sync-issue` to file a plugin issue.
5. Repair agent reads exactly one GitHub Issue and creates branch `agent/issue-<id>-<slug>`. Changes are scoped to plugin files (`skills/`, `agents/`, `bin/`, `hooks/`, `docs/`); never to the run directory.
6. Repair agent proves the issue with a failing comparator command or artifact-level evidence before changing code.
7. Repair agent commits and opens or updates one PR linked to the issue.
8. Independent reviewer (`adapt-reviewer`) checks issue scope, diff, tests, comparator report, and merge gate.
9. Merge only when `verify-merge-gate` returns passed and the reviewer verdict is `approved`.
10. After merge, rerun `/loongforge:adapt` for the affected phase from a clean state. The new run must clear Gate 1 again before Gate 2 is re-checked.

## Status Semantics

- `passed`: Gate 1 (`loongforge-phase-gate`) and Gate 2 (`compare-phase`) both passed for the phase, in that order.
- `failed`: Gate 2 found an actionable mismatch on a Gate-1-passing run; should become or update a GitHub Issue against the plugin.
- `gate1_failed`: Gate 1 has not yet passed; this is the phase agent's repair loop, not the issue-loop's.
- `deferred`: Phase 3/4 runtime validation is outside the MVP.
- `needs-human`: iteration limits, missing baseline, or unreproducible issue blocked autonomy.

## Deterministic CLI Layer

The Python scripts do deterministic transforms only. They do not dispatch agents.
The main Claude session dispatches repair/review agents using the GitHub Issue and PR as task boundaries.

## Repair PR Loop

For each synced GitHub Issue:

1. Fetch the issue body and linked IssueSpec.
2. Create branch `agent/issue-<number>-<short-slug>`.
3. Prove the issue by rerunning the comparator command (Gate 2) on a Gate-1-passing run, or by citing artifact-level evidence from the comparator report.
4. Modify only plugin files required by the issue. Never modify files under any `runs/<run>/` directory; the run's defects are not the issue-loop's concern.
5. Run targeted tests and the relevant comparator.
6. Commit with `Fixes #<number>` or `Closes #<number>` in the PR body.
7. Push the branch and create a PR.

## Review and Merge Gate

The reviewer is an **independent sub-agent**, not the repair agent. Dispatch the `adapt-reviewer` plugin agent (see `agents/adapt-reviewer.md`) on every repair PR. The repair agent MUST NOT review its own PR.

The reviewer evaluates:

- PR scope matches exactly one linked issue.
- Issue acceptance checklist passes.
- Plugin tests pass.
- Phase artifact gate passes when an artifact exists.
- DS V4 static comparator passes.
- Downstream readiness is not blocked.
- Deferred phase gates (Phase 3/4 runtime validation) are not treated as local blocking gates.

The reviewer's structured output is persisted to:

```text
.loongforge/issue-loop/review_verdicts/issue-<n>.yml
```

Schema lives at `references/review_verdict.md`. The `verdict` field maps to the merge-gate `review_verdict` input as: `approved` → `approved`; any other value (`request_changes`, `block`, `needs_human`) → `changes_requested`.

Before merge, write a gate input YAML and run:

```bash
loongforge-issue-loop verify-merge-gate --inputs <gate.yml>
```

Only merge when the command exits 0 (which requires `review_verdict: approved` from the reviewer's verdict file).
