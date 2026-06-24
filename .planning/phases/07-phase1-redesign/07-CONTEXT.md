# Phase 7: Phase 1 Redesign — Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Redesign Phase 1 of the adapt skill to: (1) correctly consume Phase 0's three-document output as primary input, (2) support dual-repo code generation (LoongForge + Megatron), (3) add performance guard rails, (4) strengthen verification with HF sanity run and shared-seed initialization, and (5) explicitly integrate with the Loop FSM exit path.

Scope: Phase 1 agent.md rewrite, supporting schema/rule files (strategy_rules.yaml, perf_rules.yaml, verify.md, phase1_output_schema.yaml), and validate_phase_completion.py Phase 1 checks. Phase 2/3/4/5 agent changes are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Dual-Repo Generation
- **D-01:** Phase 1 generates code for **both** LoongForge and Megatron repositories. Step 2d (new) designs Megatron gap modules for gap components. Step 3 distinguishes `generated_loongforge_files` and `generated_megatron_files`. Loop Engineering Hooks create branches and PRs on both repos.
- **D-02:** Megatron existing-file modifications follow the **same** rules as LoongForge-side modifications: PROTECTED_FILES.md applies (append-only new branches at end of methods, no modification of existing branch logic, no behavior change for other models). No stricter framework-extension process needed beyond what PROTECTED_FILES already enforces.

### Performance Guard Rails
- **D-03:** Step 3 adds ~8 static perf guard rails (P1-P8) as mandatory checks, parallel to existing G1-G14. Each rule has: `when` condition, `violation_signal`, `rationale`. Known anti-patterns covered: IdentityOp in core_attention slot, custom nn.Module instead of flat Parameter + einsum, not reusing Megatron MoE infrastructure, missing activation checkpointing for large models, incorrect TP/EP communication patterns, unfused kernel when fused is available, missing inverse RoPE for MLA hybrid attention, missing activation offload context.
- **D-04:** Perf rules written in a **separate file** `references/phases/phase1/perf_rules.yaml` (not inside strategy_rules.yaml) to keep files manageable. Step 3 reads this file and enforces rules alongside G1-G14.

### Verification Rigor
- **D-05:** Step 7 forward comparison uses **shared-seed initialization** instead of independent random init: initialize HF model with fixed seed, dump all parameters, manually set those parameters into the LoongForge model. Differences then reflect only architecture discrepancies, not initialization noise.
- **D-06:** Phase 1 verification adds three improvements:
  1. **HF Sanity Run** (new step before Step 7): load model via `transformers` library, run forward with fixed input, confirm HF side produces finite loss and can actually execute.
  2. **Example Script Dry Run** (new step after Step 7): run original generated example script with `--train-iters 0 --no-load-optim`, verify shell is executable, parameters are valid, paths are correct, model can load.
  3. **Full input tensor fixation**: `input_ids`, `attention_mask`, `position_ids`, `labels` all fixed and identical on both sides. Current design only fixes `input_ids`.

### Bridge Mapping Consumption + Confidence-Driven Validation
- **D-07:** Phase 1 Step 2 uses **confidence-driven 3-level validation depth**:
  - `confidence=high`: Adopt Phase 0 strategy directly, verify reference_impl_analysis.yaml entry exists and is complete, skip Step 2c Megatron reading.
  - `confidence=medium`: Simplified Step 2c — only read Megatron source sections related to behavioral_diff topics. May override strategy with evidence.
  - `confidence=low`: Full Step 2c reading. May override strategy. Must record override reason in strategy_plan.
  - `gap` (megatron=null): No Step 2c (no Megatron module to read). Read bridge_mapping.gaps[].phase1_guidance. Design new module in new Step 2d.
- **D-08:** Loop FSM exit path explicitly described in Phase 1 agent.md:
  - When `repos:` present: Step 3 generates code and commits to branch → Step 4-6 lint/review/smoke → Step 7 validate → **pass** → create PR + merge → done; **fail** → exit to loop_controller, which drives diagnose → issue → fix-PR → review → merge → rerun.
  - When `repos:` absent: existing local repair loop (<=30 rounds). validator fail → human_needed.

### Bridge Mapping as Primary Input
- **D-09:** `bridge_mapping_path` is the **primary input** for Phase 1. `model_spec_path` is legacy fallback only (used when bridge_mapping_path is absent). Step 1 extracts component_bridge, gaps, validator_requirements, implementation_contract, conversion_requirements from bridge_mapping.yaml. Step 1 extracts components, structural_tags, traps, weight_structure from hf_analysis.yaml. Step 1.5 loads reference_impl_analysis.yaml as Megatron architecture context (replacing raw Megatron source file reading for confidence=high/medium components).
- **D-10:** Step 1.5 Megatron Architecture Pre-read is **restructured**: confidence=high/medium components load their Megatron context from reference_impl_analysis.yaml (already analyzed by Phase 0). Only confidence=low components and gap components require direct Megatron source file reading (Step 2c/2d). megatron_preread_checklist.yaml still required for understanding the assembly flow, but component-specific reading is delegated to confidence levels.

### Output Schema Updates
- **D-11:** `phase1_output_schema.yaml` updated to include: `bridge_mapping_consumed: true`, `generated_megatron_files` list, `strategy_overrides` recording Phase 0 strategy → Phase 1 final strategy with override reason, `hf_sanity_run_passed: true`, `example_script_dry_run_passed: true`.

### Claude's Discretion
- Exact perf rule IDs (P1-P8) and their violation signals
- How Step 2d (Megatron gap module design) structures its output for Step 3 consumption
- Whether HF Sanity Run is a separate step (Step 6.5) or integrated into Step 7
- Exact shared-seed initialization implementation (dump format, parameter name mapping)
- Whether reference_impl_analysis.yaml fully replaces megatron_preread_checklist.yaml or supplements it

### Folded Todos
None.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 0 v2 output (consumed by Phase 1)
- `skills/adapt/knowledge_base/schema/bridge_mapping_schema.yaml` — Bridge mapping YAML schema (component_bridge + gaps + validator_requirements)
- `skills/adapt/knowledge_base/schema/hf_analysis_schema.yaml` — HF analysis YAML schema (supersedes model_spec)
- `skills/adapt/knowledge_base/schema/reference_impl_analysis_schema.yaml` — Megatron-side analysis schema
- `skills/adapt/knowledge_base/examples/bridge_mapping_llm.yaml` — DS V4 bridge_mapping example (9 component_bridge + 3 gaps)

### Current Phase 1 implementation (to be rewritten)
- `skills/adapt/references/phases/phase1/agent.md` — Current Phase 1 agent manual (611 lines, 7+1 steps)
- `skills/adapt/references/phases/phase1/verify.md` — Current Phase 1 verification skill
- `skills/adapt/references/phases/phase1/strategy_rules.yaml` — Current strategy decision rules + structural_rules (G1-G14)
- `skills/adapt/references/phases/phase1/megatron_preread_checklist.yaml` — Current Megatron pre-read checklist
- `skills/adapt/references/phases/phase1/phase1_output_schema.yaml` — Current output schema
- `skills/adapt/knowledge_base/recipes/forward_debug.md` — Forward debug manual (PHASE1_VERIFY hook)

### Supporting reference files
- `skills/adapt/knowledge_base/schema/MEGATRON_COMPONENT_MAP.md` — Megatron architecture & component reference
- `skills/adapt/knowledge_base/schema/PROTECTED_FILES.md` — File protection rules (R021)
- `skills/adapt/knowledge_base/schema/FILE_STRUCTURE.md` — File layout and generation order
- `skills/adapt/knowledge_base/linter_rules/RULES.md` — R001-R020 linter rules
- `skills/adapt/knowledge_base/failure_patterns/phase1/*.md` — Known Phase 1 failure patterns
- `skills/adapt/references/tools/code-review/SKILL.md` — Code review skill
- `skills/adapt/references/tools/linter-check/SKILL.md` — Linter check skill

### Ground truth reference (DS V4 adaptation)
- `/Users/weizhihao/workspace/tmp_repo/0623/ground_truth/baidu/hac-aiacc/AIAK-Megatron/` — GT: Megatron-side implementation (hyper_connection.py, dsa.py, router.py, transformer_config.py changes)
- `/Users/weizhihao/workspace/tmp_repo/0623/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/` — GT: LoongForge-side implementation (7 core files in deepseek_v4/)
- `/Users/weizhihao/workspace/tmp_repo/0623/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml` — GT: weight name mapping (100+ entries)

### Architecture references
- `skills/adapt/references/loop_engineering/README.md` — P1-P21 principles mapping
- `skills/adapt/lib/loop_controller.py` — Loop FSM implementation (12-state controller)
- `skills/adapt/lib/schema.py` — Pydantic v2 models (BridgeMapping, ComponentBridge, GapEntry, etc.)
- `.planning/PROJECT.md` — Core value, constraints, key decisions
- `.planning/phases/06-phase0-redesign/06-CONTEXT.md` — Phase 6 decisions (D-01 through D-19)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `strategy_rules.yaml` structural_rules section: G1-G14 already define violation_signal and rationale format — P1-P8 perf rules follow same pattern
- `verify.md` Step 0-6 structure: existing verification flow is well-structured, needs insertion of HF sanity run and example script dry run
- `phase1_output_schema.yaml`: already has `strategy.overrides` and `contract_preflight` sections — extend with `bridge_mapping_consumed`, `generated_megatron_files`, new check fields
- `loop_controller.py`: FSM already supports both repos (loongforge + megatron) for PR/issue creation — Phase 1 just needs to generate code for both repos
- `gh_client.py` + `FakeGhClient`: already supports `create_branch` / `open_pr` on either repo — no new infrastructure needed
- `reference_impl_analysis.yaml`: Phase 0 already produces Megatron module analysis with class signatures, init members, forward flow, config fields, weight params — Phase 1 can consume this directly instead of re-reading source

### Established Patterns
- Guard rails (G1-G14) in strategy_rules.yaml: `when` condition + `violation_signal` + `rationale` + `applies_to_gaps` — same format for perf rules
- Confidence-driven flow: bridge_mapping already has `confidence: high/medium/low` field — natural selector for validation depth
- Dual-repo PR flow: Loop Engineering Hooks already reference `repos.loongforge` and `repos.megatron` — just need Phase 1 to generate files for both
- Phase 0 quality inner loop (D-15): Phase 1's confidence-driven validation follows similar "skip what's already confirmed" philosophy

### Integration Points
- Step 1 → Step 1.5 → Step 2 chain: must be restructured to load bridge_mapping as primary input
- Step 2 → Step 2d: new step for Megatron gap module design, feeds into Step 3
- Step 3: generation flow must branch into LoongForge files and Megatron files
- Step 7 verify.md: must add HF sanity run, shared-seed init, full tensor fixation, example script dry run
- Loop controller: Phase 1 agent.md must explicitly describe the "commit → validate → loop" exit path
- validate_phase_completion.py: add Phase 1 checks for bridge_mapping_consumed, generated_megatron_files consistency, perf lint execution

</code_context>

<specifics>
## Specific Ideas

- "执行phase1的重构，我比较关心的是：（1）phase1现在是否能够将phase0的产出正确消费（2）phase1是否能够依据phase0的产出来生成类似gt这样的代码（3）phase1应该需要加入一些perf的check防止写出的代码性能低，显存多（4）phase1是否能够对Megatron理解深入，能够像gt代码那样修改Megatron（5）phase1的验证部分需要实际运行hf transformer的代码（构建脚本） & 生成的example脚本，同时固定所有的输入，（6）phase1是否有生成的代码有问题提交issue & pr & rerun这种逻辑" — user's 6-point concern list
- GT demonstrates that Phase 1 must generate code for TWO repositories: 7 LoongForge files + ~4 Megatron modifications (hyper_connection.py new, dsa.py new, transformer_config.py modify, router.py modify)
- "当用户给出repo时，我希望的是验证前在特定分支提交代码，然后进入验证，如果验证失败则进入loop" — user's exact description of the FSM exit flow
- Shared-seed initialization: initialize HF model with fixed seed → dump parameters → manually set into LoongForge model. This ensures loss comparison reflects only architecture differences.
- Perf anti-patterns observed in agent-generated code: IdentityOp in core_attention slot, custom nn.Module instead of flat Parameter, not reusing Megatron MoE infrastructure, missing activation checkpointing

</specifics>

<deferred>
## Deferred Ideas

- **Runtime perf smoke test in Step 7**: Measuring peak memory and execution time during trim config forward+backward. Deferred to Phase 3 or a separate task — static perf lint (D-03) is sufficient for Phase 1 scope.
- **Automated Megatron regression testing**: When modifying transformer_config.py or router.py, automatically verify other models still work. This is a Phase 3/4 concern (real-weight verification across models).
- **Cross-model compatibility check**: Verify that Megatron modifications don't break existing models (e.g., DeepSeek V3, Qwen). Deferred to runtime acceptance testing on GPU machine.
- **Advanced Megatron source reading agent**: A separate sub-agent dedicated to deep Megatron code understanding. Current confidence-driven approach (D-07) may be sufficient; revisit if Phase 1 agent struggles with complex Megatron modifications.

</deferred>

---

*Phase: 07-phase1-redesign*
*Context gathered: 2026-06-24*
