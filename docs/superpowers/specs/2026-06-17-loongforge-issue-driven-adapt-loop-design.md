# LoongForge Issue-Driven Adapt Loop Design

Date: 2026-06-17
Status: Draft for user review
Repository: `Zachary-wW/loongforge-plugin`

## 1. Goal

Build a local-first, issue-driven iteration loop for `/loongforge:adapt`.

The loop runs adaptation phases locally. Whenever a phase, checker, reviewer, or downstream phase finds an actionable problem that blocks the current goal, the system creates or updates a GitHub Issue. A repair agent reads that issue, fixes the plugin locally on an issue-scoped branch, opens a PR, and an independent review/verification agent checks whether the issue is actually resolved. If all gates pass, the PR is merged automatically. The phase is then rerun. This repeats until the enabled phase goals are satisfied or the loop reaches a bounded human handoff state.

The first target case is DS V4. The original unadapted input code comes from:

- `~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Megatron/` at `12713af0`
- `~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Training-Omni/` at `04500dd5`

Baseline groundtruth for static comparison is the already-adapted DS V4 code at:

- `~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Megatron/` at `e5b77017`
- `~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Training-Omni/` at `3a16d140`

The checkpoint/tokenizer input is the reference URL `https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base`; the local no-GPU MVP must not download large checkpoint artifacts. Reference code comes from HuggingFace DeepSeek V4 and NVIDIA Megatron-LM issue #4468.

The local machine is a Mac without GPU. Therefore the MVP validates Phase 0, Phase 1, and Phase 2 through static artifact/code/conversion comparison against groundtruth code, not runtime GPU loss or training checks. In this mode, the loop writes separate static-readiness reports and must not claim GPU-only validators passed solely because static comparison passed. Phase 3 and Phase 4 are deferred for this MVP.

## 2. Non-goals

The MVP does not implement:

- GPU training, random-init loss alignment, real-weight loss diff, or runtime feature matrix validation.
- Phase 3 and Phase 4 execution.
- GitHub Actions or remote runner orchestration.
- Parallel repair of multiple issues.
- Slack, Discord, CI-feed, or community feedback scanning.
- Fully automatic multi-repo code modifications outside the plugin unless explicitly required later.

## 3. Core Principles

1. **Local execution, GitHub ledger**: adapt, comparator, repair, review, and verification run locally; GitHub stores issues, PRs, review comments, merge history, and traceability.
2. **Issue as the repair unit**: every repair branch and PR must be scoped to one GitHub Issue. New unrelated findings create or update separate issues.
3. **Proof before repair**: the repair agent must reproduce the problem or provide artifact-level proof before changing code.
4. **Maker-checker split**: the agent that repairs an issue cannot be the only judge that it is fixed.
5. **Bounded autonomy**: every issue and phase has iteration limits and a `needs-human` escape path.
6. **Mutable goal contracts**: phase goals are versioned artifacts. If downstream failures show an upstream goal is incomplete, the goal contract itself is repaired through the same issue/PR/review loop.
7. **No-GPU honesty**: runtime GPU gates are explicitly deferred, never silently treated as passed.

## 4. High-Level Architecture

```text
Local Phase Runner
  Runs /loongforge:adapt Phase N locally and reads run_dir phase artifacts.

Problem Detector
  Turns verifier failures, comparator mismatches, downstream fallbacks, and review failures into structured IssueSpec records.

Baseline Comparator
  Compares Phase 0-2 outputs against DS V4 baseline code/facts from AIAK-Megatron and AIAK-Training-Omni.

GitHub Issue Manager
  Creates or updates GitHub Issues using a dedup key.

Repair Agent
  Reads one issue, creates an issue branch, proves/reproduces the problem, fixes plugin code/tests/docs, and pushes a PR.

PR Manager
  Creates or updates PRs and connects them to issues.

Review Agent
  Independently checks the PR diff, issue checklist, phase artifacts, comparator report, and local verification.

Verification Gate
  Blocks merge unless all local no-GPU MVP gates pass.

Loop State Store
  Persists phase, issue, PR, iteration, report, and resume state.
```

## 5. Core State Machine

```text
PHASE_RUNNING
  -> PHASE_GOAL_CHECK
  -> PHASE_GOAL_FAILED
  -> ISSUE_CREATED_OR_UPDATED
  -> REPAIR_BRANCH_CREATED
  -> REPAIR_SUBMITTED_AS_PR
  -> REVIEW_AND_VERIFY
     -> pass: AUTO_MERGE -> ISSUE_CLOSED -> PHASE_RETRY
     -> fail: ISSUE_UPDATED_WITH_EVIDENCE -> REPAIR_AGAIN
     -> max_iterations_exceeded: NEEDS_HUMAN
```

Phase-level loop:

```text
for phase in [0, 1, 2]:
  run phase locally
  run artifact gate + baseline static comparator + downstream readiness gate
  while phase goal is not met:
    create/update GitHub issue
    run issue-scoped repair loop
    review and verify PR
    merge when all gates pass
    rerun current phase
  continue to next enabled phase

phase3, phase4: deferred with explicit no-GPU reason
```

## 6. Local State and Artifacts

Use a local state directory:

```text
.loongforge/issue-loop/
  state.yml
  phase_goal_contract.yml
  issue_specs/
  verification_reports/
  comparator_reports/
```

Example `state.yml`:

```yaml
repo: Zachary-wW/loongforge-plugin
mode: local_execution_github_issues
target_case: ds_v4
baseline:
  description: "Groundtruth code that generated artifacts should match structurally."
  megatron:
    path: ~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Megatron
    commit: e5b77017
  omni:
    path: ~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Training-Omni
    commit: 3a16d140
inputs:
  base_code:
    description: "Original unadapted Megatron/Omni code used as the adaptation target input."
    megatron:
      path: ~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Megatron
      commit: 12713af0
    omni:
      path: ~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Training-Omni
      commit: 04500dd5
  hf_checkpoint_and_tokenizer_url: https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base
  reference_code_urls:
    - https://github.com/huggingface/transformers/tree/main/src/transformers/models/deepseek_v4
    - https://github.com/NVIDIA/Megatron-LM/issues/4468
  large_artifact_policy: "Do not download checkpoint weights or other large artifacts; use metadata/source references only."
scope:
  phases_enabled: [0, 1, 2]
  phases_deferred:
    3: "Mac no GPU; loss-diff validation deferred"
    4: "Mac no GPU; runtime feature matrix validation deferred"
active_phase: 0
active_issue: null
active_pr: null
phase_iterations:
  "0": 0
  "1": 0
  "2": 0
limits:
  max_iterations_per_issue: 5
  max_iterations_per_phase: 10
merge_policy: auto_after_review_and_verification
```

Example `phase_goal_contract.yml`:

```yaml
phase0:
  version: 1
  goal: "Extract enough DS V4 facts for Phase 1 code generation."
  acceptance: []
  comparator_rules: []
phase1:
  version: 1
  goal: "Generate baseline-aligned framework-native DS V4 code."
  acceptance: []
  comparator_rules: []
phase2:
  version: 1
  goal: "Generate baseline-aligned DS V4 conversion rules."
  acceptance: []
  comparator_rules: []
```

Report artifacts must be written to disk so GitHub issues can reference stable evidence:

```text
.loongforge/issue-loop/issue_specs/phase0-<dedup>.yml
.loongforge/issue-loop/comparator_reports/phase0-iter3.yml
.loongforge/issue-loop/verification_reports/issue-17-pr-22.yml
```

## 7. IssueSpec and GitHub Issue Policy

Problems become structured `IssueSpec` records before they reach GitHub.

Minimal `IssueSpec` fields:

```yaml
dedup_key: phase0:model_spec_missing_dsv4_mtp:phase1_contract_blocked
phase: 0
title: "[Phase 0][DS V4] model_spec misses MTP fields required by Phase 1"
kind: bug|gap|regression|contract-missing|verification-failure|goal-contract-gap
severity: blocker|high|medium|low
goal_blocked: "Phase 1 cannot choose DS V4 native strategy without MTP metadata."
observed: "phase1 reports fallback_phase=0 because model_spec lacks ..."
expected: "Phase 0 output should include ..."
reproduction:
  commands:
    - "loongforge-adapt --resume <run_dir> --from-phase 0"
    - "loongforge-phase-gate --run-dir <run_dir> --phase 0"
  artifacts:
    - "<run_dir>/phases/phase0/model_spec.yaml"
    - "<run_dir>/phases/phase1_output.yml"
acceptance:
  - "model_spec contains DS V4 MTP topology and config fields"
  - "phase0_output.yml passes loongforge-phase-gate"
  - "Phase 1 no longer falls back to Phase 0 for this issue"
labels:
  - loongforge-adapt
  - phase-0
  - ds-v4
  - agent-fixable
```

Dedup policy:

```text
same dedup_key + open issue exists
  -> update/comment on existing issue with new evidence

same dedup_key + closed issue exists but failure reproduces again
  -> reopen issue or create linked regression issue

no matching issue
  -> create new GitHub Issue
```

GitHub issue template:

```markdown
## Phase
Phase 0

## Goal blocked
...

## Observed failure
...

## Expected behavior
...

## Evidence
- command:
- artifacts:
- logs:
- validator/comparator result:

## Acceptance checklist
- [ ] ...
- [ ] ...

## Dedup key
`phase0:model_spec_missing_dsv4_mtp:phase1_contract_blocked`

## Agent instructions
Repair agent must reproduce or prove the issue before modifying code.
```

## 8. Repair, PR, Review, and Verification Loop

### 8.1 Repair Agent

The repair agent executes one issue at a time:

```text
1. Read GitHub issue.
2. Create local branch: agent/issue-<id>-<short-slug>.
3. Read issue evidence and acceptance checklist.
4. Reproduce the failure or create artifact-level proof.
5. Modify plugin code, tests, docs, phase manuals, comparator rules, or goal contracts as needed.
6. Run issue-specific checks, plugin tests, and relevant static gates.
7. Commit and push the branch.
8. Create or update a PR.
```

Repair agent rules:

- Do not repair unrelated findings in the same branch.
- If a new problem is found, create/update another issue.
- If the issue cannot be reproduced or proven, label/comment `needs-repro` and pause that issue.

### 8.2 PR Requirements

PR body must include:

```markdown
Closes #<issue-id>

## Problem
...

## Fix
...

## Verification
- [ ] issue acceptance checklist passed
- [ ] plugin tests passed
- [ ] phase artifact gate passed
- [ ] DS V4 static baseline comparator passed

## Risk
...
```

### 8.3 Review Agent

The review agent independently checks:

1. PR scope matches the linked issue.
2. Diff follows plugin architecture and surrounding style.
3. Tests or comparator rules cover the fix.
4. Issue acceptance checklist is satisfied.
5. Phase output schema and step gate are not broken.
6. Docs and knowledge base are updated when behavior or contracts change.
7. Local no-GPU verification actually passes.

### 8.4 Verification Gate

A PR may auto-merge only when all hard gates pass:

```text
- Issue acceptance checklist passes.
- Review agent verdict is approved.
- Plugin local tests pass.
- Relevant phase artifact gate passes.
- DS V4 static baseline comparator passes.
- Current phase downstream readiness passes.
- Working tree is clean.
- PR branch is up to date and mergeable.
- No GPU-only gate is incorrectly configured as blocking.
```

If review or verification fails:

```text
comment on PR and issue with failing command, report path, and unmet checklist item
repair_iteration += 1
repair agent continues on same PR
```

If issue iteration limit is reached:

```text
label issue needs-human
mark PR draft or close it with explanation
pause the loop and write state.yml
```

### 8.5 Auto Merge

When all gates pass:

```bash
gh pr merge <pr> --squash --delete-branch
gh issue close <issue> --comment "Resolved by PR #<pr>."
```

After merge:

1. Checkout main.
2. Pull latest main.
3. Clean local branch state.
4. Rerun the current phase.
5. Recheck phase goal before advancing.

## 9. Phase 0-2 MVP Goals

### 9.1 Phase 0 Goal

Phase 0 must extract enough DS V4 facts for Phase 1 to generate code without guessing.

Initial checklist:

```markdown
- [ ] Resolve HF source/config/modeling paths.
- [ ] Record baseline repositories and commits.
- [ ] Identify DS V4 architecture family/category.
- [ ] Extract DS V4 component graph needed by Phase 1.
- [ ] Extract MLA-related config fields and structural facts.
- [ ] Extract MoE router/expert/shared-expert facts.
- [ ] Extract MTP, or explicitly prove it is absent.
- [ ] Extract checkpoint tensor naming patterns needed by Phase 2.
- [ ] Write reference_contract.yml linking baseline files/symbols to required components.
- [ ] Phase 1 strategy preflight can consume Phase 0 output without fallback_phase=0 for missing analysis.
```

Phase 0 comparator:

```text
phase0 model_spec/reference_contract
  <-> DS V4 facts from AIAK-Megatron and AIAK-Training-Omni baseline commits
```

### 9.2 Phase 1 Goal

Phase 1 must generate or modify framework-native DS V4 code that aligns structurally and semantically with baseline implementation patterns.

Initial checklist:

```markdown
- [ ] Generated code uses framework-native integration, not standalone fallback.
- [ ] DS V4 config fields cover baseline-required fields.
- [ ] MLA component structure matches baseline-required classes/functions/interfaces.
- [ ] MoE component structure matches baseline-required classes/functions/interfaces.
- [ ] MTP component structure matches baseline-required classes/functions/interfaces, or absence is justified.
- [ ] Layer spec / module spec integration follows baseline native pattern.
- [ ] Lint/import/static checks pass where available on Mac.
- [ ] Phase 2 can consume generated code and config without missing structural information.
```

Phase 1 comparator:

```text
generated Omni/Megatron code
  <-> AIAK-Megatron + AIAK-Training-Omni baseline implementation
```

Comparator dimensions:

- Symbols.
- Classes.
- Function signatures.
- Config fields.
- Module/layer spec wiring.
- Critical branch logic.
- Protected-file policy.

### 9.3 Phase 2 Goal

Phase 2 must generate baseline-aligned DS V4 conversion rules and tensor mapping coverage.

Initial checklist:

```markdown
- [ ] Conversion config/rules cover baseline DS V4 tensor names.
- [ ] MLA tensor mappings are present.
- [ ] MoE router/expert/shared expert tensor mappings are present.
- [ ] MTP tensor mappings are present or absence is justified.
- [ ] Split/merge/transpose rules match baseline intent.
- [ ] Converter entrypoints/scripts are generated.
- [ ] No runtime GPU gate is required for MVP pass.
```

Phase 2 comparator:

```text
generated convert yaml/scripts/converter
  <-> baseline conversion logic or tensor naming patterns
```

## 10. Deferred Phase Handling

Phase 3 and Phase 4 are not passed in the MVP. They are explicitly deferred:

```yaml
phase3:
  status: deferred
  reason: "Local Mac has no GPU; runtime loss-diff validation is out of MVP scope."
phase4:
  status: deferred
  reason: "Local Mac has no GPU; runtime feature matrix validation is out of MVP scope."
```

If future remote GPU validation is added, it should become a separate optional gate or later milestone, not hidden inside this local MVP.

## 11. Mutable Goal Contract

Phase goals can be wrong or incomplete. They must therefore be versioned and repairable.

Example:

```text
Phase 1 repeatedly generates poor DS V4 code.
Root cause: Phase 0 output does not require baseline MLA submodule facts.
Action: create issue kind=goal-contract-gap for Phase 0.
Repair: update phase_goal_contract.yml, Phase 0 manual/schema/comparator, and analyzer tests.
Then rerun Phase 0 and Phase 1 readiness.
```

Goal contract repair follows the same issue/PR/review/merge loop as code repair.

Review requirements for goal contract changes:

- The new goal is evidence-based.
- It helps downstream phase readiness.
- It is not overfit to one line of DS V4 code when a general rule is possible.
- Comparator/tests prove the new requirement is enforceable.

## 12. Error Handling

Recommended categories:

```yaml
unreproducible:
  action: comment issue + label needs-repro
  loop: pause issue

baseline_unavailable:
  action: label needs-baseline
  loop: pause phase

goal_contract_gap:
  action: create/update issue kind=goal-contract-gap
  loop: repair goal contract, then rerun upstream phase

repair_failed:
  action: comment failure evidence
  loop: retry until max_iterations_per_issue

review_failed:
  action: comment PR findings
  loop: repair same PR

verification_failed:
  action: attach report to issue/PR
  loop: repair same issue

max_phase_iterations_exceeded:
  action: label needs-human
  loop: pause target case
```

Auto-merge protection rules:

- If PR changes exceed issue scope, block merge.
- If comparator fails, block merge.
- If reviewer verdict is not approved, block merge.
- If phase goal contract changes, rerun related upstream/downstream checks before merge.

## 13. Testing Strategy

### 13.1 Unit Tests

Cover pure logic:

- `IssueSpec` generation.
- Dedup key calculation.
- GitHub issue lookup/update/create in dry-run mode.
- `state.yml` read/write/resume.
- Phase goal contract validation.
- Comparator report parsing.

### 13.2 Fixture Tests

Use small DS V4-like fixtures or snapshots:

- Baseline symbol extraction.
- Missing Phase 0 model_spec field creates a Phase 0 issue.
- Missing generated code symbol creates a Phase 1 issue.
- Missing conversion tensor map creates a Phase 2 issue.

### 13.3 Integration Dry Run

Run without touching GitHub:

```text
Phase checker -> IssueSpec -> dry-run GitHub payload -> simulated repair report -> simulated review pass/fail -> state transition
```

CLI shape:

```bash
loongforge-issue-loop run --target ds-v4 --dry-run
loongforge-issue-loop run --target ds-v4 --apply
```

`--dry-run` prints planned GitHub/branch/PR actions. `--apply` performs real GitHub issue/PR actions through `gh`.

## 14. Open Decisions for Implementation Planning

These can be finalized during implementation planning:

1. Exact CLI placement: new `bin/loongforge-issue-loop` wrapper or subcommand under existing adapt scripts.
2. Exact comparator implementation split: Python deterministic extraction first, LLM semantic review second, or both from the start.
3. Whether first PRs should auto-merge immediately or run in `--dry-run` / `--no-merge` mode until confidence is established.
4. Whether GitHub labels should be auto-created by the tool.

The design assumes the default desired end state is real GitHub issue creation and auto-merge after review and verification, with dry-run available for safe testing.
