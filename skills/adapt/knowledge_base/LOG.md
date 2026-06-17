# LoongForge Knowledge Base Log

> Format: `## [YYYY-MM-DD] <event_type> | <subject>`
> event_type: adapt / query / lint / update
> Append Rule: Append only; do not modify existing entries.
> grep usage: `grep "^## \[" LOG.md | tail -5`

## [2026-04-13] adapt | knowledge_base restructure
- Completed directory restructure per three-layer separation plan (Plan B)
- Created: INDEX.md, LOG.md, schema/, wiki/, sources/
- Created: mla.md, moe.md, mtp.md, gqa_vs_mha.md under wiki/concepts/
- Migrated: arch_specs/ -> sources/, model_cards/ -> wiki/, failure_patterns/ -> wiki/failure_patterns/
- Updated path references: SKILL.md, phase0/phase1 agent, linter_check.md

## [2026-04-14] update | knowledge_base simplification restructure
- Simplified sources/: reduced from 15 yamls to 9 (6 LLM + 3 VLM), removed structurally highly similar redundant families
- Merged traps: moved trap entries from each family card in wiki/llm/ and wiki/vlm/ into the corresponding sources yaml `traps` section
- Deleted: wiki/llm/ (5 files), wiki/vlm/ (4 files), wiki/concepts/ (4 files)
- Retained: wiki/failure_patterns/ (4 mimo failure records, the only non-derivable runtime content)
- Deleted: weight_mapping_rules/mapping_rules.md (removed; Phase 2 now references candidate convert yaml + arch_spec.yaml)
- Updated: SKILL.md knowledge base index table (removed wiki family card rows and mapping_rules.md row)
- Updated: INDEX.md maintenance procedures and index entries, aligned with new structure

## [2026-04-21] update | QRH Quick Reference Handbook + Phase 2 / backup-model optimization
- Created: knowledge_base/qrh/ directory
- Created: qrh/gpu_resource_adjustment.md — GPU resource dynamic adjustment (GPU count, parallel strategy, CUDA device selection)
- Created: qrh/environment_setup.md — Runtime environment configuration (PYTHONPATH concatenation patterns, module path mapping)
- Updated: SKILL.md knowledge base index table added QRH entry, HUMAN_NEEDED table added GPU/environment issue troubleshooting path
- Updated: INDEX.md added QRH section
- Updated: references/phases/phase2_convert_agent.md Step 5 restructured into 5a (HF Roundtrip Test) + 5b (offline conversion) + 5c (offline Roundtrip verification)
- Updated: references/tools/backup-model/SKILL.md added VLM module config YAML backup and deletion (foundation/encoder/projector module YAMLs)

## [2026-04-24] update | templates standardization alignment
- Fixed config templates: unified import paths to long form (`from loongforge.models.common.base_model_config import BaseModelConfig`), added model_type generation, added register_model_config import hints
- Fixed attention/mla.py.tpl: MLASelfAttention import path changed to `megatron.core.transformer.multi_latent_attention`, moved to module top level
- Reverted scripts shebang: unified to `#! /bin/bash` (consistent with existing scripts in examples/)
- Supplemented image_encoder_convert.yaml.tpl: FULLATT_INDEXES variable documentation
- Unified moe_config.py.tpl placeholder naming ({{FAMILY}}/{{FAMILY_CLASS}}/{{FAMILY_UPPER}}/{{FAMILY_CONST}})
- Verification: compared against 10+ actual config/layer_spec/script files, confirmed templates are consistent with existing code
- Updated INDEX.md: expanded Templates section with complete file listing
- Updated SKILL.md / phase1_codegen_agent.md / linter-check SKILL: added template reference hints

## [2026-05-28] adapt | deepseek_v4_flash_base
- sources/llm/deepseek_v3.yaml: appended traps +6, code_paths existing, omni_reference existing
- Phase status: P0 passed / P1 passed / P2 passed / P3 blocked / P4 blocked
- Major diff components: positional_encoding, attention, attention_norm, flash_attention, ffn, moe_gate, moe_experts, moe_layer, decoder_layer, mtp, model, config
- New traps count: 6
- Note: Phase 3 real-weight loss-diff did not pass (latest loss_diff=0.5412483215332031 > 0.01); Phase 4 was skipped per user instruction and not validated.

## [2026-06-01] adapt | deepseek_v4_flash
- Created: sources/llm/deepseek_v4_flash.yaml; updated INDEX.md source entry.
- Phase status: P0 passed / P1 passed / P2 passed / P3 passed / P4 passed / P5 passed.
- Major diff components: embedding, positional_encoding, attention, attention_norm, ffn, moe_gate, moe_experts, moe_shared_experts, moe_layer, decoder_layer, mtp, lm_head, model, causal_lm, config.
- Phase 3 real-weight loss-diff passed with threshold 0.01: hf_loss=20.0229434967041, omni_loss=20.02294158935547, loss_diff=0.0000019073486328125.
- New traps count: 10, including hyper-connection .scale preservation, routed expert .weight suffix mismatch, FP8 block-scale materialization, and causal-mask component debugging.

## [2026-06-01] update | deepseek_v4_flash Phase 4 correction
- Corrected Phase 4 status from passed to human_needed: only the Phase 3 real-weight precision baseline had run; applicable runtime switches were not actually executed with added parameters.
- Updated: sources/llm/deepseek_v4_flash.yaml validation.phase4 now records human_needed and the missing mutable torchrun/optimizer-step Phase 3 baseline.
- Updated: adaptation_run_20260601_170932 Phase 4 artifacts now report feature-compat human_needed with fallback_phase=phase3.
- Phase 5 knowledge update remains provisional until Phase 4 is rerun from a proper torchrun/optimizer-step baseline.

## [2026-06-01] update | deepseek_v4_flash runtime Phase 4 rerun
- Produced real LoongForge torchrun optimizer-step Phase 3 baselines for pretrain and SFT from examples/deepseek_v4_flash scripts.
- Reran Phase 4 switch matrix from mutable runtime scripts: EP, SFT Packing, Fused Linear Cross Entropy, optimizer CPU offload, and low-precision optimizer states passed.
- Recorded concrete failures: TP blocked by sliced num_query_groups=1 vs TP=2, PP/VPP blocked by pipeline deallocating a view tensor, FP8 blockwise training OOM on single-GPU smoke.
- Updated: sources/llm/deepseek_v4_flash.yaml validation.phase4 now records human_needed with passed/failed_switches/human_needed switch details.

## [2026-06-02] update | deepseek_v4_flash real-script Phase 3/4/5 correction
- Corrected Phase 3 record to require the generated real pretrain script path: examples/deepseek_v4_flash/pretrain/pretrain_deepseek_v4_flash.sh -> torchrun -> loongforge/train.py.
- HF recomputed CE on the exported real runtime batch on CUDA; hf_loss_mean and runtime_loss_mean both equal 19.44605255126953, loss_mean_diff=0.0 <= 0.01.
- Corrected VPP Phase 4 evidence: the rerun failed during model CUDA initialization with OOM on rank1, not merely because PP had failed earlier.
- Updated: Phase 4/5 artifacts and sources/llm/deepseek_v4_flash.yaml now record human_needed final status because TP/PP/VPP/FP8 applicable failures remain unresolved; failed remains nested switch evidence only.
