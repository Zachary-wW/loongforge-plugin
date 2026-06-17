---
name: adapt_issue_loop
description: >
  Use when running the local-first issue-driven LoongForge adapt iteration loop,
  creating GitHub issues from Phase 0-2 DS V4 static baseline mismatches,
  driving repair PRs, review, verification, and merge.
---

# /loongforge:adapt_issue_loop — Issue-Driven Adapt Loop

This skill coordinates the local-first issue loop for `/loongforge:adapt`.

Invocation:

```text
/loongforge:adapt_issue_loop --target ds-v4 --run-dir <adapt_run_dir> [--dry-run|--apply]
```

CLI wrapper:

```bash
loongforge-issue-loop <subcommand> [options]
```

## Scope

The MVP runs on a Mac no GPU environment. It validates Phase 0-2 only:

- Phase 0: static artifact completeness against DS V4 baseline facts.
- Phase 1: generated code structure/signature/config/native integration against DS V4 baseline code.
- Phase 2: conversion/tensor mapping coverage against DS V4 baseline conversion facts.

Phase 3 and Phase 4 are deferred in this MVP and must not be reported as passed.

## Baseline Groundtruth

Default target case `ds-v4` uses:

```text
../baidu/hac-aiacc/AIAK-Megatron      @ 12713af0
../baidu/hac-aiacc/AIAK-Training-Omni @ 83e71867
```

## Orchestration Rules

1. Initialize `.loongforge/issue-loop/state.yml` and `phase_goal_contract.yml`.
2. Run or resume `/loongforge:adapt` locally for the enabled phase.
3. Run `loongforge-issue-loop compare-phase` for the current phase.
4. If comparison fails, run `issue-from-report` and `sync-issue`.
5. Repair agent reads exactly one GitHub Issue and creates branch `agent/issue-<id>-<slug>`.
6. Repair agent proves the issue with a failing check or artifact-level evidence before changing code.
7. Repair agent commits and opens or updates one PR linked to the issue.
8. Review agent checks issue scope, diff, tests, comparator report, and merge gate.
9. Merge only when `verify-merge-gate` returns passed and review verdict is approved.
10. After merge, rerun the current phase before advancing.

## Status Semantics

- `passed`: the local no-GPU static comparator and phase artifact gates passed.
- `failed`: an actionable mismatch exists and should become or update a GitHub Issue.
- `deferred`: GPU-only Phase 3/4 validation is outside the MVP.
- `needs-human`: iteration limits, missing baseline, or unreproducible issue blocked autonomy.

## Deterministic CLI Layer

The Python scripts do deterministic transforms only. They do not dispatch agents.
The main Claude session dispatches repair/review agents using the GitHub Issue and PR as task boundaries.

## Repair PR Loop

For each synced GitHub Issue:

1. Fetch the issue body and linked IssueSpec.
2. Create branch `agent/issue-<number>-<short-slug>`.
3. Prove the issue by rerunning the comparator command or by citing artifact-level evidence.
4. Modify only plugin files required by the issue.
5. Run targeted tests and the relevant comparator.
6. Commit with `Fixes #<number>` or `Closes #<number>` in the PR body.
7. Push the branch and create a PR.

## Review and Merge Gate

Review agent must evaluate:

- PR scope matches exactly one linked issue.
- Issue acceptance checklist passes.
- Plugin tests pass.
- Phase artifact gate passes when an artifact exists.
- DS V4 static comparator passes.
- Downstream readiness is not blocked.
- No GPU-only gate is treated as a local blocking gate.

Before merge, write a gate input YAML and run:

```bash
loongforge-issue-loop verify-merge-gate --inputs <gate.yml>
```

Only merge when the command exits 0 and review verdict is `approved`.
