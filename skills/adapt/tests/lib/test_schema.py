"""Tests for skills.adapt.lib.schema — Pydantic v2 models for run_inputs.yml."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from skills.adapt.lib.schema import (
    RunInputs,
    ReposBlock,
    RepoSpec,
    HFImplSpec,
    HFCkptSpec,
    LoopBudget,
    LoopBlockOutput,
    PrBlockOutput,
    IssuesBlockOutput,
    SourceBlock,
    PathsBlock,
    OptionsBlock,
)


# ---------------------------------------------------------------------------
# Legacy v1 round-trip
# ---------------------------------------------------------------------------

def _legacy_v1_dict() -> dict:
    """A dict matching the legacy _build_run_inputs output (no repos/loop)."""
    return {
        "source": {"hf_ckpt_path": "/tmp/m"},
        "paths": {
            "hf_modeling_path": "",
            "hf_transformers_path": "",
            "omni_path": "",
            "megatron_path": "",
        },
        "options": {
            "model_name": "x",
            "gpu_execution_mode": "local_gpu",
            "enable_slice_ckpt": "false",
            "k8s_yaml_path": "",
            "k8s_launch_cmd": "",
            "wip_code_paths": "",
        },
    }


def test_legacy_v1_round_trip():
    d = _legacy_v1_dict()
    model = RunInputs.model_validate(d)
    dumped = model.model_dump(exclude_none=True, mode="json")
    assert dumped == d


def test_legacy_v1_no_repos_loop_engineering_disabled():
    model = RunInputs.model_validate(_legacy_v1_dict())
    assert model.loop_engineering_enabled is False
    assert model.repos is None
    assert model.loop is None


# ---------------------------------------------------------------------------
# V2 round-trip (with repos + loop)
# ---------------------------------------------------------------------------

def _v2_dict() -> dict:
    return {
        "source": {"hf_ckpt_path": "/tmp/m"},
        "paths": {
            "hf_modeling_path": "",
            "hf_transformers_path": "",
            "omni_path": "",
            "megatron_path": "",
        },
        "options": {
            "model_name": "x",
            "gpu_execution_mode": "local_gpu",
            "enable_slice_ckpt": "false",
            "k8s_yaml_path": "",
            "k8s_launch_cmd": "",
            "wip_code_paths": "",
        },
        "repos": {
            "hf_impl": {"url": "https://github.com/huggingface/transformers", "ref": "main"},
            "hf_ckpt": {"url": "https://huggingface.co/org/model"},
            "loongforge": {"url": "https://github.com/Zachary-wW/LoongForge", "base_ref": "main", "work_branch": ""},
            "megatron": {"url": "https://github.com/Zachary-wW/Loong-Megatron", "base_ref": "loong-main/core_v0.15.0", "work_branch": ""},
        },
        "loop": {
            "max_attempts_per_phase": 5,
            "max_attempts_per_run": 25,
            "max_wallclock_minutes": 240,
            "escalation": "human_needed",
        },
    }


def test_v2_round_trip():
    d = _v2_dict()
    model = RunInputs.model_validate(d)
    assert model.loop_engineering_enabled is True
    dumped = model.model_dump(exclude_none=True, mode="json")
    # The dumped dict should re-validate to the same model
    RunInputs.model_validate(dumped)


def test_v2_repos_present_loop_engineering_enabled():
    model = RunInputs.model_validate(_v2_dict())
    assert model.loop_engineering_enabled is True
    assert model.repos is not None
    assert str(model.repos.hf_impl.url) == "https://github.com/huggingface/transformers"
    assert model.repos.loongforge.base_ref == "main"
    assert model.repos.megatron.base_ref == "loong-main/core_v0.15.0"


# ---------------------------------------------------------------------------
# extra="forbid" rejects typos
# ---------------------------------------------------------------------------

def test_extra_forbid_rejects_typo_repo():
    d = _legacy_v1_dict()
    d["repo"] = {"url": "https://example.com"}  # typo: "repo" instead of "repos"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RunInputs.model_validate(d)


def test_extra_forbid_rejects_unknown_key_in_repos():
    d = _v2_dict()
    d["repos"]["unknown_repo"] = {"url": "https://example.com"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RunInputs.model_validate(d)


# ---------------------------------------------------------------------------
# LoopBudget ceiling enforcement
# ---------------------------------------------------------------------------

def test_loop_budget_max_attempts_per_phase_ceiling():
    with pytest.raises(ValidationError):
        LoopBudget(max_attempts_per_phase=51)


def test_loop_budget_max_attempts_per_run_ceiling():
    with pytest.raises(ValidationError):
        LoopBudget(max_attempts_per_run=501)


def test_loop_budget_max_wallclock_minutes_ceiling():
    with pytest.raises(ValidationError):
        LoopBudget(max_wallclock_minutes=10081)


def test_loop_budget_valid_boundaries():
    # These should NOT raise
    LoopBudget(max_attempts_per_phase=1, max_attempts_per_run=1, max_wallclock_minutes=10)
    LoopBudget(max_attempts_per_phase=50, max_attempts_per_run=500, max_wallclock_minutes=10080)


# ---------------------------------------------------------------------------
# LOG-02 forward-compat: PrBlockOutput and IssuesBlockOutput
# ---------------------------------------------------------------------------

def test_pr_block_skeleton_forward_compat():
    """PrBlockOutput with extra='ignore' silently drops unknown keys."""
    model = PrBlockOutput.model_validate({
        "number": 7,
        "url": "https://x",
        "unknown_future": "ok",
    })
    assert model.number == 7
    assert model.url == "https://x"
    assert model.merged_sha is None


def test_pr_block_skeleton_defaults():
    model = PrBlockOutput.model_validate({})
    assert model.number is None
    assert model.url is None
    assert model.head is None
    assert model.base is None
    assert model.state is None
    assert model.merged_sha is None
    assert model.idempotency_key is None


def test_issues_block_skeleton_forward_compat():
    """IssuesBlockOutput with extra='ignore' silently drops unknown keys."""
    model = IssuesBlockOutput.model_validate({
        "opened": [1, 2],
        "closed": [],
        "escalated": [],
        "future_key": "ok",
    })
    assert model.opened == [1, 2]
    assert model.closed == []
    assert model.escalated == []


def test_issues_block_skeleton_defaults():
    model = IssuesBlockOutput.model_validate({})
    assert model.opened == []
    assert model.closed == []
    assert model.escalated == []


# ---------------------------------------------------------------------------
# LoopBlockOutput
# ---------------------------------------------------------------------------

def test_loop_block_output_exit_reason_values():
    for reason in [
        "validator_passed",
        "validator_passed_after_fix",
        "exhausted",
        "escalated",
        "base_only",
        "human_needed",
    ]:
        model = LoopBlockOutput(exit_reason=reason)
        assert model.exit_reason == reason


def test_loop_block_output_invalid_exit_reason():
    with pytest.raises(ValidationError):
        LoopBlockOutput(exit_reason="invalid_reason")


# ---------------------------------------------------------------------------
# Sub-model extra="forbid" enforcement
# ---------------------------------------------------------------------------

def test_repo_spec_extra_forbid():
    with pytest.raises(ValidationError):
        RepoSpec(url="https://github.com/org/repo", extra_field="bad")


def test_hf_impl_spec_extra_forbid():
    with pytest.raises(ValidationError):
        HFImplSpec(url="https://github.com/org/repo", extra_field="bad")


def test_hf_ckpt_spec_extra_forbid():
    with pytest.raises(ValidationError):
        HFCkptSpec(url="https://huggingface.co/org/model", extra_field="bad")


def test_repos_block_extra_forbid():
    with pytest.raises(ValidationError):
        ReposBlock(
            hf_impl=HFImplSpec(url="https://github.com/a/b"),
            hf_ckpt=HFCkptSpec(url="https://huggingface.co/a/b"),
            loongforge=RepoSpec(url="https://github.com/a/b"),
            megatron=RepoSpec(url="https://github.com/a/b"),
            extra="bad",
        )
