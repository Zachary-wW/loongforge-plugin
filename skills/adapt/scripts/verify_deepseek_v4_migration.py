#!/usr/bin/env python3
"""Static verifier for DeepSeek-V4 source-to-target migration.

This verifier intentionally does not import LoongForge or Megatron. It checks
filesystem layout and source-code markers required for the approved DeepSeek-V4
migration from /ssd3/weizhihao/code/v4_0520 into a v4_0615-style target tree.

Run as:

    python skills/adapt/scripts/verify_deepseek_v4_migration.py \
        --scope all \
        --omni-root /ssd3/weizhihao/code/v4_0615/AIAK-Training-Omni \
        --megatron-root /ssd3/weizhihao/code/v4_0615/AIAK-Megatron \
        --source-omni-root /ssd3/weizhihao/code/v4_0520/AIAK-Training-Omni \
        --source-megatron-root /ssd3/weizhihao/code/v4_0520/AIAK-Megatron \
        --report-json <run_dir>/phases/phase3/deepseek_v4_migration_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List


VALIDATOR_NAME = "deepseek-v4-migration"
BLOCK_EXIT_CODE = 2

FORBIDDEN_MEGATRON_FILES = (
    "megatron/core/transformer/experimental_attention_variant/csa.py",
    "megatron/core/transformer/experimental_attention_variant/deepseek_v4_hybrid_attention.py",
)
FORBIDDEN_MEGATRON_STRINGS = (
    "dsv4_hybrid",
    "DeepseekV4",
    "deepseek_v4",
    "csa_compress_ratios",
    "o_lora_rank",
)


class CheckState:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.checked_files: List[str] = []
        self._seen_errors: set = set()

    def error(self, message: str) -> None:
        if message not in self._seen_errors:
            self.errors.append(message)
            self._seen_errors.add(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def checked(self, path: Path) -> None:
        self.checked_files.append(str(path))


def _normalize_omni_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    if (root / "loongforge").is_dir():
        return root
    if root.name == "loongforge":
        return root.parent
    return root


def _normalize_megatron_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    if (root / "megatron" / "core").is_dir():
        return root
    if root.name == "megatron" and (root / "core").is_dir():
        return root.parent
    return root


def _read(path: Path, state: CheckState) -> str | None:
    state.checked(path)
    if not path.is_file():
        state.error(f"Missing file: {path}")
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _require_file(root: Path, relpath: str, state: CheckState) -> Path:
    path = root / relpath
    state.checked(path)
    if not path.is_file():
        state.error(f"Missing file: {path}")
    return path


def _require_contains(path: Path, needles: Iterable[str], state: CheckState, label: str | None = None) -> None:
    text = _read(path, state)
    if text is None:
        return
    for needle in needles:
        if needle not in text:
            prefix = f"{label}: " if label else ""
            state.error(f"{prefix}{path} missing required marker: {needle!r}")


def verify_source_omni(root: Path, state: CheckState) -> None:
    """Confirm the source tree carries the expected v4_0520 Omni payload."""
    for relpath in [
        "loongforge/models/foundation/deepseek_v4/__init__.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_config.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_layer_spec.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_model.py",
        "configs/models/deepseek4/deepseek_v4_flash_base.yaml",
        "configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml",
    ]:
        _require_file(root, relpath, state)


def verify_source_megatron(root: Path, state: CheckState) -> None:
    """Confirm the source tree exposes the V4-specific Megatron files used by 0520."""
    for relpath in [
        "megatron/core/transformer/experimental_attention_variant/csa.py",
        "megatron/core/transformer/experimental_attention_variant/deepseek_v4_hybrid_attention.py",
    ]:
        _require_file(root, relpath, state)


def verify_omni_target(root: Path, state: CheckState) -> None:
    """Verify the target LoongForge tree contains the migrated DeepSeek-V4 package."""
    for relpath in [
        "loongforge/models/foundation/deepseek_v4/__init__.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_config.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_layer_spec.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_model.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_csa.py",
        "loongforge/models/foundation/deepseek_v4/deepseek_v4_attention.py",
        "configs/models/deepseek4/deepseek_v4_flash_base.yaml",
        "configs/models/deepseek4/deepseek_v4_flash_base_lite_4l_mtp1.yaml",
        "configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml",
        "examples/deepseek_v4/sft_v4.sh",
    ]:
        _require_file(root, relpath, state)

    # Lite-4L config must mirror the lite checkpoint at
    # /ssd3/weizhihao/ckpt/DeepSeek-V4-Flash-Base-lite-lay4L-mtp1/config.json
    _require_contains(
        root / "configs/models/deepseek4/deepseek_v4_flash_base_lite_4l_mtp1.yaml",
        [
            "_target_: loongforge.models.foundation.deepseek_v4.DeepseekV4Config",
            "model_type: deepseek_v4",
            "num_layers: 4",
            "mtp_num_layers: 1",
            "csa_compress_ratios: [0, 0, 4, 128, 0]",
            "moe_n_hash_layers: 3",
            "experimental_attention_variant: dsv4_hybrid",
            "moe_router_score_function: sqrtsoftplus",
            "qk_layernorm: true",
            "head_dim: 512",
            "qk_rope_head_dim: 64",
            "o_groups: 8",
            "o_lora_rank: 1024",
            "swiglu_limit: 10.0",
        ],
        state,
        "DeepSeek V4 lite-4L config",
    )

    _require_contains(
        root / "loongforge/utils/constants.py",
        ['DEEPSEEK_V4', '"deepseek_v4"'],
        state,
        "model family constant",
    )
    _require_contains(
        root / "loongforge/models/foundation/__init__.py",
        ["DeepseekV4Config", "DeepseekV4Model", "AutoModel.register(DeepseekV4Config"],
        state,
        "foundation registration",
    )
    _require_contains(
        root / "loongforge/utils/config_map.py",
        [
            '"deepseek-v4-flash"',
            '"deepseek-v4-flash-base-sliced"',
            '"deepseek-v4-flash-base-lite-4l-mtp1"',
            '"configs/models/deepseek4"',
        ],
        state,
        "config map",
    )
    _require_contains(
        root / "loongforge/models/foundation/deepseek_v4/deepseek_v4_config.py",
        [
            "class DeepseekV4Config",
            "BaseModelMLAConfig",
            "LanguageModelFamilies.DEEPSEEK_V4",
            "moe_n_hash_layers",
            "csa_compress_ratios",
            "o_groups",
            "swiglu_limit",
        ],
        state,
        "DeepSeek V4 config",
    )
    _require_contains(
        root / "loongforge/models/foundation/deepseek_v4/deepseek_v4_layer_spec.py",
        [
            "get_deepseek_v4_decoder_block_and_mtp_spec",
            "DSv4HybridSelfAttention",
            "CompressedSparseAttention",
            "from loongforge.models.foundation.deepseek_v4.deepseek_v4_csa",
        ],
        state,
        "DeepSeek V4 layer spec",
    )
    _require_contains(
        root / "loongforge/models/foundation/deepseek_v4/deepseek_v4_model.py",
        [
            "class DeepseekV4Model",
            "config_class = DeepseekV4Config",
            "register_load_state_dict_post_hook",
            "_extra_state",
        ],
        state,
        "DeepSeek V4 model",
    )
    _require_contains(
        root / "loongforge/models/foundation/base/base_gpt_model.py",
        [
            "moe_n_hash_layers",
            "decoder_extra_kwargs['input_ids']",
            "isinstance(decoder_output, tuple)",
            "mhc_multistream",
            "mhc_multistream=mhc_multistream",
            "self.position_embedding_type == 'yarn' and not self.config.multi_latent_attention",
        ],
        state,
        "DeepSeek V4 BaseGPTModel runtime contract",
    )
    _require_contains(
        root / "loongforge/data/chat_template.py",
        ['name="deepseek4"'],
        state,
        "chat template",
    )
    _require_contains(
        root / "loongforge/train/arguments.py",
        ['"--deepseek-v4-sft-packing"'],
        state,
        "deepseek-v4 SFT packing CLI",
    )
    _require_contains(
        root / "configs/models/deepseek4/deepseek_v4_flash_base.yaml",
        [
            "_target_: loongforge.models.foundation.deepseek_v4.DeepseekV4Config",
            "model_type: deepseek_v4",
            "experimental_attention_variant: dsv4_hybrid",
            "csa_compress_ratios",
            "moe_n_hash_layers",
            "moe_router_score_function: sqrtsoftplus",
            "qk_layernorm: true",
            "mtp_num_layers",
        ],
        state,
        "DeepSeek V4 model YAML",
    )
    _require_contains(
        root / "configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml",
        [
            "tid2eid",
            "compressor",
            "indexer",
            "mtp",
            "weight_scale_key: scale",
        ],
        state,
        "DeepSeek V4 conversion YAML",
    )
    _require_contains(
        root / "examples/deepseek_v4/checkpoint_convert/convert_deepseek_v4_hf_to_mcore_fp8.sh",
        [
            "MODEL_CONFIG_FILE",
            "CONVERT_FILE",
            "configs/models/deepseek4/deepseek_v4_flash_base.yaml",
            "--pretrain_as_fp8",
            "--force_pow_2_scales",
        ],
        state,
        "DeepSeek V4 HF-to-MCore conversion script",
    )
    _require_contains(
        root / "tools/convert_checkpoint/huggingface/huggingface_checkpoint.py",
        [
            "weight_scale_key",
            "fp8_weight_roots",
            "mtp.layers.",
            "hc_attn_alpha_pre",
            "hc_ffn_alpha_pre",
            "seen_storages",
            "untyped_storage",
        ],
        state,
        "DeepSeek V4 native HF checkpoint contract",
    )
    _require_contains(
        root / "tools/convert_checkpoint/mcore/mcore_moe.py",
        [
            "if mt not in m_dict:",
            "if t_name not in m_dict[mt]:",
        ],
        state,
        "DeepSeek V4 MCore MoE expert shard guard",
    )
    _require_contains(
        root / "tools/convert_checkpoint/utils/utils.py",
        [
            "weight_scale_inv.transpose(0, 1)",
            "scale_rows",
            "scale_cols",
        ],
        state,
        "DeepSeek V4 FP8 scale layout compatibility",
    )


def verify_megatron_target(root: Path, state: CheckState) -> None:
    """Megatron must NOT carry V4-specific files or strings."""
    for relpath in FORBIDDEN_MEGATRON_FILES:
        path = root / relpath
        state.checked(path)
        if path.is_file():
            state.error(f"Forbidden Megatron file present: {path}")

    for relpath in [
        "megatron/core/transformer/moe/moe_utils.py",
        "megatron/training/arguments.py",
    ]:
        text = _read(root / relpath, state)
        if text is None:
            continue
        if "sqrtsoftplus" not in text:
            state.error(
                f"{root / relpath} missing 'sqrtsoftplus' (required generic interface for DeepSeek-V4)"
            )

    # Forbidden V4 strings anywhere under megatron/
    mc_root = root / "megatron"
    if mc_root.is_dir():
        for path in mc_root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for needle in FORBIDDEN_MEGATRON_STRINGS:
                if needle in text:
                    state.error(
                        f"Forbidden Megatron marker {needle!r} found in {path} "
                        f"(DeepSeek-V4 specific logic must live in LoongForge)"
                    )


def build_report(state: CheckState, scope: str, report_json: str | None) -> dict:
    status = "passed" if not state.errors else "failed"
    artifacts = [report_json] if report_json else []
    return {
        "status": status,
        "summary": (
            f"DeepSeek V4 migration verifier {status}: "
            f"{len(state.errors)} error(s), {len(state.warnings)} warning(s), "
            f"{len(state.checked_files)} file check(s)"
        ),
        "scope": scope,
        "errors": state.errors,
        "warnings": state.warnings,
        "checked_files": state.checked_files,
        "validator": {
            "name": VALIDATOR_NAME,
            "status": status,
            "attempt": 1,
            "failure_gate": None if status == "passed" else "static_migration_invariants",
            "metrics": {
                "error_count": len(state.errors),
                "warning_count": len(state.warnings),
                "checked_file_count": len(state.checked_files),
            },
            "commands": [],
            "logs": [],
            "artifacts": artifacts,
            "diagnosis": (
                None if status == "passed"
                else "Target tree is missing required DeepSeek-V4 migration files, source markers, or contains forbidden Megatron-side V4 logic."
            ),
            "fallback_phase": None,
        },
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify DeepSeek-V4 migration invariants")
    parser.add_argument("--scope", choices=["omni", "megatron", "all"], default="all")
    parser.add_argument("--omni-root", default=None, help="Target AIAK-Training-Omni root")
    parser.add_argument("--megatron-root", default=None, help="Target AIAK-Megatron root")
    parser.add_argument("--source-omni-root", default=None, help="Optional source AIAK-Training-Omni root")
    parser.add_argument("--source-megatron-root", default=None, help="Optional source AIAK-Megatron root")
    parser.add_argument("--report-json", default=None, help="Optional path to write JSON report")
    args = parser.parse_args(argv)

    if args.scope in {"omni", "all"} and not args.omni_root:
        parser.error("--omni-root is required for scope omni/all")
    if args.scope in {"megatron", "all"} and not args.megatron_root:
        parser.error("--megatron-root is required for scope megatron/all")

    state = CheckState()

    if args.source_omni_root:
        verify_source_omni(_normalize_omni_root(args.source_omni_root), state)
    if args.source_megatron_root:
        verify_source_megatron(_normalize_megatron_root(args.source_megatron_root), state)

    if args.scope in {"omni", "all"}:
        verify_omni_target(_normalize_omni_root(args.omni_root), state)
    if args.scope in {"megatron", "all"}:
        verify_megatron_target(_normalize_megatron_root(args.megatron_root), state)

    report = build_report(state, args.scope, args.report_json)

    if args.report_json:
        report_path = Path(args.report_json).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "passed" else BLOCK_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
