# Phase 7: Phase 1 Redesign — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 07-phase1-redesign
**Areas discussed:** Dual-repo generation, Perf check depth, Verification rigor, Bridge consumption + FSM

---

## Dual-Repo Generation

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 1 双仓库生成 | Step 2d 增加 Megatron gap module 设计，Step 3 区分 generated_loongforge_files 和 generated_megatron_files | ✓ |
| 拆出 Megatron Edit 步骤 | Phase 1 只生成 LoongForge 代码 + megatron_patch_plan.md，新增 Phase 1.5 处理 Megatron | |
| 指令式 Megatron 修改 | Phase 1 只生成 LoongForge 代码，Megatron 修改写在 gaps[].phase1_guidance 由 loop controller 执行 | |

**User's choice:** Phase 1 双仓库生成
**Notes:** User confirmed Phase 1 should generate code for both repositories. GT demonstrates this is necessary — DS V4 requires ~4 Megatron modifications.

### Megatron modification rules

| Option | Description | Selected |
|--------|-------------|----------|
| 同规则同流程 | PROTECTED_FILES.md applies equally to LoongForge and Megatron | ✓ |
| 更严的框架扩展流程 | Stricter "framework extension" process with blast radius analysis | |
| 只新增不修改 | Only create new Megatron files, never modify existing ones | |

**User's choice:** 同规则同流程
**Notes:** No stricter process needed — PROTECTED_FILES.md already enforces append-only, no behavior change for other models.

---

## Perf Check Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Static perf lint in Step 3 | ~8 perf guard rails (P1-P8) as mandatory Step 3 checks | ✓ |
| Runtime perf test in Step 7 | Measure peak memory and execution time during trim config | |
| Both static + runtime | Step 3 static lint + Step 7 runtime smoke test | |

**User's choice:** Static perf lint in Step 3
**Notes:** User chose static perf lint over runtime. Runtime perf testing deferred to Phase 3 or separate task.

### Perf rules location

| Option | Description | Selected |
|--------|-------------|----------|
| strategy_rules.yaml 同文件 | Add P1-P8 to existing structural_rules section | |
| 独立 perf_rules.yaml | Separate file to keep strategy_rules.yaml manageable | ✓ |

**User's choice:** 独立 perf_rules.yaml
**Notes:** Separate file avoids bloating strategy_rules.yaml.

---

## Verification Rigor

### Initialization strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Sliced checkpoint 真实权重 | Use real weights from sliced checkpoint for forward comparison | |
| 共享 seed 初始化 | Initialize HF model with fixed seed, dump params, set into LoongForge model | ✓ |
| 放宽阈值 + 行为级验证 | Keep random init but relax threshold + add behavioral checks | |

**User's choice:** 共享 seed 初始化
**Notes:** Shared-seed initialization eliminates random noise, making loss comparison reflect only architecture differences.

### Additional verification steps

| Option | Description | Selected |
|--------|-------------|----------|
| 增加 HF Sanity Run 步骤 | Run HF transformers forward before Step 7 to confirm HF side works | ✓ |
| 增加 Example Script Dry Run | Run original example script with --train-iters 0 after Step 7 | ✓ |
| 全面固定输入张量 | Fix all input tensors (attention_mask, position_ids, labels) not just input_ids | ✓ |

**User's choice:** All three selected (multiSelect)
**Notes:** User wants all three improvements. HF sanity run before Step 7, example script dry run after Step 7, full tensor fixation across both sides.

---

## Bridge Consumption + FSM

### Confidence-driven validation

| Option | Description | Selected |
|--------|-------------|----------|
| Confidence 驱动 3 级验证 | high=adopt+skip 2c, medium=simplified 2c, low=full 2c, gap=2d | ✓ |
| 全部完整验证 | All components do full Step 2c regardless of confidence | |
| 轻量模式 | Only verify reference_impl_analysis exists, skip 2c for all | |

**User's choice:** Confidence 驱动 3 级验证
**Notes:** Three-tier validation based on Phase 0 confidence level. High confidence components skip expensive Megatron reading.

### Loop FSM exit path

| Option | Description | Selected |
|--------|-------------|----------|
| 明确 FSM exit path | Agent.md describes commit → validate → loop flow | ✓ |
| 保留本地修复 + FSM 外层 | Phase 1 always does local repair, FSM is outer wrapper | |

**User's choice:** 明确 FSM exit path (user specified: "验证前在特定分支提交代码，然后进入验证，如果验证失败则进入loop")

### FSM flow detail

| Option | Description | Selected |
|--------|-------------|----------|
| Commit → Validate → Loop | repos: present → commit to branch → validate → pass=PR+merge / fail=loop_controller | ✓ |
| Commit → Validate → PR (human merge) | Same but require human review before merge | |

**User's choice:** Commit → Validate → Loop

---

## Claude's Discretion

- Exact perf rule IDs and violation signals
- Step 2d output structure for Megatron gap module design
- HF Sanity Run step numbering
- Shared-seed initialization implementation details
- Whether reference_impl_analysis fully replaces or supplements megatron_preread_checklist

## Deferred Ideas

- Runtime perf smoke test (Step 7 peak memory + time measurement) — deferred to Phase 3 or separate task
- Automated Megatron regression testing — deferred to runtime acceptance
- Cross-model compatibility check — deferred to GPU machine acceptance
- Advanced Megatron source reading sub-agent — revisit if confidence-driven approach insufficient
