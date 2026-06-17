# QRH-001: GPU Resource Dynamic Adjustment

## Scenario

When running GPU tasks (bridge_roundtrip, convert, training) and encountering insufficient resources or device failures, you need to dynamically adjust the GPU count and parallel strategy.

## Common Symptoms

- `CUDA out of memory`
- `NCCL timeout` / `NCCL error: unhandled system error`
- `RuntimeError: CUDA error: device-side assert triggered`
- A specific GPU has abnormally high temperature / ECC errors / is occupied by another process
- `torch.cuda.device_count()` returns a value different from expected

## Resolution Steps

### 1. Diagnose Available GPUs

```bash
# View GPU status (memory usage, processes, temperature, ECC errors)
nvidia-smi

# Check available device count
python -c "import torch; print(f'Available: {torch.cuda.device_count()} GPUs')"

# Check which GPUs are occupied
nvidia-smi --query-compute-apps=pid,gpu_uuid,used_memory --format=csv
```

### 2. Specify Available GPUs (Skip Problematic GPUs)

Control visible devices via `CUDA_VISIBLE_DEVICES`, **must be set before torchrun**:

```bash
# Use only GPUs 0,1,2,3 (skip 4-7)
export CUDA_VISIBLE_DEVICES=0,1,2,3

# Skip GPU 2 (failed GPU)
export CUDA_VISIBLE_DEVICES=0,1,3,4,5,6,7

# Single GPU debugging
export CUDA_VISIBLE_DEVICES=0
```

> **Note**: After setting `CUDA_VISIBLE_DEVICES`, device indices visible within the program are renumbered starting from 0.
> For example, with `CUDA_VISIBLE_DEVICES=2,3`, `cuda:0` in the program actually corresponds to physical GPU 2.

### 3. Adjust GPUS_PER_NODE and nproc_per_node

`GPUS_PER_NODE` and `--nproc_per_node` **must equal the actual number of visible GPUs**:

```bash
# Method A: Manual specification
export CUDA_VISIBLE_DEVICES=0,1,2,3
GPUS_PER_NODE=4

# Method B: Auto-calculate from CUDA_VISIBLE_DEVICES (recommended)
GPUS_PER_NODE=$(echo "$CUDA_VISIBLE_DEVICES" | awk -F, '{print NF}')
```

Repository references:
- Scripts under `examples_xpu/` use Method B (e.g., `examples_xpu/internvl3.5/finetuning/sft_internvl3_5_8b.sh:38-39`)
- Scripts under `examples/` mostly use Method A (e.g., `examples/qwen2.5/pretrain/pretrain_qwen2.5_7b_bridge.sh:18`)

### 4. Adjust Parallel Strategy (TP/PP/EP)

The parallel strategy must be compatible with the available GPU count. Core constraints:

```
GPUS_PER_NODE >= TP_SIZE * PP_SIZE  (non-MoE)
GPUS_PER_NODE >= TP_SIZE * PP_SIZE * EP_SIZE / EP_per_node  (MoE)
```

**Degradation Strategy Priority** (from least to greatest impact):

| Priority | Adjustment Method | Applicable Scenario | Side Effect |
|----------|------------------|--------------------|-------------|
| 1 | Reduce PP_SIZE | Preferred when GPU count is insufficient | Requires more memory/GPUs |
| 2 | Reduce TP_SIZE | Still insufficient after PP=1 | Requires more memory/GPUs |
| 3 | Reduce EP_SIZE | MoE models | Each GPU hosts more experts |
| 4 | Reduce micro-batch-size | Insufficient memory | Training speed decreases |
| 5 | Reduce to TP=1, PP=1 | Last resort (small models/roundtrip test) | Single GPU must fit the model |

**For bridge_roundtrip.sh (weight verification scenario)**: Prioritize reducing to minimum parallelism (TP=1 PP=1), since only conversion correctness is needed, not training performance.

Example — Degraded from 8 GPUs to 4 GPUs:

```bash
# Original config (8 GPUs)
export CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
GPUS_PER_NODE=8
--tensor-model-parallel-size 4
--pipeline-model-parallel-size 2

# Degraded config (4 GPUs)
export CUDA_VISIBLE_DEVICES=0,1,2,3
GPUS_PER_NODE=4
--tensor-model-parallel-size 2
--pipeline-model-parallel-size 2
# or
--tensor-model-parallel-size 4
--pipeline-model-parallel-size 1
```

### 5. VLM Special Considerations

VLM has an independent encoder TP configuration:

```bash
--tensor-model-parallel-size 4          # LLM backbone TP
--encoder-tensor-model-parallel-size 2   # Vision encoder TP (can be adjusted independently)
```

The encoder TP can typically be smaller than the LLM TP (the vision encoder has fewer parameters). When degrading, prioritize reducing the encoder TP.

Repository references:
- `tools/dist_checkpoint/test/internvl2.5/8b_bridge_roundtrip.sh:70-73`
- `tools/dist_checkpoint/test/test_hf_checkpoint_converter.sh:47-52` (qwen2.5_vl with TP=4 + ENCODER_TP=2 configuration)

### 6. Verify Adjusted Configuration

After adjustment, perform a simple verification first:

```bash
# Confirm GPU visibility
CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES python -c \
  "import torch; print(f'Visible GPUs: {torch.cuda.device_count()}')"

# Confirm NCCL communication works (multi-GPU)
CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES torchrun --nproc_per_node=$GPUS_PER_NODE \
  -c "import torch.distributed as dist; dist.init_process_group('nccl'); print(f'rank {dist.get_rank()} ok')"
```

## Decision Flowchart

```
GPU task failed
  |
  +-- OOM -> Reduce micro-batch-size -> Reduce TP/PP -> human_needed
  |
  +-- GPU failure/occupied -> nvidia-smi to locate -> CUDA_VISIBLE_DEVICES to exclude -> Adjust GPUS_PER_NODE + TP/PP
  |
  +-- NCCL timeout -> Check GPU reachability -> Exclude failed GPUs -> Retry with fewer GPUs
  |
  +-- device_count mismatch -> Check CUDA_VISIBLE_DEVICES setting -> Ensure nproc_per_node is consistent
```
