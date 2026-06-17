# LLM Checkpoint Convert Script Template (HF → mcore)
# Applicable scenarios: Pure LLM (Dense or MoE) HF to mcore checkpoint conversion
# Reference: qwen2.5/checkpoint_convert/convert_qwen2.5_7b_hf_to_mcore.sh
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid conversion script

#! /bin/bash

export LOONGFORGE_PATH=${LOONGFORGE_PATH:-"/workspace/LoongForge"}
MEGATRON_PATH=${MEGATRON_PATH:-"/workspace/Loong-Megatron"}
CONVERT_CHECKPOINT_PATH="$LOONGFORGE_PATH/tools/convert_checkpoint"

LOAD={{HF_CKPT_PATH}}
SAVE={{MCORE_CKPT_PATH}}

MODEL_CONFIG_FILE=${LOONGFORGE_PATH}/configs/models/{{FAMILY_DIR}}/{{MODEL_YAML}}

CONVERT_FILE=${LOONGFORGE_PATH}/configs/models/{{FAMILY_DIR}}/ckpt_convert/{{CONVERT_YAML}}

TP={{TP}}
PP={{PP}}
# {{EP_LINE}} Uncomment for MoE models:
# EP={{EP}}

PYTHONPATH=$MEGATRON_PATH:$PYTHONPATH \
    python $CONVERT_CHECKPOINT_PATH/module_convertor/model.py \
    --load_platform=huggingface \
    --save_platform=mcore \
    --config_file $MODEL_CONFIG_FILE \
    --convert_file $CONVERT_FILE \
    --tensor_model_parallel_size=$TP \
    --pipeline_model_parallel_size=$PP \
    --load_ckpt_path=$LOAD \
    --save_ckpt_path=$SAVE \
    --safetensors \
    --no_save_optim \
    --no_load_optim
    # {{EP_ARG}} Uncomment for MoE models:
    # --expert_parallel_size=$EP \
    # {{ETP_ARG}} Expert tensor parallelism:
    # --expert_tensor_parallel_size={{ETP}} \
    # {{MAX_WORKERS}} Speed up for large models:
    # --max_workers=32

# ============================================================
# Variable substitution guide:
#   {{HF_CKPT_PATH}}    → HF checkpoint path (e.g. /mnt/cluster/huggingface.co/Qwen/Qwen2.5-7B)
#   {{MCORE_CKPT_PATH}}  → mcore output path
#   {{FAMILY_DIR}}       → Model family directory (e.g. qwen2.5, llama3)
#   {{MODEL_YAML}}       → Model config YAML filename (e.g. qwen2_5_7b.yaml)
#   {{CONVERT_YAML}}     → Conversion config YAML filename (e.g. qwen2_5_convert_llm.yaml)
#   {{TP}}               → Tensor parallel size
#   {{PP}}               → Pipeline parallel size
#   {{EP}}               → Expert parallel size (MoE models)
#   {{ETP}}              → Expert tensor parallel size (large-scale MoE)
# ============================================================
