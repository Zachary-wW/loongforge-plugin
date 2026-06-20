# LoongForge Knowledge Base Index

> Update Rule: Update this file immediately after every page addition/deletion.

## Agent Maintenance Procedures

### When Adapting a New Model (ingest)
1. Execute Phase 5 (`phase5_knowledge_update_agent.md`) to complete the knowledge base update automatically:
   - Create or update the corresponding `.yaml` in `sources/` (including `structural_tags`, `code_paths`, `omni_reference`, `traps` sections)
   - Append a new model entry in this file (Sources section)
   - Append an `adapt` type event in `LOG.md`
2. If encountering a hard-to-diagnose runtime failure, create a record file under `failure_patterns/phase<N>/`, named: `<short_description>_<YYYY-MM-DD>.md`

### When Answering Questions (query)
- If the answer involves adaptation traps, archive them into the `traps` section of the corresponding sources yaml

### Periodic Maintenance (lint)
- Run a lint check after every 5 adapt operations
- Lint check items: whether sources yaml `traps` cover known traps, whether `failure_patterns/` has content not yet summarized in sources traps
- After fixing, append a `lint` type event in LOG.md

---

## Schema (Rules and Processes)

- [FILE_STRUCTURE](schema/FILE_STRUCTURE.md) — Required file layout, generation order, `__init__.py` format, few-shot reference paths
- [HF_SCAN_RULES](schema/HF_SCAN_RULES.md) — Phase 0 Step 1: hf_path file classification rules
- [MEGATRON_COMPONENT_MAP](schema/MEGATRON_COMPONENT_MAP.md) — Phase 1 Step 2c: Component key to Megatron source file mapping
- [HF_OMNI_FIELD_MAP](schema/HF_OMNI_FIELD_MAP.md) — Phase 1 Step 3/3.5: HF config.json to Omni field mapping + YAML verification checklist
- [PROTECTED_FILES](schema/PROTECTED_FILES.md) — Common file protection list: prohibited from modification / append-only / Phase 2 modifiable files, preventing adaptation of one model from affecting others
- [model_spec structure specification](sources/source_digest_schema.md) — `model_spec.yaml` section structure, per-Phase read conventions, HF source code pointer usage

## Recipes (Implementation Details, Read On Demand)

- [modeling_source_resolution](recipes/modeling_source_resolution.md) — Phase 0 Step 1d: Situation A->B->C->D resolution order when modeling_*.py is missing
- [strategy_plan](recipes/strategy_plan.md) — Phase 1 Step 2: strategy_plan in-memory format + actual decision cases
- [vlm_task_encoder](recipes/vlm_task_encoder.md) — Phase 1 Step 3f (VLM): Task Encoder four-dimensional difference analysis + generation decisions
- [forward_debug](recipes/forward_debug.md) — Phase 1 Step 7: PHASE1_VERIFY hook + error classification + self-check checklist + tensor dump
- [convert_debug](recipes/convert_debug.md) — Phase 2 Step 5a/5b/5c: convert shell debugging, roundtrip diagnostics, name_map fixes

## Examples (Example Files, For Reference)

- [model_spec_llm](examples/model_spec_llm.yaml) — Complete model_spec.yaml LLM example (DeepSeek-V3)
- [model_spec_vlm](examples/model_spec_vlm.yaml) — Complete model_spec.yaml VLM example (Qwen2.5-VL)

---

## Sources (Model Structure + Adaptation Traps, Original Data Must Not Be Modified)

Each yaml contains: HF reference paths, Omni reference paths, `structural_tags` (structural features), `traps` (known adaptation traps).

### LLM
- [deepseek_v3](sources/llm/deepseek_v3.yaml) — MLA+MoE+MTP, sigmoid gate, e_score_correction_bias
- [qwen2](sources/llm/qwen2.yaml) — Dense GQA, no QK Norm
- [qwen3](sources/llm/qwen3.yaml) — Dense/MoE GQA, QK Norm
- [qwen3_5](sources/llm/qwen3_5.yaml) — Hybrid Linear+Transformer, partial RoPE
- [qwen3_next](sources/llm/qwen3_next.yaml) — Hybrid variant (GQA + Linear Attn + MoE + MTP)
- [mimo](sources/llm/mimo.yaml) — Dense + MTP, reversed _concat_embeddings order

### VLM
- [internvl](sources/vlm/internvl.yaml) — InternViT + InternLM backbone
- [qwen2_5_vl](sources/vlm/qwen2_5_vl.yaml) — Qwen2.5 + mRoPE, spatial_merge_size
- [qwen3_vl](sources/vlm/qwen3_vl.yaml) — Qwen3 + mRoPE, no windowed attention

---

## Wiki (Runtime Failure Records)

Each phase subdirectory contains failure patterns for that stage. Each phase agent reads all `.md` files in the corresponding directory **before execution** and memorizes **prevention** measures.

### phase0/
- [partial_rotary_factor_missed](failure_patterns/phase0/partial_rotary_factor_missed.md) — config.json did not extract partial_rotary_factor -> Phase 1 forward loss does not converge

### phase1/
- [markdown_prose_in_python_R1_syntax](failure_patterns/phase1/markdown_prose_in_python_R1_syntax.md) — Agent wrote markdown content into .py files -> R1 SyntaxError (first recorded: mimo_7b_base, all 4 files)
- [common_codegen_failures](failure_patterns/phase1/common_codegen_failures.md) — Common code generation failure quick reference (R002/R003/R006/R007/R008, loss NaN, convert key missing, etc.)

### phase2/
- [common_convert_failures](failure_patterns/phase2/common_convert_failures.md) — Common convert failure quick reference (key missing/extra/shape error, VLM three-component YAML issues, missing environment variables, etc.)

---

## Weight Conversion System (Phase 2 Knowledge Base)

- [ARCHITECTURE](convert_checkpoint/ARCHITECTURE.md) — Overall conversion system architecture: Hub-and-Spoke design, directory structure, core abstractions, name_map mechanism, TP slicing rules
- [MODULE_FORMATS](convert_checkpoint/MODULE_FORMATS.md) — Module weight format overview: Attention (7 types), MLP (3 types), MoE (6 types), Embedding, MTP, LayerNorm, with decision quick-reference table
- [CUSTOM_CONVERTERS](convert_checkpoint/CUSTOM_CONVERTERS.md) — Detailed reference for 5 custom converters: design patterns, algorithms, when to create new ones
- [ADAPTATION_GUIDE](convert_checkpoint/ADAPTATION_GUIDE.md) — Step-by-step guide for adapting weight conversion for new models: Tier 1/2/3 decisions, YAML templates, verification procedures

---

## Templates & Rules (Tool Files, Read-Only)

> **Usage Convention**: Before generating code, you must read the corresponding template to ensure import paths, class structure, and placeholder replacements are consistent with the template.

- [linter RULES](linter_rules/RULES.md) — R001-R020 check details

### templates/config/ — Config Data Class Templates
- `dense_config.py.tpl` — Dense model config (inherits BaseModelConfig)
- `moe_config.py.tpl` — MoE model config (inherits BaseModelConfig, with MoE-specific fields)

### templates/attention/ — Attention layer_spec Templates
- `mla.py.tpl` — Multi-Latent Attention (MLASelfAttention, imported from multi_latent_attention)
- `gqa.py.tpl` — Grouped Query Attention (Dense model)
- `gqa_moe_vl.py.tpl` — GQA + MoE + VL combination

### templates/ffn/ — FFN layer_spec Templates
- `swiglu_dense.py.tpl` — SwiGLU Dense FFN
- `moe_ffn.py.tpl` — MoE FFN (includes `_get_mlp_module_spec`)
- `geglu_dense.py.tpl` — GeGLU Dense FFN

### templates/convert/ — Weight Conversion YAML Templates
- `dense_llm_convert.yaml.tpl` — Dense LLM conversion config
- `moe_llm_convert.yaml.tpl` — MoE LLM conversion config
- `image_encoder_convert.yaml.tpl` — Vision encoder conversion config (includes FULLATT_INDEXES)
- `image_projector_convert.yaml.tpl` — Vision projector conversion config

### templates/scripts/ — Training/Conversion Shell Script Templates
- `pretrain_dense.sh.tpl` / `pretrain_moe.sh.tpl` — Pretrain launch scripts
- `sft_dense.sh.tpl` / `sft_moe.sh.tpl` — SFT launch scripts
- `convert_llm_hf_to_mcore.sh.tpl` — LLM conversion script
- `convert_vlm_hf_to_mcore.sh.tpl` — VLM conversion script (includes 3 convert calls)

### templates/yaml/ — Model YAML Config Templates
- `dense_model.yaml.tpl` / `moe_model.yaml.tpl` — LLM model configs
- `image_encoder.yaml.tpl` / `image_projector.yaml.tpl` — Vision module configs
- `vlm_composite.yaml.tpl` — VLM multimodal composite config

---

## QRH — Quick Reference Handbook (Runtime Common Issues Quick Reference)

When encountering resource or environment issues during GPU task execution, **check the QRH first and attempt self-repair before retrying**, to avoid unnecessary HUMAN_NEEDED.

- [gpu_resource_adjustment](qrh/gpu_resource_adjustment.md) — GPU resource dynamic adjustment: diagnosing available GPUs, specifying CUDA devices to skip failed GPUs, adjusting TP/PP/EP parallel strategies, VLM encoder TP independent adjustment
- [environment_setup](qrh/environment_setup.md) — Runtime environment configuration: PYTHONPATH concatenation patterns (4 task types), module-to-path mapping, referencing existing scripts to set environment variables
