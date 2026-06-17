# MoE LLM Pretrain Launch Script Template
# Applicable scenarios: LLM pretraining with MoE
# Reference: deepseek_v2/pretrain/pretrain_deepseek_v2_group.sh
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid launch script
# Extends pretrain_dense.sh.tpl with MoE-specific parameters

#! /bin/bash
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

MEGATRON_PATH=${MEGATRON_PATH:-"/workspace/Loong-Megatron"}
LOONGFORGE_PATH=${LOONGFORGE_PATH:-"/workspace/LoongForge"}

DATA_PATH=${DATA_PATH:-"{{DATA_PATH}}"}

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
    # {{MODEL_EXTRA_ARGS}} Model-specific parameters (e.g. MLA, RoPE, etc.):
    # --rotary-base {{ROTARY_BASE}}
    # --norm-epsilon {{NORM_EPS}}
    # --enable-fa-within-mla                                   # DeepSeek MLA models
    # --multi-latent-attention                                  # DeepSeek MLA models
)

DATA_ARGS=(
    --tokenizer-type HFTokenizer
    --hf-tokenizer-path $TOKENIZER_PATH
    --eod-mask-loss
    --data-path $DATA_PATH
    --split {{DATA_SPLIT}}
)

TRAINING_ARGS=(
    --training-phase pretrain
    --seq-length {{SEQ_LENGTH}}
    --max-position-embeddings {{MAX_POS_EMB}}
    --init-method-std {{INIT_STD}}
    --micro-batch-size {{MICRO_BS}}
    --global-batch-size {{GLOBAL_BS}}
    --lr {{LR}}
    --min-lr {{MIN_LR}}
    --clip-grad 1.0
    --weight-decay {{WEIGHT_DECAY}}
    --optimizer adam
    --adam-beta1 0.9
    --adam-beta2 0.95
    --adam-eps {{ADAM_EPS}}
    --norm-epsilon {{NORM_EPS}}
    --train-iters {{TRAIN_ITERS}}
    --lr-decay-iters {{LR_DECAY_ITERS}}
    --lr-decay-style cosine
    --lr-warmup-fraction 0.002
    --initial-loss-scale 65536
    --bf16
    --load $CHECKPOINT_PATH
    --save $CHECKPOINT_PATH
    --save-interval {{SAVE_INTERVAL}}
    --eval-interval {{EVAL_INTERVAL}}
    --eval-iters 10
    #--ckpt-step 0
    #--no-load-optim
    #--no-load-rng
)

# ── MoE-specific parameters ────────────────────────────────────────────────
MOE_ARGS=(
    --moe-router-load-balancing-type {{MOE_LB_TYPE}}            # aux_loss | seq_aux_loss
    --moe-router-topk {{MOE_TOPK}}
    --moe-aux-loss-coeff {{MOE_AUX_LOSS_COEFF}}                # e.g. 1e-3
    --moe-grouped-gemm
    # {{MOE_EXTRA_ARGS}} Model-specific MoE parameters:
    # --moe-router-num-groups {{MOE_NUM_GROUPS}}
    # --moe-router-group-topk {{MOE_GROUP_TOPK}}
    # --moe-router-topk-scaling-factor {{MOE_SCALING_FACTOR}}
    # --moe-router-score-function {{MOE_SCORE_FUNC}}            # softmax | sigmoid
    # --moe-router-enable-expert-bias                           # DeepSeek-V3
    # --moe-router-bias-update-rate {{MOE_BIAS_RATE}}
    # --moe-router-dtype {{MOE_ROUTER_DTYPE}}                   # fp32
)

MODEL_PARALLEL_ARGS=(
    --tensor-model-parallel-size {{TP}}
    --pipeline-model-parallel-size {{PP}}
    --expert-model-parallel-size {{EP}}
    # {{EP_TP}} Expert tensor parallelism (needed for large-scale models):
    # --expert-tensor-parallel-size {{ETP}}
    --sequence-parallel
    --moe-token-dispatcher-type {{MOE_DISPATCHER}}              # alltoall | flex
    --use-distributed-optimizer
    --distributed-backend nccl
    # {{EXTRA_PARALLEL_ARGS}} Additional parameters for large-scale models:
    # --overlap-grad-reduce
    # --overlap-param-gather
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
    ${MOE_ARGS[@]} \
    ${MODEL_PARALLEL_ARGS[@]} \
    ${LOGGING_ARGS[@]}

# ============================================================
# Variable substitution guide (base fields same as pretrain_dense.sh.tpl; below are MoE-specific):
#   {{MOE_LB_TYPE}}             → Router load balancing type (aux_loss, seq_aux_loss)
#   {{MOE_TOPK}}                → Router top-k (e.g. 6, 8)
#   {{MOE_AUX_LOSS_COEFF}}      → Auxiliary loss coefficient (e.g. 1e-3)
#   {{MOE_NUM_GROUPS}}          → Router group count (e.g. 8)
#   {{MOE_GROUP_TOPK}}          → Group top-k (e.g. 3, 4)
#   {{MOE_SCALING_FACTOR}}      → Top-k scaling factor (e.g. 16.0, 2.5)
#   {{MOE_SCORE_FUNC}}          → Score function (softmax, sigmoid)
#   {{MOE_DISPATCHER}}          → Token dispatcher type (alltoall, flex)
#   {{EP}}                      → Expert parallel size (e.g. 8, 32)
#   {{ETP}}                     → Expert tensor parallel size (e.g. 1)
# ============================================================
