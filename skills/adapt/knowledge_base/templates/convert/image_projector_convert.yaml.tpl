# Image Projector Checkpoint Convert YAML Template
# Applicable scenarios: Vision projector (MLP Adapter) HF ↔ mcore weight conversion
# Reference: image_projector/ckpt_convert/qwen_mlp_adapter_convert.yaml,
#            image_projector/ckpt_convert/intern_mlp_adapter_convert.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid conversion config
# Note: Projector conversion configs are minimal; no args section, only direct key-value mappings

hydra:
  searchpath:
    - file://${oc.env:LOONGFORGE_PATH}/configs/models/

defaults:
  - image_projector@module: ???
  - _self_

# Adapter configuration - direct weight mappings (mcore_key: hf_key)
{{ADAPTER_MAPPINGS}}
# Example - Qwen MLP Adapter:
# adapter.layernorm.weight: visual.merger.ln_q.weight
# adapter.linear_fc1.weight: visual.merger.mlp.0.weight
# adapter.linear_fc1.bias: visual.merger.mlp.0.bias
# adapter.linear_fc2.weight: visual.merger.mlp.2.weight
# adapter.linear_fc2.bias: visual.merger.mlp.2.bias
#
# Example - InternVL MLP Adapter:
# adapter.layernorm.weight: mlp1.0.weight
# adapter.layernorm.bias: mlp1.0.bias
# adapter.linear_fc1.weight: mlp1.1.weight
# adapter.linear_fc1.bias: mlp1.1.bias
# adapter.linear_fc2.weight: mlp1.3.weight
# adapter.linear_fc2.bias: mlp1.3.bias

name_map:
  mcore:
    layer_prefix: adapter. # don't remove the dot

# ============================================================
# Variable substitution guide:
#   {{ADAPTER_MAPPINGS}}  → Direct weight mappings (format: mcore_key: hf_key)
#                            One weight mapping per line, including layernorm + fc1 + fc2
#
# Mapping rules:
#   - mcore side is fixed as adapter.layernorm.{weight,bias},
#     adapter.linear_fc1.{weight,bias}, adapter.linear_fc2.{weight,bias}
#   - HF side varies by model:
#     Qwen: visual.merger.ln_q.*, visual.merger.mlp.{0,2}.*
#     InternVL: mlp1.{0,1,3}.*
#     PatchMerger: depends on specific implementation
#   - If adapter has no bias → remove .bias lines
#   - If adapter has extra layernorm (e.g. ln_q + ln_kv) → add corresponding mappings
# ============================================================
