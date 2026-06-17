# VLM Checkpoint Convert Script Template (HF → mcore)
# Applicable scenarios: VLM (language + vision + projector) HF to mcore checkpoint conversion
# Reference: qwen2.5_vl/checkpoint_convert/convert_qwen2.5_vl_7b_hf_to_mcore.sh,
#            internvl2.5/checkpoint_convert/convert_internvl2.5_8b_hf_to_mcore.sh
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid conversion script
# Process: Convert LLM / encoder / projector / patch separately → merge

#! /bin/bash

export LOONGFORGE_PATH=${LOONGFORGE_PATH:-"/workspace/LoongForge"}
MEGATRON_PATH=${MEGATRON_PATH:-"/workspace/Loong-Megatron"}
CONVERT_CHECKPOINT_PATH="$LOONGFORGE_PATH/tools/convert_checkpoint"

LOAD={{HF_CKPT_PATH}}
SAVE={{MCORE_CKPT_PATH}}

SAVE_LANGUAGE_MODEL={{TMP_DIR}}/language-mcore
SAVE_VISION_MODEL={{TMP_DIR}}/vision-model-mcore
SAVE_ADAPTER={{TMP_DIR}}/adapter-mcore
SAVE_PATCH={{TMP_DIR}}/patch-mcore

MODEL_CONFIG_FILE=${LOONGFORGE_PATH}/configs/models/{{VLM_FAMILY_DIR}}/{{VLM_YAML}}

FOUNDATION_CONVERT_FILE=${LOONGFORGE_PATH}/configs/models/{{LLM_FAMILY_DIR}}/ckpt_convert/{{LLM_CONVERT_YAML}}
IMAGE_ENCODER_CONVERT_FILE=${LOONGFORGE_PATH}/configs/models/image_encoder/ckpt_convert/{{ENC_CONVERT_YAML}}
IMAGE_PROJECTOR_CONVERT_FILE=${LOONGFORGE_PATH}/configs/models/image_projector/ckpt_convert/{{PROJ_CONVERT_YAML}}

ETP={{ENC_TP}}
DTP={{DEC_TP}}
PP={{PP}}
# {{VPP_LINE}} Uncomment when using virtual pipeline:
# VPP={{VPP}}
# CUSTOM_PIPELINE_LAYERS={{CUSTOM_PIPELINE_LAYERS}}

# ── Step 1: Convert Language Model ─────────────────────────────────
PYTHONPATH=$MEGATRON_PATH:$PYTHONPATH \
    python $CONVERT_CHECKPOINT_PATH/module_convertor/model.py \
    --load_platform=huggingface \
    --save_platform=mcore \
    --config_file $MODEL_CONFIG_FILE \
    --convert_file $FOUNDATION_CONVERT_FILE \
    --tensor_model_parallel_size=$DTP \
    --pipeline_model_parallel_size=$PP \
    --load_ckpt_path=$LOAD \
    --save_ckpt_path=$SAVE_LANGUAGE_MODEL \
    --safetensors \
    --no_save_optim \
    --no_load_optim
    # {{VPP_ARGS}} Uncomment the following lines for virtual pipeline, and add \ at the end of --no_load_optim above:
    # --num-virtual-stages-per-pipeline-rank=$VPP \
    # --custom_pipeline_layers=$CUSTOM_PIPELINE_LAYERS

# ── Step 2: Convert Vision Encoder ──────────────────────────────────
PYTHONPATH=$MEGATRON_PATH:$PYTHONPATH \
    python $CONVERT_CHECKPOINT_PATH/module_convertor/model.py \
    --load_platform=huggingface \
    --save_platform=mcore \
    --config_file $MODEL_CONFIG_FILE \
    --convert_file $IMAGE_ENCODER_CONVERT_FILE \
    --tensor_model_parallel_size=$ETP \
    --load_ckpt_path=$LOAD \
    --save_ckpt_path=$SAVE_VISION_MODEL \
    --safetensors \
    --no_save_optim \
    --no_load_optim

# ── Step 3: Convert Projector / Adapter ────────────────────────────
PYTHONPATH=$MEGATRON_PATH:$PYTHONPATH \
    python $CONVERT_CHECKPOINT_PATH/module_convertor/{{ADAPTER_SCRIPT}} \
    --load_platform=huggingface \
    --save_platform=mcore \
    --config_file $MODEL_CONFIG_FILE \
    --convert_file $IMAGE_PROJECTOR_CONVERT_FILE \
    --tensor_model_parallel_size $DTP \
    --load_ckpt_path=$LOAD \
    --save_ckpt_path=$SAVE_ADAPTER \
    --safetensors \
    --no_save_optim \
    --no_load_optim

# ── Step 4: Convert Vision Patch ────────────────────────────────────
PYTHONPATH=$MEGATRON_PATH:$PYTHONPATH \
    python $CONVERT_CHECKPOINT_PATH/module_convertor/vision_patch.py \
    --load_platform=huggingface \
    --save_platform=mcore \
    --config_file $MODEL_CONFIG_FILE \
    --convert_file $IMAGE_ENCODER_CONVERT_FILE \
    --tensor_model_parallel_size=$ETP \
    --load_ckpt_path=$LOAD \
    --save_ckpt_path=$SAVE_PATCH \
    --safetensors \
    --no_save_optim \
    --no_load_optim

# ── Step 5: Merge all modules ─────────────────────────────────────────
PYTHONPATH=$MEGATRON_PATH:$LOONGFORGE_PATH:$PYTHONPATH \
    python $CONVERT_CHECKPOINT_PATH/mcore/{{MERGE_SCRIPT}} \
    --megatron_path $MEGATRON_PATH \
    --language_model_path $SAVE_LANGUAGE_MODEL/release \
    --vision_model_path $SAVE_VISION_MODEL/release \
    --vision_patch $SAVE_PATCH/release \
    --adapter_path $SAVE_ADAPTER/release \
    --encoder_tensor_model_parallel_size $ETP \
    --decoder_tensor_model_parallel_size $DTP \
    --pipeline_model_parallel_size $PP \
    --save_ckpt_path $SAVE/release \
    --config_file $MODEL_CONFIG_FILE
    # {{VPP_MERGE}} Uncomment the following lines for virtual pipeline, and add \ at the end of --config_file above:
    # --num_virtual_stages_per_pipeline_rank=$VPP

echo release > $SAVE/latest_checkpointed_iteration.txt

# ── Clean up temporary files ─────────────────────────────────────────
rm -rf $SAVE_LANGUAGE_MODEL
rm -rf $SAVE_VISION_MODEL
rm -rf $SAVE_ADAPTER
rm -rf $SAVE_PATCH

# ============================================================
# Variable substitution guide:
#   {{HF_CKPT_PATH}}            → HF checkpoint path
#   {{MCORE_CKPT_PATH}}         → mcore final output path
#   {{TMP_DIR}}                  → Temporary intermediate files directory
#   {{VLM_FAMILY_DIR}}          → VLM config directory (e.g. qwen2.5vl, internvl2.5)
#   {{VLM_YAML}}                → VLM composite YAML (e.g. qwen2_5_vl_7b.yaml)
#   {{LLM_FAMILY_DIR}}          → LLM config directory (e.g. qwen2.5, internlm2.5)
#   {{LLM_CONVERT_YAML}}        → LLM convert YAML
#   {{ENC_CONVERT_YAML}}        → Encoder convert YAML
#   {{PROJ_CONVERT_YAML}}       → Projector convert YAML
#   {{ENC_TP}}                   → Encoder tensor parallel size
#   {{DEC_TP}}                   → Decoder (LLM) tensor parallel size
#   {{PP}}                       → Pipeline parallel size
#   {{VPP}}                      → Virtual pipeline stages
#   {{CUSTOM_PIPELINE_LAYERS}}   → Custom pipeline layer allocation (e.g. 6,8,6,8)
#   {{ADAPTER_SCRIPT}}           → Adapter conversion script name
#                                   Qwen: adapter.py
#                                   InternVL: adapter_internvl.py
#   {{MERGE_SCRIPT}}             → Merge script name
#                                   Standard: merge_megatron.py
#                                   MoE: merge_megatron_expert.py
# ============================================================
