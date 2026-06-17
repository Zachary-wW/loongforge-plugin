# Dense LLM Pretrain Launch Script Template
# Applicable scenarios: Standard Dense LLM pretraining
# Reference: qwen2.5/pretrain/pretrain_qwen2.5_7b.sh, llama3.1/pretrain/pretrain_llama3.1_8b.sh
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid launch script

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
    # {{MODEL_EXTRA_ARGS}} Model-specific parameters:
    # --rotary-base {{ROTARY_BASE}}
    # --rotary-seq-len-interpolation-factor 1
)

DATA_ARGS=(
    --tokenizer-type HFTokenizer
    --hf-tokenizer-path $TOKENIZER_PATH
    --eod-mask-loss
    --data-path $DATA_PATH
    --split {{DATA_SPLIT}}                                      # e.g. 949,50,1 or 99,1,0
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

MODEL_PARALLEL_ARGS=(
    --tensor-model-parallel-size {{TP}}
    --pipeline-model-parallel-size {{PP}}
    --use-distributed-optimizer
    --overlap-grad-reduce
    --overlap-param-gather
    --distributed-backend nccl
    #--sequence-parallel
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
    ${MODEL_PARALLEL_ARGS[@]} \
    ${LOGGING_ARGS[@]}

# ============================================================
# Variable substitution guide:
#   {{MODEL_NAME}}       → --model-name value (e.g. qwen2.5-7b, llama3.1-8b)
#   {{DATA_PATH}}        → Pretraining data path
#   {{TOKENIZER_PATH}}   → HF tokenizer path
#   {{CHECKPOINT_PATH}}  → Checkpoint path
#   {{TENSORBOARD_PATH}} → TensorBoard log path
#   {{DATA_SPLIT}}       → Data split ratio (e.g. 949,50,1)
#   {{SEQ_LENGTH}}       → Sequence length (e.g. 4096)
#   {{MAX_POS_EMB}}      → Max position embeddings (e.g. 4096, 32768)
#   {{INIT_STD}}         → Initialization std (e.g. 0.02, 0.006)
#   {{MICRO_BS}}         → Micro batch size (typically 1)
#   {{GLOBAL_BS}}        → Global batch size (e.g. 1024)
#   {{LR}}               → Learning rate (e.g. 0.0002, 1.0e-5)
#   {{MIN_LR}}           → Minimum learning rate (e.g. 1.0e-5, 1.0e-6)
#   {{WEIGHT_DECAY}}     → Weight decay (e.g. 0.01, 0.1)
#   {{ADAM_EPS}}          → Adam epsilon (e.g. 1e-05, 1e-08)
#   {{NORM_EPS}}          → Norm epsilon (e.g. 1e-05, 1e-6)
#   {{TRAIN_ITERS}}      → Training iterations
#   {{LR_DECAY_ITERS}}   → LR decay iterations (usually equals train_iters)
#   {{SAVE_INTERVAL}}    → Save interval (e.g. 5000)
#   {{EVAL_INTERVAL}}    → Eval interval (e.g. 1000)
#   {{TP}}               → Tensor parallel size (e.g. 1, 2, 4)
#   {{PP}}               → Pipeline parallel size (e.g. 1, 2, 4)
#   {{ROTARY_BASE}}      → RoPE base (e.g. 500000, 1000000)
# ============================================================
