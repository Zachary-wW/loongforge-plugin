# QRH-002: Runtime Environment Configuration

## Scenario

When running GPU tasks, encountering `ModuleNotFoundError`, `ImportError`, or path-related errors indicates that environment variables are not set correctly. You should reference the environment configuration patterns from existing scripts in the repository.

## Common Symptoms

- `ModuleNotFoundError: No module named 'megatron'`
- `ModuleNotFoundError: No module named 'loongforge'`
- `ModuleNotFoundError: No module named 'dist_checkpoint'`
- `ModuleNotFoundError: No module named 'convert_checkpoint'`
- `ImportError: cannot import name 'xxx' from 'yyy'`
- `FileNotFoundError: [Errno 2] No such file or directory: '/workspace/...'`

## Core Environment Variables

### Required Path Variables

```bash
# Megatron-LM path (patched version)
MEGATRON_PATH=${MEGATRON_PATH:-"/workspace/Loong-Megatron"}

# LoongForge project root directory
export LOONGFORGE_PATH=${LOONGFORGE_PATH:-"/workspace/LoongForge"}
```

> **Note**: The default values for these paths are container-internal paths (`/workspace/`). For local development, you must override them via environment variables with actual paths.

### PYTHONPATH Concatenation Patterns

Different task types require different PYTHONPATH configurations:

| Task Type | PYTHONPATH | Reference Script |
|-----------|-----------|-----------------|
| Training (pretrain/sft) | `$MEGATRON_PATH:$LOONGFORGE_PATH:$PYTHONPATH` | `examples/qwen2.5/pretrain/pretrain_qwen2.5_7b_bridge.sh` |
| Bridge Roundtrip Test | `$MEGATRON_PATH:$LOONGFORGE_PATH:$PYTHONPATH` | `tools/dist_checkpoint/test/qwen3/8b_bridge_roundtrip.sh` |
| Checkpoint Conversion (convert) | `$MEGATRON_PATH:$PYTHONPATH` | `examples/llama3.1/checkpoint_convert/convert_llama3.1_70b_hf_to_mcore.sh` |
| HF Checkpoint Converter Test | `$MEGATRON_PATH:$LOONGFORGE_PATH:$LOONGFORGE_PATH/tools:$PYTHONPATH` | `tools/dist_checkpoint/test/test_hf_checkpoint_converter.sh` |

**Key Distinctions**:
- Training and roundtrip tests require `$LOONGFORGE_PATH` (to load network construction code)
- Offline convert typically only needs `$MEGATRON_PATH` (pure conversion logic)
- `test_hf_checkpoint_converter.py` additionally requires `$LOONGFORGE_PATH/tools` (because it directly imports `from dist_checkpoint...` and `from convert_checkpoint...`)

### Common Template

```bash
MEGATRON_PATH=${MEGATRON_PATH:-"/workspace/Loong-Megatron"}
export LOONGFORGE_PATH=${LOONGFORGE_PATH:-"/workspace/LoongForge"}

PYTHONPATH=$MEGATRON_PATH:$LOONGFORGE_PATH:$PYTHONPATH \
    torchrun --nproc_per_node $GPUS_PER_NODE \
    ...
```

## Resolution Steps

### 1. Identify the Missing Module

Determine which path is missing based on the module name in `ModuleNotFoundError`:

| Missing Module | Required Path |
|---------------|--------------|
| `megatron` / `megatron.core` | `$MEGATRON_PATH` |
| `loongforge` | `$LOONGFORGE_PATH` |
| `dist_checkpoint` | `$LOONGFORGE_PATH/tools` |
| `convert_checkpoint` | `$LOONGFORGE_PATH/tools` |

### 2. Find Reference Scripts

Locate existing scripts for the same task type in the repository as references:

```bash
# Training scripts
ls examples/<candidate_family>/pretrain/
ls examples/<candidate_family>/finetuning/

# Conversion scripts
ls examples/<candidate_family>/checkpoint_convert/

# Roundtrip test scripts
ls tools/dist_checkpoint/test/<candidate_family>/
```

### 3. Compare Environment Configuration

Read the first 20 lines of the reference script (environment variables are typically set at the beginning) and compare with the current script:

Key checks:
- Whether `MEGATRON_PATH` and `LOONGFORGE_PATH` are defined
- Whether `PYTHONPATH` concatenation includes required paths
- Whether `export` is used correctly (`LOONGFORGE_PATH` typically needs export because it is referenced by child processes)

### 4. Other Common Environment Variables

```bash
# PyTorch / NCCL related (common in bridge_roundtrip.sh)
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1    # Allow loading non-weights_only checkpoints
export CUDA_DEVICE_MAX_CONNECTIONS=1          # NCCL performance optimization
export NCCL_DEBUG=WARNING                     # NCCL log level (set to INFO for debugging)

# Memory optimization (common in large model scripts)
export TORCH_NCCL_AVOID_RECORD_STREAMS=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

Repository references:
- `tools/dist_checkpoint/test/qwen3/4b_bridge_roundtrip.sh:5-10`
- `examples/qwen3/pretrain/pretrain_qwen3_480b_a35b.sh` beginning

### 5. Missing Dependency Packages

If the issue is not a path problem but a third-party package that is not installed:

```bash
# GPU environment
pip install -r requirements.txt

# XPU environment
pip install -r requirements_xpu.txt

# Common missing packages
pip install safetensors    # HF checkpoint loading
pip install omegaconf      # YAML config parsing
pip install hydra-core     # Hydra config framework
```

## Decision Flowchart

```
ModuleNotFoundError
  |
  +-- megatron related -> Check MEGATRON_PATH -> Add to PYTHONPATH
  |
  +-- loongforge related -> Check LOONGFORGE_PATH -> Add to PYTHONPATH
  |
  +-- dist_checkpoint / convert_checkpoint -> Add $LOONGFORGE_PATH/tools to PYTHONPATH
  |
  +-- Third-party package -> pip install
  |
  +-- Unsure -> Find a reference script of the same type, compare PYTHONPATH settings
```
