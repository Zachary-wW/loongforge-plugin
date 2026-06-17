# Dense LLM SFT Launch Script Template
# Applicable scenarios: Standard Dense LLM supervised fine-tuning (SFT)
# Reference: qwen2.5/finetuning/sft_qwen2.5_7b.sh, llama3.1/finetuning/sft_llama3.1_8b.sh
#
# Usage: Replace all {{PLACEHOLDER}} values to produce a valid launch script
# Key differences from pretrain_dense.sh.tpl: training-phase=sft, added SFT_ARGS, split=100,0,0

#! /bin/bash
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

MEGATRON_PATH=${MEGATRON_PATH:-"/workspace/Loong-Megatron"}
LOONGFORGE_PATH=${LOONGFORGE_PATH:-"/workspace/LoongForge"}

DATA_PATH=${DATA_PATH:-"{{SFT_DATA_PATH}}"}

#DATA_CACHE_PATH=${DATA_CACHE_PATH:-"{{DATA_CACHE_PATH}}"}

#DATASET_CONFIG_PATH=${DATASET_CONFIG_PATH:-"{{DATASET_CONFIG_PATH}}"}

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
    # --rotary-seq-len-interpolation-factor 1
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

    #--train-on-prompt
    #--eod-mask-loss

    #--sft-dataset-config $DATASET_CONFIG_PATH
    #--data-cache-path $DATA_CACHE_PATH
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
    ${SFT_ARGS[@]} \
    ${MODEL_PARALLEL_ARGS[@]} \
    ${LOGGING_ARGS[@]}

# ============================================================
# Variable substitution guide (base fields same as pretrain_dense.sh.tpl; below are SFT-specific):
#   {{SFT_DATA_PATH}}        → SFT data path (JSON format)
#   {{CHAT_TEMPLATE}}        → Chat template name (e.g. qwen, llama3.1, deepseek, chatml)
#   {{SFT_GLOBAL_BS}}        → SFT global batch size (typically smaller than pretrain, e.g. 128)
#   {{SFT_LR}}               → SFT learning rate (typically lower than pretrain)
#   {{SFT_MIN_LR}}           → SFT minimum learning rate
#   {{SFT_TRAIN_ITERS}}      → SFT iterations (typically 5000)
#   {{SFT_LR_DECAY_ITERS}}   → SFT LR decay iterations
#   {{SFT_SAVE_INTERVAL}}    → SFT save interval (e.g. 500)
#   {{SFT_EVAL_INTERVAL}}    → SFT eval interval (e.g. 100)
#
# Key differences between SFT and Pretrain:
#   - training-phase: sft (instead of pretrain)
#   - split: 100,0,0 (all data for training)
#   - Added SFT_ARGS section (chat-template, etc.)
#   - global-batch-size is typically smaller
#   - train-iters is typically fewer
#   - save-interval is typically more frequent
# ============================================================
