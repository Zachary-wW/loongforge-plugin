# MoE LLM SFT Launch Script Template
# Applicable scenarios: LLM supervised fine-tuning (SFT) with MoE
# Reference: deepseek_v2/finetuning/sft_deepseek_v2_group.sh
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid launch script
# Extends sft_dense.sh.tpl with MoE-specific parameters

#! /bin/bash
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

MEGATRON_PATH=${MEGATRON_PATH:-"/workspace/Loong-Megatron"}
LOONGFORGE_PATH=${LOONGFORGE_PATH:-"/workspace/LoongForge"}

DATA_PATH=${DATA_PATH:-"{{SFT_DATA_PATH}}"}

#DATA_CACHE_PATH=${DATA_CACHE_PATH:-"{{DATA_CACHE_PATH}}"}

TOKENIZER_PATH=${TOKENIZER_PATH:-"{{TOKENIZER_PATH}}"}

CHECKPOINT_PATH=${CHECKPOINT_PATH:-"{{CHECKPOINT_PATH}}"}

TENSORBOARD_PATH=${TENSORBOARD_PATH:-"{{TENSORBOARD_PATH}}"}

GPUS_PER_NODE=8

# Change for multinode config
MASTER_ADDR=${MASTER_ADDR:-"localhost"}
MASTER_PORT=${MASTER_PORT:-"6000"}
NNODES=${WORLD_SIZE:-"1"}
NODE_RANK=${RANK:-"0"}

DISTRIBUTED_ARGS=(
    --nproc_per_node $GPUS_PER_NODE
    --nnodes $NNODES
    --node_rank $NODE_RANK
    --master_addr $MASTER_ADDR
    --master_port $MASTER_PORT
)

MODEL_ARGS=(
    --model-name {{MODEL_NAME}}
    # {{MODEL_EXTRA_ARGS}}
    # --rotary-base {{ROTARY_BASE}}
    # --norm-epsilon {{NORM_EPS}}
    # --enable-fa-within-mla
    # --multi-latent-attention
)

DATA_ARGS=(
    --tokenizer-type HFTokenizer
    --hf-tokenizer-path $TOKENIZER_PATH
    --data-path $DATA_PATH
    --split 100,0,0
)

SFT_ARGS=(
    --chat-template {{CHAT_TEMPLATE}}
    --sft-num-preprocess-workers 16
    --no-check-for-nan-in-loss-and-grad
    #--is-tokenized-data
    #--packing-sft-data
    #--sft-data-streaming
)

TRAINING_ARGS=(
    --training-phase sft
    --seq-length {{SEQ_LENGTH}}
    --max-position-embeddings {{MAX_POS_EMB}}
    --init-method-std {{INIT_STD}}
    --micro-batch-size {{MICRO_BS}}
    --global-batch-size {{SFT_GLOBAL_BS}}
    --lr {{SFT_LR}}
    --min-lr {{SFT_MIN_LR}}
    --clip-grad 1.0
    --weight-decay {{WEIGHT_DECAY}}
    --optimizer adam
    --adam-beta1 0.9
    --adam-beta2 0.95
    --adam-eps {{ADAM_EPS}}
    --norm-epsilon {{NORM_EPS}}
    --train-iters {{SFT_TRAIN_ITERS}}
    --lr-decay-iters {{SFT_LR_DECAY_ITERS}}
    --lr-decay-style cosine
    --lr-warmup-fraction 0.002
    --initial-loss-scale 65536
    --bf16
    --load $CHECKPOINT_PATH
    --save $CHECKPOINT_PATH
    --save-interval {{SFT_SAVE_INTERVAL}}
    --eval-interval {{SFT_EVAL_INTERVAL}}
    --eval-iters 10
    #--ckpt-step 0
    #--no-load-optim
    #--no-load-rng
)

# ── MoE-specific parameters ────────────────────────────────────────────────
MOE_ARGS=(
    --moe-router-load-balancing-type {{MOE_LB_TYPE}}
    --moe-router-topk {{MOE_TOPK}}
    --moe-aux-loss-coeff {{MOE_AUX_LOSS_COEFF}}
    --moe-grouped-gemm
    # {{MOE_EXTRA_ARGS}}
    # --moe-router-num-groups {{MOE_NUM_GROUPS}}
    # --moe-router-group-topk {{MOE_GROUP_TOPK}}
    # --moe-router-topk-scaling-factor {{MOE_SCALING_FACTOR}}
    # --moe-router-score-function {{MOE_SCORE_FUNC}}
    # --moe-router-enable-expert-bias
    # --moe-router-bias-update-rate {{MOE_BIAS_RATE}}
    # --moe-router-dtype {{MOE_ROUTER_DTYPE}}
)

MODEL_PARALLEL_ARGS=(
    --tensor-model-parallel-size {{TP}}
    --pipeline-model-parallel-size {{PP}}
    --expert-model-parallel-size {{EP}}
    # {{EP_TP}}
    # --expert-tensor-parallel-size {{ETP}}
    --sequence-parallel
    --moe-token-dispatcher-type {{MOE_DISPATCHER}}
    --use-distributed-optimizer
    --distributed-backend nccl
)

LOGGING_ARGS=(
    --log-interval 1
    --tensorboard-dir ${TENSORBOARD_PATH}
    --log-timers-to-tensorboard
)

if [ -n "${WANDB_API_KEY}" ]; then
    LOGGING_ARGS+=(
        --wandb-project ${WANDB_PROJECT}
        --wandb-exp-name ${WANDB_NAME}
    )
fi

PYTHONPATH=$MEGATRON_PATH:$LOONGFORGE_PATH:$PYTHONPATH \
    torchrun ${DISTRIBUTED_ARGS[@]} \
    $LOONGFORGE_PATH/loongforge/train.py \
    ${MODEL_ARGS[@]} \
    ${DATA_ARGS[@]} \
    ${TRAINING_ARGS[@]} \
    ${SFT_ARGS[@]} \
    ${MOE_ARGS[@]} \
    ${MODEL_PARALLEL_ARGS[@]} \
    ${LOGGING_ARGS[@]}

# ============================================================
# Variable substitution guide:
#   Base fields same as sft_dense.sh.tpl + pretrain_moe.sh.tpl
#   MoE parameters same as pretrain_moe.sh.tpl
#   SFT parameters same as sft_dense.sh.tpl
# ============================================================
