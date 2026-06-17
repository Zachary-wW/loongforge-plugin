# VLM Composite YAML Config Template
# Applicable scenarios: VLM composite configuration (image_encoder + image_projector + foundation LLM)
# Reference: qwen2.5vl/qwen2_5_vl_7b.yaml, internvl2.5/internvl2_5_8b.yaml
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid YAML config

# hydra:
#   searchpath:
#     - file://configs/

defaults:
  - ../../models/image_encoder@model.image_encoder: {{ENCODER_YAML_NAME}}
  - ../../models/image_projector@model.image_projector: {{PROJECTOR_YAML_NAME}}
  - ../../models/{{LLM_FAMILY_DIR}}@model.foundation: {{LLM_YAML_NAME}}
  - _self_

model:
  model_type: {{VLM_MODEL_TYPE}}
  # {{LOSS_FUNC}} Uncomment for custom loss:
  loss_func: ${loss_func:{{LOSS_FUNC_NAME}}}
  # {{POSITION_IDX_FUNC}} Uncomment if a custom position index function is needed:
  # position_idx_func: ${position_func:{{POSITION_IDX_FUNC_NAME}}}
  # {{MIX_FLAGS}} Uncomment if mix_used flags are needed:
  # mix_used_vision_encoder: true
  # mix_used_vision_projector: true

  foundation:
    # {{ROTARY_EMB}} Uncomment to override foundation RoPE:
    # rotary_emb_func: "{{ROTARY_EMB_FUNC}}"
    # rotary_base: {{ROTARY_BASE}}
    # {{MROPE}} Uncomment if mRoPE is needed:
    # mrope_section: {{MROPE_SECTION}}
    # {{MODEL_SPEC}} Uncomment to override foundation layer_spec:
    # model_spec: ["loongforge.models.foundation.{{LLM_SPEC_MODULE}}", "{{LLM_SPEC_FUNC}}"]
    # {{FOUNDATION_CONVERT}} Uncomment to override foundation convert_file:
    # convert_file: ${oc.env:LOONGFORGE_PATH}/configs/models/{{LLM_FAMILY_DIR}}/ckpt_convert/{{LLM_CONVERT_YAML}}

  # {{ENCODER_OVERRIDES}} Uncomment to override encoder parameters:
  # image_encoder:
  #   model_spec: ["loongforge.models.encoder.{{ENC_SPEC_MODULE}}", "{{ENC_SPEC_FUNC}}"]

  # {{PROJECTOR_OVERRIDES}} Uncomment to override projector parameters:
  # image_projector:
  #   hidden_size: {{PROJ_HIDDEN_SIZE}}
  #   ffn_hidden_size: {{PROJ_FFN_HIDDEN_SIZE}}
  #   activation_func: ${act:{{PROJ_ACTIVATION}}}

# ============================================================
# Variable substitution guide:
#   {{ENCODER_YAML_NAME}}        → image_encoder YAML name (e.g. qwen2_5_vit, intern_vit_0.3b)
#   {{PROJECTOR_YAML_NAME}}      → image_projector YAML name (e.g. qwen_mlp_adapter, intern_mlp_adapter)
#   {{LLM_FAMILY_DIR}}           → Foundation model directory name (e.g. qwen2.5, internlm2.5)
#   {{LLM_YAML_NAME}}            → Foundation YAML name (e.g. qwen2_5_7b, internlm2_5_8b)
#   {{VLM_MODEL_TYPE}}           → VLM model_type (e.g. qwen2_5_vl, intern_vl)
#   {{LOSS_FUNC_NAME}}           → Loss function name (e.g. default, loss_func_internvl)
#   {{POSITION_IDX_FUNC_NAME}}   → Position index function name (e.g. mrope_ids, rope_ids_qwen3vl)
#   {{ROTARY_EMB_FUNC}}          → RoPE function name (e.g. Qwen2VLRotaryEmbedding, DynamicRotaryEmbedding)
#   {{ROTARY_BASE}}              → RoPE base (e.g. 1000000)
#   {{MROPE_SECTION}}            → mRoPE sections (e.g. [24, 20, 20])
#   {{LLM_SPEC_MODULE}}          → layer_spec module path (e.g. qwen2.qwen_layer_spec)
#   {{LLM_SPEC_FUNC}}            → layer_spec function name (e.g. get_qwen2_vl_layer_with_te_spec)
#   {{LLM_CONVERT_YAML}}         → Foundation convert YAML name
#
# Field addition/removal rules:
#   - No position_idx_func needed → remove that line (e.g. InternVL)
#   - No mix_used flags needed → remove that block
#   - No foundation parameter overrides needed → remove corresponding lines in foundation block
#   - No encoder/projector overrides needed → remove corresponding blocks
#   - InternVL-style: need to add image_projector.hidden_size/ffn_hidden_size
#   - Qwen-VL-style: need to add position_idx_func + mix_used flags + model_spec override
# ============================================================
