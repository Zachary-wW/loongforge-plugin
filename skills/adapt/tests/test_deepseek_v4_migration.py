# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0
"""CPU-only invariants for the DeepSeek V4 reference-patchset migration.

These tests document what the v4_0520 -> v4_0615 migration is supposed to
land in the target tree. They run without GPUs or LoongForge being importable
and only inspect filesystem layout + textual markers, plus a JSON pass of the
deepseek-v4-migration verifier when both source and target trees are present.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


PLUGIN_SKILL_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = PLUGIN_SKILL_ROOT / "scripts" / "verify_deepseek_v4_migration.py"
KB_YAML = (
    PLUGIN_SKILL_ROOT
    / "knowledge_base"
    / "sources"
    / "llm"
    / "deepseek_v4_flash.yaml"
)

REPO_ROOT = PLUGIN_SKILL_ROOT.parents[2]
TARGET_OMNI = REPO_ROOT / "AIAK-Training-Omni"
TARGET_MEGATRON = REPO_ROOT / "AIAK-Megatron"
SOURCE_OMNI = Path("/ssd3/weizhihao/code/v4_0520/AIAK-Training-Omni")
SOURCE_MEGATRON = Path("/ssd3/weizhihao/code/v4_0520/AIAK-Megatron")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _require_target_omni() -> None:
    if not (TARGET_OMNI / "loongforge").is_dir():
        pytest.skip(f"AIAK-Training-Omni target tree not present at {TARGET_OMNI}")


def _require_target_megatron() -> None:
    if not (TARGET_MEGATRON / "megatron" / "core").is_dir():
        pytest.skip(f"AIAK-Megatron target tree not present at {TARGET_MEGATRON}")


def test_target_v4_package_is_present():
    _require_target_omni()
    pkg = TARGET_OMNI / "loongforge" / "models" / "foundation" / "deepseek_v4"
    for name in (
        "__init__.py",
        "deepseek_v4_config.py",
        "deepseek_v4_layer_spec.py",
        "deepseek_v4_model.py",
        "deepseek_v4_csa.py",
        "deepseek_v4_attention.py",
    ):
        assert (pkg / name).is_file(), f"missing {name}"


def test_target_v4_lite_4l_yaml_matches_lite_checkpoint():
    _require_target_omni()
    yaml_text = _read(
        TARGET_OMNI
        / "configs"
        / "models"
        / "deepseek4"
        / "deepseek_v4_flash_base_lite_4l_mtp1.yaml"
    )
    # These markers mirror the lite checkpoint's config.json. Drift here is the
    # most common cause of silent loss-diff regressions.
    for needle in (
        "_target_: loongforge.models.foundation.deepseek_v4.DeepseekV4Config",
        "model_type: deepseek_v4",
        "num_layers: 4",
        "mtp_num_layers: 1",
        "csa_compress_ratios: [0, 0, 4, 128, 0]",
        "moe_n_hash_layers: 3",
        "experimental_attention_variant: dsv4_hybrid",
        "moe_router_score_function: sqrtsoftplus",
        "head_dim: 512",
        "qk_rope_head_dim: 64",
        "o_groups: 8",
        "o_lora_rank: 1024",
        "swiglu_limit: 10.0",
    ):
        assert needle in yaml_text, f"lite-4L yaml missing marker: {needle!r}"


def test_target_omni_registrations():
    _require_target_omni()
    constants = _read(TARGET_OMNI / "loongforge" / "utils" / "constants.py")
    assert 'DEEPSEEK_V4 = "deepseek_v4"' in constants

    foundation_init = _read(
        TARGET_OMNI / "loongforge" / "models" / "foundation" / "__init__.py"
    )
    assert "from .deepseek_v4 import DeepseekV4Config, DeepseekV4Model" in foundation_init
    assert "AutoModel.register(DeepseekV4Config" in foundation_init

    config_map = _read(TARGET_OMNI / "loongforge" / "utils" / "config_map.py")
    for entry in (
        '"deepseek-v4-flash"',
        '"deepseek-v4-flash-base-sliced"',
        '"deepseek-v4-flash-base-lite-4l-mtp1"',
        '"configs/models/deepseek4"',
    ):
        assert entry in config_map, f"config_map missing entry {entry!r}"


def test_target_omni_data_and_train_hooks():
    _require_target_omni()
    chat_template = _read(TARGET_OMNI / "loongforge" / "data" / "chat_template.py")
    assert 'name="deepseek4"' in chat_template

    arguments = _read(TARGET_OMNI / "loongforge" / "train" / "arguments.py")
    assert "--deepseek-v4-sft-packing" in arguments


def test_target_base_gpt_model_threads_dsv4_runtime_context():
    _require_target_omni()
    text = _read(
        TARGET_OMNI
        / "loongforge"
        / "models"
        / "foundation"
        / "base"
        / "base_gpt_model.py"
    )
    for needle in (
        "moe_n_hash_layers",
        "decoder_extra_kwargs['input_ids']",
        "isinstance(decoder_output, tuple)",
        "mhc_multistream",
        "mhc_multistream=mhc_multistream",
        "self.position_embedding_type == 'yarn' and not self.config.multi_latent_attention",
    ):
        assert needle in text, f"BaseGPTModel missing DS V4 runtime marker {needle!r}"


def test_target_dsv4_checkpoint_converter_invariants():
    _require_target_omni()
    convert_yaml = _read(
        TARGET_OMNI
        / "configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml"
    )
    assert "weight_scale_key: scale" in convert_yaml

    hf_script = _read(
        TARGET_OMNI
        / "examples/deepseek_v4/checkpoint_convert/convert_deepseek_v4_hf_to_mcore_fp8.sh"
    )
    for needle in (
        "MODEL_CONFIG_FILE",
        "CONVERT_FILE",
        "configs/models/deepseek4/deepseek_v4_flash_base.yaml",
        "--pretrain_as_fp8",
        "--force_pow_2_scales",
    ):
        assert needle in hf_script, f"DS V4 HF-to-MCore script missing {needle!r}"

    hf_ckpt = _read(
        TARGET_OMNI
        / "tools/convert_checkpoint/huggingface/huggingface_checkpoint.py"
    )
    for needle in (
        "weight_scale_key",
        "fp8_weight_roots",
        "mtp.layers.",
        "hc_attn_alpha_pre",
        "hc_ffn_alpha_pre",
        "seen_storages",
        "untyped_storage",
    ):
        assert needle in hf_ckpt, f"HF checkpoint converter missing DS V4 marker {needle!r}"

    mcore_moe = _read(
        TARGET_OMNI / "tools/convert_checkpoint/mcore/mcore_moe.py"
    )
    assert "if mt not in m_dict:" in mcore_moe
    assert "if t_name not in m_dict[mt]:" in mcore_moe

    utils = _read(TARGET_OMNI / "tools/convert_checkpoint/utils/utils.py")
    assert "weight_scale_inv.transpose(0, 1)" in utils
    assert "scale_rows" in utils
    assert "scale_cols" in utils


def test_megatron_does_not_carry_v4_specifics():
    _require_target_megatron()
    forbidden_files = (
        TARGET_MEGATRON
        / "megatron/core/transformer/experimental_attention_variant/csa.py",
        TARGET_MEGATRON
        / "megatron/core/transformer/experimental_attention_variant/deepseek_v4_hybrid_attention.py",
    )
    for path in forbidden_files:
        assert not path.exists(), f"V4-specific Megatron file leaked: {path}"

    forbidden_strings = (
        "dsv4_hybrid",
        "DeepseekV4",
        "deepseek_v4",
        "csa_compress_ratios",
        "o_lora_rank",
    )
    mc_root = TARGET_MEGATRON / "megatron"
    if not mc_root.is_dir():
        pytest.skip("AIAK-Megatron tree not present in this checkout")
    for path in mc_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in forbidden_strings:
            assert needle not in text, (
                f"Megatron {path} carries V4-specific marker {needle!r}"
            )


def test_megatron_only_extends_with_sqrtsoftplus():
    _require_target_megatron()
    moe_utils = _read(
        TARGET_MEGATRON / "megatron/core/transformer/moe/moe_utils.py"
    )
    assert "sqrtsoftplus" in moe_utils

    args = _read(TARGET_MEGATRON / "megatron/training/arguments.py")
    assert "sqrtsoftplus" in args


def test_kb_records_migration_contract():
    text = _read(KB_YAML)
    for needle in (
        "migration:",
        "reference_root: /ssd3/weizhihao/code/v4_0520",
        "lossdiff_bundle:",
        "validation:",
        "contract: deepseek-v4-migration",
        "verifier_script: skills/adapt/scripts/verify_deepseek_v4_migration.py",
        "forbidden_megatron_files",
        "forbidden_megatron_strings",
        "allowed_megatron_diff",
    ):
        assert needle in text, f"KB yaml missing migration marker {needle!r}"


@pytest.mark.skipif(
    not (
        SOURCE_OMNI.exists()
        and SOURCE_MEGATRON.exists()
        and (TARGET_OMNI / "loongforge").is_dir()
        and (TARGET_MEGATRON / "megatron" / "core").is_dir()
    ),
    reason="v4_0520 reference tree or target AIAK trees not present",
)
def test_deepseek_v4_migration_verifier_passes():
    proc = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--scope",
            "all",
            "--omni-root",
            str(TARGET_OMNI),
            "--megatron-root",
            str(TARGET_MEGATRON),
            "--source-omni-root",
            str(SOURCE_OMNI),
            "--source-megatron-root",
            str(SOURCE_MEGATRON),
        ],
        capture_output=True,
        text=True,
    )
    # Expected: the verifier exits 0 and reports passed.
    assert proc.returncode == 0, (
        "verify_deepseek_v4_migration.py blocked:\n" + proc.stdout + proc.stderr
    )
    report = json.loads(proc.stdout)
    assert report["status"] == "passed", report
    validator = report["validator"]
    assert validator["name"] == "deepseek-v4-migration"
    assert validator["status"] == "passed"
    assert validator["metrics"]["error_count"] == 0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_verifier_matches_debug0616_contract_without_dsa_compat_and_with_generic_hash_help(tmp_path):
    omni = tmp_path / "AIAK-Training-Omni"
    megatron = tmp_path / "AIAK-Megatron"

    v4_pkg = omni / "loongforge/models/foundation/deepseek_v4"
    for name in (
        "__init__.py",
        "deepseek_v4_config.py",
        "deepseek_v4_layer_spec.py",
        "deepseek_v4_model.py",
        "deepseek_v4_csa.py",
        "deepseek_v4_attention.py",
    ):
        _write(v4_pkg / name, "\n".join([
            "class DeepseekV4Config: pass",
            "class DeepseekV4Model: pass",
            "BaseModelMLAConfig",
            "LanguageModelFamilies.DEEPSEEK_V4",
            "moe_n_hash_layers",
            "csa_compress_ratios",
            "o_groups",
            "swiglu_limit",
            "get_deepseek_v4_decoder_block_and_mtp_spec",
            "DSv4HybridSelfAttention",
            "CompressedSparseAttention",
            "from loongforge.models.foundation.deepseek_v4.deepseek_v4_csa",
            "config_class = DeepseekV4Config",
            "register_load_state_dict_post_hook",
            "_extra_state",
        ]))
    _write(
        omni / "configs/models/deepseek4/deepseek_v4_flash_base_lite_4l_mtp1.yaml",
        "\n".join([
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
        ]),
    )
    _write(
        omni / "configs/models/deepseek4/deepseek_v4_flash_base.yaml",
        "\n".join([
            "_target_: loongforge.models.foundation.deepseek_v4.DeepseekV4Config",
            "model_type: deepseek_v4",
            "experimental_attention_variant: dsv4_hybrid",
            "csa_compress_ratios",
            "moe_n_hash_layers",
            "moe_router_score_function: sqrtsoftplus",
            "qk_layernorm: true",
            "mtp_num_layers",
        ]),
    )
    _write(omni / "configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml", "tid2eid\ncompressor\nindexer\nmtp\nweight_scale_key: scale\n")
    _write(omni / "examples/deepseek_v4/sft_v4.sh", "#!/usr/bin/env bash\n")
    _write(
        omni / "examples/deepseek_v4/checkpoint_convert/convert_deepseek_v4_hf_to_mcore_fp8.sh",
        "MODEL_CONFIG_FILE=$LOONGFORGE_PATH/configs/models/deepseek4/deepseek_v4_flash_base.yaml\n"
        "CONVERT_FILE=$LOONGFORGE_PATH/configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml\n"
        "--pretrain_as_fp8 --force_pow_2_scales\n",
    )
    _write(
        omni / "loongforge/models/foundation/base/base_gpt_model.py",
        "moe_n_hash_layers\n"
        "decoder_extra_kwargs['input_ids']\n"
        "isinstance(decoder_output, tuple)\n"
        "mhc_multistream\n"
        "mhc_multistream=mhc_multistream\n"
        "self.position_embedding_type == 'yarn' and not self.config.multi_latent_attention\n",
    )
    _write(omni / "loongforge/utils/constants.py", 'DEEPSEEK_V4 = "deepseek_v4"\n')
    _write(
        omni / "loongforge/models/foundation/__init__.py",
        "from .deepseek_v4 import DeepseekV4Config, DeepseekV4Model\nAutoModel.register(DeepseekV4Config, DeepseekV4Model)\n",
    )
    _write(
        omni / "loongforge/utils/config_map.py",
        '"deepseek-v4-flash"\n"deepseek-v4-flash-base-sliced"\n"deepseek-v4-flash-base-lite-4l-mtp1"\n"configs/models/deepseek4"\n',
    )
    _write(omni / "loongforge/data/chat_template.py", 'name="deepseek4"\n')
    _write(omni / "loongforge/train/arguments.py", '"--deepseek-v4-sft-packing"\n')

    _write(
        omni / "tools/convert_checkpoint/huggingface/huggingface_checkpoint.py",
        "weight_scale_key\nfp8_weight_roots\nmtp.layers.\n"
        "hc_attn_alpha_pre\nhc_ffn_alpha_pre\nseen_storages\nuntyped_storage\n",
    )
    _write(
        omni / "tools/convert_checkpoint/mcore/mcore_moe.py",
        "if mt not in m_dict:\n    continue\nif t_name not in m_dict[mt]:\n    continue\n",
    )
    _write(
        omni / "tools/convert_checkpoint/utils/utils.py",
        "scale_rows\nscale_cols\nweight_scale_inv.transpose(0, 1)\n",
    )

    _write(megatron / "megatron/core/transformer/moe/moe_utils.py", "sqrtsoftplus\n")
    _write(
        megatron / "megatron/training/arguments.py",
        "sqrtsoftplus\nLayers with layer_number <= moe_n_hash_layers use a pre-computed tid2eid\n",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(VERIFY_SCRIPT),
            "--scope",
            "all",
            "--omni-root",
            str(omni),
            "--megatron-root",
            str(megatron),
        ],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["status"] == "passed", report
