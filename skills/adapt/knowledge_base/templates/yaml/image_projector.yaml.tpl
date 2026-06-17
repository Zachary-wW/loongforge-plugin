# Image Projector YAML Config Template
# Applicable scenarios: Vision projector configuration (MLP Adapter and variants)
# Reference: image_projector/qwen_mlp_adapter.yaml, image_projector/intern_mlp_adapter.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid YAML config

_target_: loongforge.models.encoder.{{PROJECTOR_CONFIG_CLASS}}

normalization: {{PROJ_NORMALIZATION}}             # "RMSNorm" | "LayerNorm"
# {{BIAS}} Required for Qwen-style:
# add_bias_linear: True
model_type: "{{PROJ_MODEL_TYPE}}"
# {{LAYERNORM_EPS}} Required for LayerNorm models:
# layernorm_epsilon: {{PROJ_LAYERNORM_EPSILON}}
# {{EXTRA_FIELDS}} Special projectors like PatchMerger need extra fields:
# gated_linear_unit: False

convert_file: ${oc.env:LOONGFORGE_PATH}/configs/models/image_projector/ckpt_convert/{{PROJ_CONVERT_YAML}}

# ============================================================
# Variable substitution guide:
#   {{PROJECTOR_CONFIG_CLASS}}   → Config class name (e.g. MLPAdapterConfig, InternMLPAdapterConfig,
#                                    PatchMergerMLPAdapterConfig)
#   {{PROJ_NORMALIZATION}}       → "RMSNorm" (Qwen) | "LayerNorm" (InternVL, PatchMerger)
#   {{PROJ_MODEL_TYPE}}          → e.g. "qwen2_5_vl_adapter", "intern_adapter", "patch_merger_adapter"
#   {{PROJ_LAYERNORM_EPSILON}}   → e.g. 1e-5 (required for LayerNorm models)
#   {{PROJ_CONVERT_YAML}}        → Convert YAML filename
#
# Field addition/removal rules:
#   - Qwen-style: add_bias_linear=True, normalization=RMSNorm
#   - InternVL-style: normalization=LayerNorm, layernorm_epsilon=1e-5
#   - PatchMerger-style: normalization=LayerNorm, gated_linear_unit=False
#   - Projector configs are typically minimal; most parameters are overridden by the VLM composite YAML
# ============================================================
