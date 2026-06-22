"""Pydantic v2 schema models for run_inputs.yml and phase output extensions.

Models:
  RepoSpec, HFImplSpec, HFCkptSpec, ReposBlock,
  LoopBudget, SourceBlock, PathsBlock, OptionsBlock, RunInputs,
  LoopBlockOutput, PrBlockOutput, IssuesBlockOutput.
"""
from __future__ import annotations

from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


# --- Repo specs ----------------------------------------------------------

class RepoSpec(BaseModel):
    """A single git repo reference (LoongForge or Loong-Megatron)."""
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl
    base_ref: str = "main"
    work_branch: str = ""           # filled at loop time, not by user
    subpath: Optional[str] = None   # optional path within repo


class HFImplSpec(BaseModel):
    """HF model implementation reference (subpath inside HF transformers)."""
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl
    ref: str = "main"
    subpath: Optional[str] = None


class HFCkptSpec(BaseModel):
    """HF checkpoint + tokenizer reference (HuggingFace hub URL)."""
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl                    # https://huggingface.co/<org>/<model>
    revision: str = "main"


class ReposBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hf_impl: HFImplSpec
    hf_ckpt: HFCkptSpec
    loongforge: RepoSpec
    megatron: RepoSpec


class LoopBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_attempts_per_phase: int = Field(5, ge=1, le=50)
    max_attempts_per_run: int = Field(25, ge=1, le=500)
    max_wallclock_minutes: int = Field(240, ge=10, le=10_080)
    escalation: Literal["human_needed", "autonomous_blocked"] = "human_needed"


# --- run_inputs.yml v2 (legacy v1 stays valid) ---------------------------

class SourceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hf_ckpt_path: str = ""


class PathsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hf_modeling_path: str = ""
    hf_transformers_path: str = ""
    omni_path: str = ""
    megatron_path: str = ""


class OptionsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_name: str = ""
    gpu_execution_mode: Literal["local_gpu", "k8s"] = "local_gpu"
    enable_slice_ckpt: Literal["true", "false"] = "false"
    k8s_yaml_path: str = ""
    k8s_launch_cmd: str = ""
    wip_code_paths: str = ""        # JSON-stringified list, kept opaque


class RunInputs(BaseModel):
    """Top-level run_inputs.yml. v1 had source/paths/options only.
    v2 adds optional repos and loop. Backward compat: omit them and we behave as v1."""
    model_config = ConfigDict(extra="forbid")
    source: SourceBlock = Field(default_factory=SourceBlock)
    paths: PathsBlock = Field(default_factory=PathsBlock)
    options: OptionsBlock = Field(default_factory=OptionsBlock)
    repos: Optional[ReposBlock] = None
    loop: Optional[LoopBudget] = None

    @model_validator(mode="after")
    def _v2_sanity(self) -> "RunInputs":
        # If `repos` is present, all four sub-fields must be present (Pydantic
        # already enforces this via ReposBlock). If `repos` is absent, we
        # silently disable loop engineering (loop_engineering=False downstream).
        return self

    @property
    def loop_engineering_enabled(self) -> bool:
        return self.repos is not None


# --- phaseN_output.yml extension (Phase 1 lays inert hook) ---------------

class LoopBlockOutput(BaseModel):
    """Optional `loop:` block in phaseN_output.yml. Only validated when
    loop_engineering: true is set."""
    model_config = ConfigDict(extra="forbid")
    attempts: int = Field(0, ge=0)
    max_attempts: int = Field(5, ge=1)
    exit_reason: Literal[
        "validator_passed", "validator_passed_after_fix",
        "exhausted", "escalated", "base_only", "human_needed",
    ] = "validator_passed"
    attempts_journal: str = ""


# --- LOG-02 forward-compat skeletons (Phase 2 fills field details) -------

class PrBlockOutput(BaseModel):
    """Skeleton for the optional `pr:` block in phaseN_output.yml.
    Phase 1 ships fields-as-known; extra="ignore" lets Phase 2 add more keys
    without breaking Phase 1 readers."""
    model_config = ConfigDict(extra="ignore")
    number: Optional[int] = None         # PR number once opened
    url: Optional[str] = None            # PR HTML URL
    head: Optional[str] = None           # head branch (work_branch)
    base: Optional[str] = None           # base branch (base_ref)
    state: Optional[Literal["open", "closed", "merged"]] = None
    merged_sha: Optional[str] = None     # commit sha after merge
    idempotency_key: Optional[str] = None


class IssuesBlockOutput(BaseModel):
    """Skeleton for the optional `issues:` block in phaseN_output.yml.
    Same forward-compat policy as PrBlockOutput."""
    model_config = ConfigDict(extra="ignore")
    opened: list[int] = Field(default_factory=list)   # issue numbers opened by the loop
    closed: list[int] = Field(default_factory=list)   # issue numbers auto-closed on success
    escalated: list[int] = Field(default_factory=list) # issue numbers handed to humans
