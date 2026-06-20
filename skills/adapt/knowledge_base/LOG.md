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
