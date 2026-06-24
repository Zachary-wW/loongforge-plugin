# Adapt Skill 重构 — Loop Engineering 化

## What This Is

把 `loongforge-plugin/skills/adapt`（当前的 6 阶段 HF→LoongForge 适配 skill）重构为一个显式 loop-engineering 工作流：用户在启动适配时给出 HF 模型实现 + ckpt + LoongForge 仓库 + Loong-Megatron 仓库四份输入，skill 在两个外部 GitHub 仓库（`Zachary-wW/LoongForge`、`Zachary-wW/Loong-Megatron`）上以 PR / issue / merge / rerun 闭环驱动适配，直到验证器全部通过。

服务对象：把新模型适配到 LoongForge 的算法/工程同学。运行环境：Claude Code 命令行 + GitHub（`gh` CLI）+ 现有 phase validator。

## Core Value

**适配过程必须是闭环的**：每一次代码改动都走「PR → review → merge → 验证 → 失败建 issue → 修复 PR」循环，验证器是循环的真相源；除非所有 phase validator 全部 pass，循环不结束。一切为这个闭环服务。

## Requirements

### Validated

- ✓ 现有 6 阶段（Phase 0 HF 解析 / Phase 1 组网 / Phase 2 权重转换 / Phase 3 loss-diff / Phase 4 feature-compat / Phase 5 KB）— 既存能力，保留作为 loop 内部步骤
- ✓ `loongforge-phase-gate` 作为 phase 出口确定性闸门 — 既存
- ✓ `phases/phaseN_output.yml` + `phases/phaseN/attempts.jsonl` 作为状态真相源 — 既存
- ✓ PR-01 (create_branch 拒绝 default branch)、PR-02 (squash merge + delete-branch)、PR-03 (PR 标题含 run_id/phase/attempt/validator)、PR-04 (branch 名正则 adapt/…/phaseN/attemptK)、PR-05 (human commit 检测 + /agent-resume)、PR-06 (protected path 拒绝) — Validated in Phase 2: gh_client.py
- ✓ ISSUE-01 (structured failure_signature + log excerpt + attempts.jsonl + reproduction)、ISSUE-02 (Fixes #N linkage)、ISSUE-03 (dedup key 跨 attempt 去重)、ISSUE-04 (label bootstrapping) — Validated in Phase 2: gh_client.py + templates.py
- ✓ RESUME-03 (idempotency key SHA256 + footer + find_by_idempotency_key) — Validated in Phase 2: idempotency.py + gh_client.py

### Active

- [ ] **REQ-INPUT-01**：在 skill 启动时收集四类输入：HF 实现代码 URL、ckpt+tokenizer URL、LoongForge 仓库 URL、Loong-Megatron 仓库 URL（含分支/路径），并校验
- [ ] **REQ-INPUT-02**：把这四个 URL 落到 `run_inputs.yml` 新增字段，下游 phase 都从这里读
- ✓ LOOP-01 (12-state FSM Probe→Edit→PR→Merge(base)→Validate→Diagnose→Issue→Fix-PR→Review→Merge→Rerun→Exit), LOOP-02 (validator_passed/validator_passed_after_fix only positive exits), LOOP-03 (3-axis budget: per-phase 5 / per-run 25 / wallclock 240 min), LOOP-04 (Diagnose read-only classifier distinct from Edit), LOOP-05 (wrong-direction → human_needed + escalation.md) — Validated in Phase 3: loop_controller.py + diagnose_classifier.py
- ✓ VAL-01 (validator wrapper calls loongforge-phase-gate subprocess, never rewrites), VAL-02 (structured FailureSignature; free-text-only → failure_signature=None → NEEDS_HUMAN), VAL-03 (Phase 3/4 flake-rerun with DEFAULT_FLAKE_RERUN_COUNT=3), VAL-04 (3-part integrity check: binary hash + log mtime + log presence; _validate_loop_evidence rejects passed when integrity_ok=False), VAL-05 (get_megatron_head_sha via gh api; loong_megatron_sha stored in LoopState) — Validated in Phase 3: validator_wrapper.py + validate_phase_completion.py + loop_controller.py
- ✓ LOG-01 (every FSM transition appends one row to attempts.jsonl with ts/attempt/kind/pr_url/issue_url/validator/verdict/exit_reason/event_id) — Validated in Phase 3: loop_controller.py + validator_wrapper.py

### Active

- ✓ RESUME-01 (--resume reconstructs FSM state from last attempts.jsonl row + loop_state.yml via LoopState.from_disk) — Validated in Phase 4: resume.py
- ✓ RESUME-02 (reconcile_remote_state detects PR 404, closed-without-merge, SHA drift, force-push, issue 404, closed-unexpectedly; mismatches force SystemExit(3)) — Validated in Phase 4: resume.py + run.py
- ✓ DOC-03 (all 6 agent.md carry conditional Loop Engineering Hooks with Pre-Edit branch creation + Post-Edit PR submission, gated on repos: presence) — Validated in Phase 4: references/phases/phaseN/agent.md
- ✓ TEST-01 (E2E fail→diagnose→issue→fix-PR→review→merge→pass cycle on Phase 1 against FakeGhClient) — Validated in Phase 4: test_loop_e2e.py
- ✓ TEST-04 (kill mid-DIAGNOSE/mid-ISSUE, resume produces zero duplicate issues/PRs) — Validated in Phase 4: test_resume.py
- ✓ COMPAT-01 (legacy invocation without repos: produces no pr/issues/loop blocks, passes validate_phase_output) — Validated in Phase 4: test_compat.py

- ✓ DOC-01 (SKILL.md rewritten with loop-first architecture: 12-state FSM, three-layer framing, maker-checker split, three-axis budget, When NOT to Use, Loop Invocation, End-of-Run Housekeeping wiring) — Validated in Phase 5: skills/adapt/SKILL.md
- ✓ DOC-02 (loop_engineering/README.md maps P1-P21 to concrete implementation files/functions, cites se.rpcx.io/04/08/12) — Validated in Phase 5: skills/adapt/references/loop_engineering/README.md
- ✓ DOC-04 (summary_generator.py produces comprehension_summary.md + phaseN_summary.md with merge_commit_sha column; CLI entry point) — Validated in Phase 5: skills/adapt/lib/summary_generator.py
- ✓ ACC-01 (386 pytest tests green, test_loop_e2e.py proves full FSM cycle against FakeGhClient) — Validated in Phase 5
- ✓ ACC-02 (ds_v4_runbook.md with DS V4 invocation, pass criteria, community diff placeholder) — Validated in Phase 5: skills/adapt/references/acceptance/ds_v4_runbook.md
- ✓ ACC-03 (HANDOFF.md with copy list, env setup, resume instructions, ckpt expectations) — Validated in Phase 5: .planning/HANDOFF.md

- ✓ P1R-01 (bridge_mapping_path as primary input for Phase 1, model_spec_path legacy fallback) — Validated in Phase 7: agent.md
- ✓ P1R-02 (dual-repo code generation: LoongForge + Megatron, Step 2d gap module design) — Validated in Phase 7: agent.md + strategy_rules.yaml
- ✓ P1R-03 (P1-P8 static perf guard rails with blocking severity) — Validated in Phase 7: perf_rules.yaml
- ✓ P1R-04 (verification rigor: shared-seed init 1e-3, HF sanity run, example script dry run, full tensor fixation) — Validated in Phase 7: verify.md
- ✓ P1R-05 (confidence-driven 3-level validation: high/medium/low/gap) — Validated in Phase 7: agent.md + strategy_rules.yaml + megatron_preread_checklist.yaml
- ✓ P1R-06 (explicit Loop FSM exit path: repos:present → commit/validate/loop; repos:absent → local repair) — Validated in Phase 7: agent.md
- ✓ P1R-07 (validate_phase_completion.py Phase 1 checks for bridge_mapping_consumed, generated_megatron_files, perf_lint_executed, hf_sanity_run_passed, example_script_dry_run_passed, strategy_overrides) — Validated in Phase 7: validate_phase_completion.py

### Out of Scope

- 修改 LoongForge / Loong-Megatron 业务代码本身 — 这次只重构 plugin 侧的 adapt skill，外部仓库的 PR 由 skill 运行时产生
- 替换 `loongforge-phase-gate` / phase validator 内部逻辑 — 只调用，不改判定标准
- 引入新的验证维度（perf、可解释性等）— 现有 validator 集合就够
- 多模型并行 / 多 run 调度 — 单次 skill 调用单个 run
- 自建 GitHub App / webhook — 全程通过 `gh` CLI 同步驱动

## Context

- **现状**：`skills/adapt/SKILL.md` 已经是一份 160 行的 6 阶段编排手册，强调 phase agent 内部 loop（`attempts.jsonl`），但**没有把"通过 GitHub PR/issue 与外部仓库交互"作为一等公民**。当前的 retry 都是本地 phase-internal，外部协作面靠人工。
- **本次重构动因**：算法同学希望把适配过程从"本地脚本黑盒"变成"GitHub 上可追溯的协作闭环"——每次失败都有 issue 可指、每次修复都有 PR 可 review，最终 merge 后才允许下一轮 validate。
- **方法论锚点**：loop engineering（se.rpcx.io 第 4 / 8 / 12 篇）。把"循环 + 反馈"作为一等设计原则，而不是把适配当成线性流水线。
- **外部依赖**：GitHub 仓库 `Zachary-wW/LoongForge`（主干 main）+ `Zachary-wW/Loong-Megatron`（分支 `loong-main/core_v0.15.0`）。运行时通过 `gh` CLI 操作 PR / issue。
- **样板模型**：DeepSeek-V4-Flash（HF 路径 `transformers/models/deepseek_v4` + ckpt `deepseek-ai/DeepSeek-V4-Flash-Base`），用作 e2e 验证案例。
- **验收分两层（重要）**：
  - **本地验收**（开发机/笔记本，无 GPU）：plugin 整理到"可运行"状态 —— Pydantic 模型 round-trip、redactor snapshot、`FakeGhClient` mock 的 PR/issue/merge 全链路、`--resume` 幂等、所有 pytest 绿。**不跑真 GPU validator，不发真 PR**。
  - **GPU 机器验收**（开发机 GPU 节点）：用户把当前 session + plugin 代码拷贝过去，用重构后的 skill 完整跑一次 DS V4 适配，然后把结果与一份**社区版本**的同模型适配做 diff，看缺什么、差什么。这是最终验收，**不在本会话内执行**。

## Constraints

- **Tech stack**：Claude Code skill (Markdown + Python helpers) + Bash + `gh` CLI；不引入新语言/服务
- **External access**：必须有对 LoongForge / Loong-Megatron 仓库的写权限（PR + issue + merge）；权限缺失要 fail-fast 且报错明确
- **Compatibility**：保留 `--resume` 与现有 `phases/phaseN_output.yml` 契约
- **Determinism**：loop 必须有显式上界（最大 attempts、最大总耗时），避免 token / GitHub API 失控
- **Security**：PR/issue 正文不得包含 ckpt 路径以外的敏感信息（无 token、无内部域名）
- **Plugin layout**：所有改动收敛在 `skills/adapt/`；`skills/adapt_eval` 不动
- **Branch**：当前工作分支 `refactor/adapt-loop-engineering`（基于 main）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 保留 Phase 0–5 作为 loop 内部步骤，不重新拆 phase | 减小重构面，复用既有 validator | — Pending |
| PR/issue 仅作用于 LoongForge / Loong-Megatron 两个外部仓库；plugin 自身不走该 loop | 用户明确选择 | — Pending |
| 验证器 = 现有 phase validators 的并集（phase1-verify / phase2-conversion / loss-diff / feature-compat / kb-consistency） | 用户明确选择，不新设统一验证器 | — Pending |
| 跳过 `/gsd:map-codebase`，researcher 针对性读 `skills/adapt/` + se.rpcx.io 三篇 | 改动边界已经清晰 | — Pending |
| 工作模式：YOLO + Coarse（4–5 phase）+ Inherit 模型 + Researcher/Plan-Checker/Verifier 全开 | 用户选择 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-24 after Phase 10 completion — 7-phase structure with Performance Tuning as Phase 4*
