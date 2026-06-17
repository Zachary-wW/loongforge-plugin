"""State helpers for loongforge-issue-loop."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


STATE_REL_DIR = Path(".loongforge") / "issue-loop"
DEFAULT_REPO = "Zachary-wW/loongforge-plugin"
DEFAULT_TARGET = "ds_v4"
DEFAULT_INPUT_MEGATRON_PATH = "~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Megatron"
DEFAULT_INPUT_MEGATRON_COMMIT = "12713af0"
DEFAULT_INPUT_OMNI_PATH = "~/workspace/agent_skills/tmp/baidu/hac-aiacc/AIAK-Training-Omni"
DEFAULT_INPUT_OMNI_COMMIT = "04500dd5"
DEFAULT_GROUNDTRUTH_MEGATRON_PATH = "~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Megatron"
DEFAULT_GROUNDTRUTH_MEGATRON_COMMIT = "e5b77017"
DEFAULT_GROUNDTRUTH_OMNI_PATH = "~/workspace/debug/0616/baidu/hac-aiacc/AIAK-Training-Omni"
DEFAULT_GROUNDTRUTH_OMNI_COMMIT = "3a16d140"
DEFAULT_HF_CHECKPOINT_AND_TOKENIZER_URL = "https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base"
DEFAULT_REFERENCE_CODE_URLS = [
    "https://github.com/huggingface/transformers/tree/main/src/transformers/models/deepseek_v4",
    "https://github.com/NVIDIA/Megatron-LM/issues/4468",
]
DEFAULT_LARGE_ARTIFACT_POLICY = (
    "Do not download checkpoint weights or other large artifacts; "
    "use metadata/source references only."
)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, yaml.dump(data, sort_keys=False, allow_unicode=True))


def load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected YAML mapping at {path}")
    return loaded


def default_state(repo: str = DEFAULT_REPO) -> dict[str, Any]:
    return {
        "repo": repo,
        "mode": "local_execution_github_issues",
        "target_case": DEFAULT_TARGET,
        "baseline": {
            "description": "Groundtruth code that generated artifacts should match structurally.",
            "megatron": {
                "path": DEFAULT_GROUNDTRUTH_MEGATRON_PATH,
                "commit": DEFAULT_GROUNDTRUTH_MEGATRON_COMMIT,
            },
            "omni": {
                "path": DEFAULT_GROUNDTRUTH_OMNI_PATH,
                "commit": DEFAULT_GROUNDTRUTH_OMNI_COMMIT,
            },
        },
        "inputs": {
            "base_code": {
                "description": "Original unadapted Megatron/Omni code used as the adaptation target input.",
                "megatron": {
                    "path": DEFAULT_INPUT_MEGATRON_PATH,
                    "commit": DEFAULT_INPUT_MEGATRON_COMMIT,
                },
                "omni": {
                    "path": DEFAULT_INPUT_OMNI_PATH,
                    "commit": DEFAULT_INPUT_OMNI_COMMIT,
                },
            },
            "hf_checkpoint_and_tokenizer_url": DEFAULT_HF_CHECKPOINT_AND_TOKENIZER_URL,
            "reference_code_urls": list(DEFAULT_REFERENCE_CODE_URLS),
            "large_artifact_policy": DEFAULT_LARGE_ARTIFACT_POLICY,
        },
        "scope": {
            "phases_enabled": [0, 1, 2],
            "phases_deferred": {
                3: "Mac no GPU; loss-diff validation deferred",
                4: "Mac no GPU; runtime feature matrix validation deferred",
            },
        },
        "active_phase": 0,
        "active_issue": None,
        "active_pr": None,
        "phase_iterations": {"0": 0, "1": 0, "2": 0},
        "limits": {
            "max_iterations_per_issue": 5,
            "max_iterations_per_phase": 10,
        },
        "merge_policy": "auto_after_review_and_verification",
    }


def default_goal_contract() -> dict[str, Any]:
    return {
        "phase0": {
            "version": 1,
            "goal": "Extract enough DS V4 facts for Phase 1 code generation.",
            "acceptance": [
                "Resolve HF source/config/modeling paths.",
                "Record AIAK-Megatron and AIAK-Training-Omni baseline commits.",
                "Identify DS V4 architecture family/category.",
                "Extract MLA-related config fields and structural facts.",
                "Extract MoE router/expert/shared-expert facts.",
                "Extract MTP facts or explicitly prove MTP is absent.",
                "Extract checkpoint tensor naming patterns needed by Phase 2.",
                "Write reference_contract.yml linking baseline files/symbols to required components.",
                "Phase 1 strategy preflight can consume Phase 0 output without fallback_phase=0 for missing analysis.",
            ],
            "comparator_rules": [
                {"id": "phase0_mla", "markers": ["qk_rope_head_dim", "o_lora_rank", "csa_compress_ratios"]},
                {"id": "phase0_moe", "markers": ["moe_n_hash_layers", "moe_router_score_function", "sqrtsoftplus"]},
                {"id": "phase0_mtp", "markers": ["mtp_num_layers"]},
            ],
        },
        "phase1": {
            "version": 1,
            "goal": "Generate baseline-aligned framework-native DS V4 code.",
            "acceptance": [
                "Generated code uses framework-native integration, not standalone fallback.",
                "DS V4 config fields cover baseline-required fields.",
                "MLA component structure matches baseline-required classes/functions/interfaces.",
                "MoE component structure matches baseline-required classes/functions/interfaces.",
                "MTP component structure matches baseline-required classes/functions/interfaces, or absence is justified.",
                "Layer spec / module spec integration follows baseline native pattern.",
                "Lint/import/static checks pass where available on Mac.",
                "Phase 2 can consume generated code and config without missing structural information.",
            ],
            "comparator_rules": [
                {"id": "phase1_package", "markers": ["DeepseekV4Config", "DeepseekV4Model", "deepseek_v4_layer_spec"]},
                {"id": "phase1_attention", "markers": ["experimental_attention_variant", "dsv4_hybrid", "csa_compress_ratios"]},
                {"id": "phase1_moe_mtp", "markers": ["moe_n_hash_layers", "mtp_num_layers", "sqrtsoftplus"]},
            ],
        },
        "phase2": {
            "version": 1,
            "goal": "Generate baseline-aligned DS V4 conversion rules.",
            "acceptance": [
                "Conversion config/rules cover baseline DS V4 tensor names.",
                "MLA tensor mappings are present.",
                "MoE router/expert/shared expert tensor mappings are present.",
                "MTP tensor mappings are present or absence is justified.",
                "Split/merge/transpose rules match baseline intent.",
                "Converter entrypoints/scripts are generated.",
                "No runtime GPU gate is required for MVP pass.",
            ],
            "comparator_rules": [
                {"id": "phase2_mla_tensors", "markers": ["attention.q_down", "attention.q_up", "attention.kv_down"]},
                {"id": "phase2_moe_tensors", "markers": ["experts", "router", "shared"]},
                {"id": "phase2_mtp_tensors", "markers": ["mtp"]},
            ],
        },
        "phase3": {
            "status": "deferred",
            "reason": "Mac no GPU; runtime loss-diff validation is out of MVP scope.",
        },
        "phase4": {
            "status": "deferred",
            "reason": "Mac no GPU; runtime feature matrix validation is out of MVP scope.",
        },
    }


def init_loop_state(plugin_root: Path, repo: str = DEFAULT_REPO, force: bool = False) -> Path:
    state_dir = plugin_root / STATE_REL_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    for child in ("issue_specs", "verification_reports", "comparator_reports"):
        (state_dir / child).mkdir(parents=True, exist_ok=True)

    state_path = state_dir / "state.yml"
    contract_path = state_dir / "phase_goal_contract.yml"
    if force or not state_path.exists():
        dump_yaml(state_path, default_state(repo=repo))
    if force or not contract_path.exists():
        dump_yaml(contract_path, default_goal_contract())
    return state_dir


def load_state(state_dir: Path) -> dict[str, Any]:
    return load_yaml(state_dir / "state.yml")


def load_goal_contract(state_dir: Path) -> dict[str, Any]:
    return load_yaml(state_dir / "phase_goal_contract.yml")


def update_state(state_dir: Path, updates: dict[str, Any]) -> dict[str, Any]:
    data = load_state(state_dir)
    data.update(updates)
    dump_yaml(state_dir / "state.yml", data)
    return data
