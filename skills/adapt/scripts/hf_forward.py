#!/usr/bin/env python3
"""
scripts/hf_forward.py -- HF random-init forward script (for Phase 1 verification)

Uses the transformers library to run one forward pass with randomly initialized weights and output loss.
Does not load any checkpoint -- only verifies network construction correctness.

Usage:
  python skills/adapt/scripts/hf_forward.py --hf-path <hf_path>
  python skills/adapt/scripts/hf_forward.py --hf-path <hf_path> --seq-len 128 --seed 42

Output (last line):
  HF_LOSS: <float>
"""
import argparse
import sys

import torch


# Fixed input: consistent with the OMNI_PHASE1_VERIFY hook on the Omni side
# input_ids = torch.arange(100, 100 + seq_len), reshaped to (1, seq_len)
_INPUT_START = 100


def build_input_ids(seq_len: int, device: torch.device) -> torch.Tensor:
    """build_input_ids"""
    return torch.arange(_INPUT_START, _INPUT_START + seq_len, dtype=torch.long, device=device).unsqueeze(0)


def run_hf_forward(hf_path: str, seq_len: int = 128, seed: int = 42) -> float:
    """run hf forward"""
    try:
        from transformers import AutoConfig, AutoModelForCausalLM
    except ImportError:
        print("ERROR: transformers is not installed, please pip install transformers", file=sys.stderr)
        sys.exit(1)

    torch.manual_seed(seed)

    config = AutoConfig.from_pretrained(hf_path, trust_remote_code=True)
    # Random initialization (no weight loading)
    model = AutoModelForCausalLM.from_config(config, trust_remote_code=True)
    model.eval()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)

    input_ids = build_input_ids(seq_len, device)
    labels = input_ids.clone()

    with torch.no_grad():
        output = model(input_ids=input_ids, labels=labels)

    loss = output.loss.item()
    return loss


def main():
    """main"""
    parser = argparse.ArgumentParser(description="HF random-init forward (for Phase 1 verification)")
    parser.add_argument("--hf-path", required=True, help="HF model local path (containing config.json)")
    parser.add_argument("--seq-len", type=int, default=128, help="Sequence length (default 128)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default 42)")
    args = parser.parse_args()

    loss = run_hf_forward(args.hf_path, seq_len=args.seq_len, seed=args.seed)
    print(f"HF_LOSS: {loss:.6f}")


if __name__ == "__main__":
    main()
