#!/usr/bin/env python3
"""
hf_tensor_dump.py -- HF-side tensor capture for Phase 3 loss-diff verification.

Registers PyTorch hooks on a HuggingFace model to save per-module tensors
(forward inputs/outputs, backward gradients, weights) in tensor logging format.
Module names are translated from HF convention to Omni/Megatron-Core convention
using the Phase 2 convert YAML name_map.

Output file naming (tensor logging compatible):
    <prefix>.<mapped_module_name>.<tensor_type>.step<N>.rank<R>.mbs<M>.pt

Usage:
    python hf_tensor_dump.py \
        --hf-ckpt-path /path/to/hf_ckpt \
        --convert-yaml-path /path/to/convert.yaml \
        --save-dir /path/to/hf_tensors/ \
        --stage forward \
        --seq-len 128

    python hf_tensor_dump.py --generate-mock-input --seq-len 128 \
        --mock-input-path /path/to/mock_input.pt
"""
import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import torch
import yaml


# ---------------------------------------------------------------------------
# YAML parsing: build HF -> mcore module name mapping
# ---------------------------------------------------------------------------

def build_module_mapping(convert_yaml_path: str) -> Dict[str, str]:
    """Parse a convert YAML and return a flat HF-module -> mcore-module mapping.

    The mapping is at the *module* level (not weight level).  For per-layer
    entries the layer index is left as a placeholder -- callers expand it via
    ``_map_module_name()``.

    Special keys in the returned dict:
        ``__hf_layer_prefix__``   -- e.g. ``"model.layers"``
        ``__mcore_layer_prefix__`` -- e.g. ``"decoder.layers"``

    Returns:
        dict mapping HF module suffix -> mcore module suffix, plus the two
        special prefix keys.
    """
    with open(convert_yaml_path, "r") as fh:
        cfg = yaml.safe_load(fh)

    name_map = cfg["name_map"]
    hf_map = name_map["huggingface"]
    mc_map = name_map["mcore"]

    hf_transformer = hf_map.get("transformer", "model")
    hf_layer_prefix = hf_map.get("layer_prefix", "layers")
    mc_layer_prefix = mc_map.get("layer_prefix", "decoder.layers")

    full_hf_layer_prefix = f"{hf_transformer}.{hf_layer_prefix}"

    mapping: Dict[str, str] = {
        "__hf_layer_prefix__": full_hf_layer_prefix,
        "__mcore_layer_prefix__": mc_layer_prefix,
    }

    # Canonical keys shared by both hf and mcore sections
    canonical_keys = set(hf_map.keys()) & set(mc_map.keys())
    # Remove structural keys
    canonical_keys -= {"transformer", "layer_prefix"}

    for ckey in sorted(canonical_keys):
        hf_val = hf_map[ckey]
        mc_val = mc_map[ckey]

        # Resolve mcore side -- can be str or dict with "name" key
        if isinstance(mc_val, dict):
            mc_name = mc_val["name"]
        else:
            mc_name = mc_val

        # Resolve HF side -- can be str or list (e.g. QKV split)
        if isinstance(hf_val, list):
            # All split projections map to the same mcore fused module
            for hf_name in hf_val:
                mapping[hf_name] = mc_name
        elif isinstance(hf_val, str):
            # Non-layer modules (word_embeddings, final_layernorm, lm_head)
            # use the raw HF name (which already includes the full path).
            # Per-layer modules use just the suffix within a layer.
            mapping[hf_val] = mc_name
        # else: skip None values

    return mapping


# ---------------------------------------------------------------------------
# Module name translation
# ---------------------------------------------------------------------------

def _map_module_name(
    hf_name: str,
    mapping: Dict[str, str],
    hf_prefix: str,
    mcore_prefix: str,
) -> Optional[str]:
    """Translate a full HF module name to the corresponding mcore name.

    Args:
        hf_name: e.g. ``"model.layers.3.self_attn.o_proj"``
        mapping: output of ``build_module_mapping()``
        hf_prefix: HF layer prefix, e.g. ``"model.layers"``
        mcore_prefix: mcore layer prefix, e.g. ``"decoder.layers"``

    Returns:
        Mapped mcore name (e.g. ``"decoder.layers.3.self_attention.linear_proj"``)
        or None if the module is not in the mapping.
    """
    # Check per-layer pattern: <hf_prefix>.<idx>.<suffix>
    layer_re = re.compile(re.escape(hf_prefix) + r"\.(\d+)\.(.+)")
    m = layer_re.match(hf_name)
    if m:
        layer_idx = m.group(1)
        suffix = m.group(2)
        if suffix in mapping:
            return f"{mcore_prefix}.{layer_idx}.{mapping[suffix]}"
        return None

    # Check non-layer (global) modules
    if hf_name in mapping:
        return mapping[hf_name]

    return None


# ---------------------------------------------------------------------------
# Hook registration
# ---------------------------------------------------------------------------

def _make_save_hook(
    mapped_name: str,
    save_dir: Path,
    tensor_type: str,
    step: int = 0,
    rank: int = 0,
    mbs: int = 0,
    prefix: str = "hf",
):
    """Return a closure that saves a tensor in tensor logging file format.

    File naming: ``<prefix>.<mapped_name>.<tensor_type>.step<N>.rank<R>.mbs<M>.pt``
    Content: ``{"tensor": cpu_tensor}`` via ``torch.save()``.
    """
    def _save(tensor: torch.Tensor):
        fname = f"{prefix}.{mapped_name}.{tensor_type}.step{step}.rank{rank}.mbs{mbs}.pt"
        path = save_dir / fname
        torch.save({"tensor": tensor.detach().cpu()}, path)

    return _save


def _make_weight_save_hook(
    module_name: str,
    mapped_name: str,
    save_dir: Path,
    prefix: str,
    step: int = 0,
    rank: int = 0,
    mbs: int = 0,
):
    """Return a forward hook closure that saves weight parameters of a module.

    The returned hook saves each weight parameter of the module in
    tensor logging file format when the module's forward pass executes.

    Args:
        module_name: original HF module name (for reference).
        mapped_name: translated mcore module name used in file naming.
        save_dir: directory to write .pt files.
        prefix: filename prefix (e.g. ``"hf"``).
        step, rank, mbs: indices for file naming.

    Returns:
        A forward hook callable with signature ``(module, input, output)``.
    """
    def _hook(module, input, output):
        for pname, param in module.named_parameters(recurse=False):
            weight_name = f"{mapped_name}.{pname}" if pname != "weight" else mapped_name
            saver = _make_save_hook(weight_name, save_dir, "weight",
                                    step=step, rank=rank, mbs=mbs, prefix=prefix)
            saver(param.data)
    return _hook


def _make_grad_save_hook(
    module_name: str,
    mapped_name: str,
    save_dir: Path,
    prefix: str,
    step: int = 0,
    rank: int = 0,
    mbs: int = 0,
):
    """Return a backward hook closure that saves ``.grad`` from weight parameters.

    After the backward pass, this hook iterates over the module's direct
    parameters and saves ``param.grad`` (HF convention) for each one.

    Args:
        module_name: original HF module name (for reference).
        mapped_name: translated mcore module name used in file naming.
        save_dir: directory to write .pt files.
        prefix: filename prefix (e.g. ``"hf"``).
        step, rank, mbs: indices for file naming.

    Returns:
        A backward hook callable with signature ``(module, grad_input, grad_output)``.
    """
    def _hook(module, grad_input, grad_output):
        for pname, param in module.named_parameters(recurse=False):
            if param.grad is not None:
                grad_name = f"{mapped_name}.{pname}" if pname != "weight" else mapped_name
                saver = _make_save_hook(grad_name, save_dir, "grad",
                                        step=step, rank=rank, mbs=mbs, prefix=prefix)
                saver(param.grad)
    return _hook


def register_hf_hooks(
    model: "torch.nn.Module",
    mapping: Dict[str, str],
    save_dir: str,
    stage: str = "forward",
    layer_pattern: str = ".*",
    prefix: str = "hf",
    step: int = 0,
    rank: int = 0,
    mbs: int = 0,
) -> List:
    """Register forward/backward hooks on HF model modules.

    For each module whose full name maps successfully via ``_map_module_name()``:
    - ``forward`` stage: saves fwd_x (first input) and fwd_y (first output).
    - ``backward`` stage: saves bwd_dx and bwd_dy.
    - Weights are saved for all matched modules regardless of stage.

    Args:
        model: HuggingFace model instance.
        mapping: output of ``build_module_mapping()``.
        save_dir: directory to write .pt files.
        stage: ``"forward"`` or ``"forward,backward"``.
        layer_pattern: regex to filter module names (applied to mapped name).
        prefix: filename prefix (default ``"hf"``).
        step, rank, mbs: step/rank/micro-batch indices for file naming.

    Returns:
        List of hook handles (call ``.remove()`` to detach).
    """
    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    hf_prefix = mapping["__hf_layer_prefix__"]
    mcore_prefix = mapping["__mcore_layer_prefix__"]

    pattern = re.compile(layer_pattern)
    stages = set(stage.split(","))
    handles = []

    for name, module in model.named_modules():
        mapped = _map_module_name(name, mapping, hf_prefix, mcore_prefix)
        if mapped is None:
            continue
        if not pattern.search(mapped):
            continue

        # Save weights immediately and register weight save hook for forward
        for pname, param in module.named_parameters(recurse=False):
            weight_name = f"{mapped}.{pname}" if pname != "weight" else mapped
            saver = _make_save_hook(weight_name, save_path, "weight",
                                    step=step, rank=rank, mbs=mbs, prefix=prefix)
            saver(param.data)

        weight_hook = _make_weight_save_hook(name, mapped, save_path, prefix,
                                             step=step, rank=rank, mbs=mbs)

        # Forward hooks
        if "forward" in stages:
            save_fwd_x = _make_save_hook(mapped, save_path, "fwd_x",
                                         step=step, rank=rank, mbs=mbs, prefix=prefix)
            save_fwd_y = _make_save_hook(mapped, save_path, "fwd_y",
                                         step=step, rank=rank, mbs=mbs, prefix=prefix)

            def _fwd_hook(mod, inp, out, _sx=save_fwd_x, _sy=save_fwd_y):
                # inp is a tuple; save the first element
                if isinstance(inp, tuple) and len(inp) > 0:
                    t = inp[0]
                    if isinstance(t, torch.Tensor):
                        _sx(t)
                # out can be a tensor or tuple
                if isinstance(out, torch.Tensor):
                    _sy(out)
                elif isinstance(out, tuple) and len(out) > 0:
                    t = out[0]
                    if isinstance(t, torch.Tensor):
                        _sy(t)

            h = module.register_forward_hook(_fwd_hook)
            handles.append(h)

        # Backward hooks
        if "backward" in stages:
            save_bwd_dx = _make_save_hook(mapped, save_path, "bwd_dx",
                                          step=step, rank=rank, mbs=mbs, prefix=prefix)
            save_bwd_dy = _make_save_hook(mapped, save_path, "bwd_dy",
                                          step=step, rank=rank, mbs=mbs, prefix=prefix)

            def _bwd_hook(mod, grad_in, grad_out, _sdx=save_bwd_dx, _sdy=save_bwd_dy):
                if isinstance(grad_in, tuple) and len(grad_in) > 0:
                    t = grad_in[0]
                    if isinstance(t, torch.Tensor):
                        _sdx(t)
                if isinstance(grad_out, tuple) and len(grad_out) > 0:
                    t = grad_out[0]
                    if isinstance(t, torch.Tensor):
                        _sdy(t)

            h = module.register_full_backward_hook(_bwd_hook)
            handles.append(h)

            # Register grad save hook (saves param.grad after backward)
            grad_hook = _make_grad_save_hook(name, mapped, save_path, prefix,
                                             step=step, rank=rank, mbs=mbs)
            h = module.register_full_backward_hook(grad_hook)
            handles.append(h)

    return handles


# ---------------------------------------------------------------------------
# Mock input generation
# ---------------------------------------------------------------------------

_INPUT_START = 100


def generate_mock_input(seq_len: int = 128, save_path: Optional[str] = None) -> dict:
    """Generate a mock input dict compatible with HF and Omni.

    Content:
        input_ids:      torch.arange(100, 100 + seq_len)   (long)
        attention_mask:  torch.ones(seq_len)                (long)
        labels:          torch.arange(100, 100 + seq_len)   (long)

    If *save_path* is given, saves via ``torch.save()``.

    Returns:
        The mock input dict.
    """
    mock = {
        "input_ids": torch.arange(_INPUT_START, _INPUT_START + seq_len, dtype=torch.long),
        "attention_mask": torch.ones(seq_len, dtype=torch.long),
        "labels": torch.arange(_INPUT_START, _INPUT_START + seq_len, dtype=torch.long),
    }
    if save_path is not None:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        torch.save(mock, save_path)
    return mock


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="HF-side tensor capture for Phase 3 loss-diff verification"
    )

    # Sub-modes
    parser.add_argument(
        "--generate-mock-input", action="store_true",
        help="Only generate mock input file and exit."
    )

    # Model / data paths
    parser.add_argument("--hf-ckpt-path", type=str, default=None,
                        help="HF model checkpoint path (local dir with config.json)")
    parser.add_argument("--convert-yaml-path", type=str, default=None,
                        help="Phase 2 convert YAML with name_map section")
    parser.add_argument("--mock-input-path", type=str, default=None,
                        help="Path to mock_input.pt (load or save)")

    # Output
    parser.add_argument("--save-dir", type=str, default="./hf_tensors",
                        help="Directory to save tensor dumps (default: ./hf_tensors)")
    parser.add_argument("--prefix", type=str, default="hf",
                        help="Filename prefix (default: hf)")

    # Execution control
    parser.add_argument("--stage", type=str, default="forward",
                        choices=["forward", "forward,backward"],
                        help="Stages to run: forward or forward,backward")
    parser.add_argument("--layer-pattern", type=str, default=".*",
                        help="Regex to filter mapped module names")
    parser.add_argument("--seq-len", type=int, default=128,
                        help="Sequence length for mock input (default: 128)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default: 42)")

    args = parser.parse_args()

    # --- Mock input generation mode ---
    if args.generate_mock_input:
        out_path = args.mock_input_path or "mock_input.pt"
        generate_mock_input(seq_len=args.seq_len, save_path=out_path)
        print(f"Mock input saved to: {out_path}")
        return

    # --- Tensor dump mode ---
    if args.hf_ckpt_path is None:
        parser.error("--hf-ckpt-path is required for tensor dump mode")
    if args.convert_yaml_path is None:
        parser.error("--convert-yaml-path is required for tensor dump mode")

    try:
        from transformers import AutoConfig, AutoModelForCausalLM
    except ImportError:
        print("ERROR: transformers not installed. pip install transformers", file=sys.stderr)
        sys.exit(1)

    torch.manual_seed(args.seed)

    # 1. Build name mapping
    mapping = build_module_mapping(args.convert_yaml_path)

    # 2. Load model
    config = AutoConfig.from_pretrained(args.hf_ckpt_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.hf_ckpt_path, config=config, trust_remote_code=True
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    if "backward" in args.stage:
        model.train()
    else:
        model.eval()

    # 3. Load or generate mock input
    if args.mock_input_path and Path(args.mock_input_path).exists():
        mock = torch.load(args.mock_input_path, weights_only=True)
    else:
        mock = generate_mock_input(seq_len=args.seq_len)

    input_ids = mock["input_ids"].unsqueeze(0).to(device)
    attention_mask = mock["attention_mask"].unsqueeze(0).to(device)
    labels = mock["labels"].unsqueeze(0).to(device)

    # 4. Register hooks
    handles = register_hf_hooks(
        model, mapping, args.save_dir,
        stage=args.stage,
        layer_pattern=args.layer_pattern,
        prefix=args.prefix,
    )

    # 5. Forward (and optionally backward)
    if "backward" in args.stage:
        output = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        loss = output.loss
        loss.backward()
    else:
        with torch.no_grad():
            output = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        loss = output.loss

    # 6. Cleanup hooks
    for h in handles:
        h.remove()

    print(f"HF_LOSS: {loss.item():.6f}")
    print(f"TENSOR_DUMP_DIR: {args.save_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
