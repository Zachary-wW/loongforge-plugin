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


def test_target_v4_package_is_present():
    pkg = TARGET_OMNI / "loongforge" / "models" / "foundation" / "deepseek_v4"
    for name in (
        "__init__.py",
        "deepseek_v4_config.py",
        "deepseek_v4_layer_spec.py",
        "deepseek_v4_model.py",
        "deepseek_v4_csa.py",
        "deepseek_v4_attention.py",
        "deepseek_v4_dsa_compat.py",
    ):
        assert (pkg / name).is_file(), f"missing {name}"


def test_target_v4_lite_4l_yaml_matches_lite_checkpoint():
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
    chat_template = _read(TARGET_OMNI / "loongforge" / "data" / "chat_template.py")
    assert 'name="deepseek4"' in chat_template

    arguments = _read(TARGET_OMNI / "loongforge" / "train" / "arguments.py")
    assert "--deepseek-v4-sft-packing" in arguments


def test_megatron_does_not_carry_v4_specifics():
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
        "moe_n_hash_layers",
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
    not (SOURCE_OMNI.exists() and SOURCE_MEGATRON.exists()),
    reason="v4_0520 reference tree not present",
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
