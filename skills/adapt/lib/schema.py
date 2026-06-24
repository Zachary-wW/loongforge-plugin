"""Pydantic v2 schema models for run_inputs.yml, phase output extensions,
and Phase 0 three-document output (HfAnalysis, ReferenceImplAnalysis, BridgeMapping).

Models (run_inputs / loop):
  RepoSpec, HFImplSpec, HFCkptSpec, ReposBlock,
  LoopBudget, SourceBlock, PathsBlock, OptionsBlock, RunInputs,
  LoopBlockOutput, PrBlockOutput, IssuesBlockOutput.

Models (Phase 0 three-document output):
  ComponentAnalysis, NovelModule, Fp32Modules, BehaviorModification,
  SourceEvidence, HfAnalysis,
  ParamEntry, InitSignature, ForwardSignature, ConfigFieldRef,
  SubmoduleSlot, WeightParamRef, MegatronModuleAnalysis,
  ConfigFieldEntry, ConfigClassAnalysis, ReferenceImplAnalysis,
  WeightMapEntry, BehavioralDiff, ComponentBridge, GapEntry,
  ReferenceEntry, BridgeMapping.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

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
    schema_version: Optional[str] = "2"
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
        "exhausted", "escalated", "base_only", "human_needed", "fix_needed",
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


# ===========================================================================
# Phase 0 Three-Document Output Models (per D-01, D-06, D-16)
# ===========================================================================

# --- HfAnalysis sub-models -------------------------------------------------

class ComponentAnalysis(BaseModel):
    """Per-component analysis within HfAnalysis.components (supersedes
    model_spec.yaml components per D-01, D-04)."""
    model_config = ConfigDict(extra="forbid")
    diff: Literal["same", "differs", "new_component", "absent_in_hf"]
    strategy: Literal["reuse_ref", "adapt_ref", "new_impl"]
    delta: List[str] = []
    note: Optional[str] = None
    hf_class: Optional[str] = None
    hf_file: Optional[str] = None
    hf_line: Optional[int] = None
    structural_tags: List[str] = []
    same_class_as: Optional[str] = None


class NovelModule(BaseModel):
    """A novel module in the HF implementation not present in candidate."""
    model_config = ConfigDict(extra="forbid")
    hf_class: str
    hf_file: Optional[str] = None
    hf_line: Optional[int] = None
    desc: str
    external_dependency: bool = False
    sub_modules: List[str] = []
    key_params: List[str] = []


class Fp32Modules(BaseModel):
    """FP32 module classification (strict vs non-strict)."""
    model_config = ConfigDict(extra="forbid")
    strict_fp32: List[str] = []
    non_strict_fp32: List[str] = []


class SourceEvidence(BaseModel):
    """Source evidence for a behavior modification."""
    model_config = ConfigDict(extra="forbid")
    hf_file: Optional[str] = None
    hf_line: Optional[int] = None
    config_fields: List[str] = []


class BehaviorModification(BaseModel):
    """A behavior modification — changes to computation without new components."""
    model_config = ConfigDict(extra="forbid")
    id: str
    component: str
    behavior_type: str
    source_evidence: SourceEvidence
    required_behavior: str
    affected_existing_modules: List[str] = []
    validation_hint: str = ""


class WeightStructure(BaseModel):
    """Weight structure summary appended by Phase 0 Step 4."""
    model_config = ConfigDict(extra="forbid")
    total_keys: int = 0
    components: Dict[str, Any] = {}


# --- HfAnalysis (supersedes model_spec.yaml — per D-01, D-04) ---------------

class HfAnalysis(BaseModel):
    """HF-side analysis output. Supersedes model_spec.yaml (per D-01, D-04).
    Preserves all fields from model_spec_llm.yaml and adds new sections
    (fp32_modules, behavior_modifications)."""
    model_config = ConfigDict(extra="forbid")
    model_category: Literal["llm", "vlm", "diffusion"]
    candidate_family: str
    hf_reference_path: str
    candidate_match_reason: str
    has_chat_template: bool = False
    low_confidence_candidate: Optional[bool] = None
    low_confidence_reason: Optional[str] = None
    components: Dict[str, ComponentAnalysis] = {}
    novel_modules: List[NovelModule] = []
    fp32_modules: Fp32Modules = Field(default_factory=Fp32Modules)
    generation_constraints: List[str] = []
    config_precision_delta: List[str] = []
    behavior_modifications: List[BehaviorModification] = []
    traps: List[str] = []
    special_features: Optional[Dict[str, Any]] = None
    weight_structure: Optional[WeightStructure] = None


# --- ReferenceImplAnalysis sub-models (NEW — per D-06, D-18) ---------------

class ParamEntry(BaseModel):
    """A single parameter in a function/class signature."""
    model_config = ConfigDict(extra="forbid")
    name: str
    type_hint: str = ""
    default_value: Optional[str] = None
    description: str = ""


class InitSignature(BaseModel):
    """__init__ signature of a Megatron module."""
    model_config = ConfigDict(extra="forbid")
    params: List[ParamEntry] = []


class ForwardSignature(BaseModel):
    """forward() signature of a Megatron module."""
    model_config = ConfigDict(extra="forbid")
    inputs: List[ParamEntry] = []
    outputs: List[str] = []
    description: str = ""


class ConfigFieldRef(BaseModel):
    """Reference to a config field used by a Megatron module."""
    model_config = ConfigDict(extra="forbid")
    field_name: str
    config_class: str
    usage_description: str = ""


class SubmoduleSlot(BaseModel):
    """A replaceable submodule slot in a Megatron module."""
    model_config = ConfigDict(extra="forbid")
    slot_name: str
    slot_type: str
    default_class: str = ""
    is_replaceable: bool = True


class WeightParamRef(BaseModel):
    """A weight parameter reference in a Megatron module."""
    model_config = ConfigDict(extra="forbid")
    param_name: str
    shape_hint: str = ""
    dtype: str = ""


class MegatronModuleAnalysis(BaseModel):
    """Analysis of a single Megatron module (per D-06)."""
    model_config = ConfigDict(extra="forbid")
    class_name: str
    source_file: str
    base_classes: List[str] = []
    init_signature: InitSignature = Field(default_factory=InitSignature)
    forward_signature: ForwardSignature = Field(default_factory=ForwardSignature)
    config_fields_used: List[ConfigFieldRef] = []
    submodule_slots: List[SubmoduleSlot] = []
    weight_params: List[WeightParamRef] = []


class ConfigFieldEntry(BaseModel):
    """A single field in a Megatron config class."""
    model_config = ConfigDict(extra="forbid")
    field_name: str
    type_hint: str = ""
    default_value: Optional[str] = None
    description: str = ""


class ConfigClassAnalysis(BaseModel):
    """Analysis of a Megatron config class."""
    model_config = ConfigDict(extra="forbid")
    class_name: str
    source_file: str
    fields: List[ConfigFieldEntry] = []
    parent_classes: List[str] = []


# --- ReferenceImplAnalysis (NEW — per D-06, D-18) --------------------------

class ReferenceImplAnalysis(BaseModel):
    """Megatron/community-side analysis output (NEW — per D-06, D-18).
    Contains class signatures, init members, forward flow, config fields
    for existing Megatron modules."""
    model_config = ConfigDict(extra="forbid")
    megatron_family: str
    source_repo: str
    source_ref: str = "main"
    analysis_timestamp: str = ""
    modules: Dict[str, MegatronModuleAnalysis] = {}
    config_classes: Dict[str, ConfigClassAnalysis] = {}


# --- BridgeMapping sub-models (NEW — per D-16, D-09, D-07) -----------------

class WeightMapEntry(BaseModel):
    """A single HF→Megatron weight mapping entry (per D-11)."""
    model_config = ConfigDict(extra="forbid")
    hf: str
    megatron: str
    shape_hint: str = ""
    reshape_required: str = ""


class BehavioralDiff(BaseModel):
    """A behavioral difference between HF and Megatron for a component."""
    model_config = ConfigDict(extra="forbid")
    topic: str
    hf: str
    megatron: str
    impact: Literal["critical", "high", "medium"]
    strategy: str = ""


class ComponentBridge(BaseModel):
    """A single component bridge entry in bridge_mapping.yaml (per D-16)."""
    model_config = ConfigDict(extra="forbid")
    hf: str
    megatron: Optional[List[str]] = None     # None for gaps (per D-09)
    strategy: Literal["reuse_ref", "adapt_ref", "new_impl"]
    confidence: Literal["high", "medium", "low"]
    weight_map: Optional[List[WeightMapEntry]] = None  # None when Megatron module absent (per D-10)
    behavioral_diff: List[BehavioralDiff] = []
    delta: List[str] = []


class GapEntry(BaseModel):
    """A gap entry — component without Megatron counterpart (per D-07)."""
    model_config = ConfigDict(extra="forbid")
    id: str                               # G1, G2, ...
    component: str
    hf: str
    megatron: str                          # what exists or "NEW" (per D-07)
    decision: str
    impact: Literal["critical", "high", "medium"]
    phase1_guidance: str


class ReferenceEntry(BaseModel):
    """A reference entry migrated from reference_contract.yml (per D-05)."""
    model_config = ConfigDict(extra="forbid")
    id: str
    locator: str
    type: str = "other"
    priority: str = "advisory"
    scope: List[str] = []
    trust_level: str = "inferred"
    component_coverage: Optional[Dict[str, str]] = None


# --- BridgeMapping (NEW — per D-16, D-09, D-07, D-05) ----------------------

class BridgeMapping(BaseModel):
    """Component-by-component bridge mapping (per D-16). The core deliverable
    that downstream phases consume. Absorbs reference_contract.yml fields
    (per D-05)."""
    model_config = ConfigDict(extra="forbid")
    model: str
    hf_source: str
    megatron_family: str
    component_bridge: List[ComponentBridge] = []
    gaps: List[GapEntry] = []
    validator_requirements: List[str] = []
    # Absorbed from reference_contract.yml (per D-05)
    implementation_contract: Optional[Dict[str, Any]] = None
    conversion_requirements: Optional[Dict[str, Any]] = None
    phase3_reference_requirements: Optional[Dict[str, Any]] = None
    # Migrated references (per D-05)
    references: List[ReferenceEntry] = []
