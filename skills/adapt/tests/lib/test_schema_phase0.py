"""Tests for Phase 0 three-document Pydantic models: HfAnalysis, ReferenceImplAnalysis, BridgeMapping.

TDD RED phase: these tests define the required behavior before implementation.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from skills.adapt.lib.schema import (
    HfAnalysis,
    ReferenceImplAnalysis,
    BridgeMapping,
    ComponentAnalysis,
    NovelModule,
    Fp32Modules,
    BehaviorModification,
    SourceEvidence,
    MegatronModuleAnalysis,
    InitSignature,
    ForwardSignature,
    ParamEntry,
    ConfigFieldRef,
    SubmoduleSlot,
    WeightParamRef,
    ConfigClassAnalysis,
    ConfigFieldEntry,
    ComponentBridge,
    WeightMapEntry,
    BehavioralDiff,
    GapEntry,
)


# ---------------------------------------------------------------------------
# Test 1: HfAnalysis parses the current model_spec_llm.yaml content
# ---------------------------------------------------------------------------

def _hf_analysis_dict() -> dict:
    """A dict matching the fields from model_spec_llm.yaml (DeepSeek-V3 example)."""
    return {
        "model_category": "llm",
        "candidate_family": "deepseek_v3",
        "hf_reference_path": "/path/to/DeepSeek-V3-candidate",
        "candidate_match_reason": "README explicitly states based on DeepSeek-V3",
        "has_chat_template": False,
        "components": {
            "embedding": {
                "diff": "same",
                "strategy": "reuse_ref",
                "hf_class": "inline",
                "hf_file": "modeling_deepseek.py",
                "hf_line": 1344,
                "structural_tags": ["untied", "padding_idx"],
                "delta": [],
                "note": None,
                "same_class_as": None,
            },
            "attention": {
                "diff": "differs",
                "strategy": "adapt_ref",
                "delta": [
                    "q_lora_rank: 1536 (new) -> absent (candidate lacks)",
                    "v_head_dim: 128 (new) -> 96 (candidate)",
                ],
                "hf_class": "DeepseekV3Attention",
                "hf_file": "modeling_deepseek.py",
                "hf_line": 630,
                "structural_tags": [
                    "mla", "q_lora_rank=1536", "kv_lora_rank=512",
                    "qk_nope_head_dim=128", "qk_rope_head_dim=64",
                    "v_head_dim=128", "decoupled_rope",
                ],
                "note": None,
                "same_class_as": None,
            },
        },
        "novel_modules": [],
        "fp32_modules": {
            "strict_fp32": ["lm_head"],
            "non_strict_fp32": [],
        },
        "traps": [
            "moe_layer_freq=1 means every layer except the first dense_first_k=3 layers is MoE",
        ],
    }


def test_hf_analysis_parses_model_spec_content():
    """HfAnalysis must parse all fields from current model_spec_llm.yaml."""
    d = _hf_analysis_dict()
    model = HfAnalysis.model_validate(d)
    assert model.model_category == "llm"
    assert model.candidate_family == "deepseek_v3"
    assert "embedding" in model.components
    assert model.components["embedding"].diff == "same"
    assert model.components["embedding"].strategy == "reuse_ref"
    assert model.components["attention"].diff == "differs"
    assert model.components["attention"].strategy == "adapt_ref"
    assert len(model.components["attention"].delta) == 2
    assert model.novel_modules == []
    assert model.fp32_modules.strict_fp32 == ["lm_head"]


def test_hf_analysis_with_novel_modules():
    d = _hf_analysis_dict()
    d["novel_modules"] = [
        {
            "hf_class": "DeepseekV3HashRouter",
            "hf_file": "modeling_deepseek.py",
            "hf_line": 500,
            "desc": "Hash-based expert routing for MoE",
            "external_dependency": False,
            "sub_modules": ["router.linear"],
            "key_params": ["num_hash_groups", "hash_fn"],
        }
    ]
    model = HfAnalysis.model_validate(d)
    assert len(model.novel_modules) == 1
    assert model.novel_modules[0].hf_class == "DeepseekV3HashRouter"
    assert model.novel_modules[0].desc == "Hash-based expert routing for MoE"


def test_hf_analysis_with_behavior_modifications():
    d = _hf_analysis_dict()
    d["behavior_modifications"] = [
        {
            "id": "BM1",
            "component": "moe_gate",
            "behavior_type": "routing_bias",
            "source_evidence": {
                "hf_file": "modeling_deepseek.py",
                "hf_line": 412,
                "config_fields": ["e_score_correction_bias"],
            },
            "required_behavior": "e_score_correction_bias must be dynamically updated during inference",
            "affected_existing_modules": ["moe_gate"],
            "validation_hint": "Check that e_score_correction_bias is not frozen",
        }
    ]
    model = HfAnalysis.model_validate(d)
    assert len(model.behavior_modifications) == 1
    assert model.behavior_modifications[0].id == "BM1"
    assert model.behavior_modifications[0].component == "moe_gate"


# ---------------------------------------------------------------------------
# Test 2: ReferenceImplAnalysis parses a Megatron-side analysis
# ---------------------------------------------------------------------------

def _reference_impl_analysis_dict() -> dict:
    return {
        "megatron_family": "deepseek_v3",
        "source_repo": "https://github.com/Zachary-wW/Loong-Megatron",
        "source_ref": "loong-main/core_v0.15.0",
        "analysis_timestamp": "2026-06-24T08:00:00Z",
        "modules": {
            "MLASelfAttention": {
                "class_name": "MLASelfAttention",
                "source_file": "megatron/core/transformer/hybrid_mla_attention.py",
                "base_classes": ["ParallelAttention"],
                "init_signature": {
                    "params": [
                        {"name": "config", "type_hint": "MLAConfig", "default_value": None, "description": "MLA attention config"},
                        {"name": "q_lora_rank", "type_hint": "int", "default_value": "1536", "description": "Query LoRA rank"},
                    ]
                },
                "forward_signature": {
                    "inputs": [
                        {"name": "hidden_states", "type_hint": "Tensor", "default_value": None, "description": "Input hidden states"},
                    ],
                    "outputs": ["context", "context_mask"],
                    "description": "MLA forward pass",
                },
                "config_fields_used": [
                    {"field_name": "q_lora_rank", "config_class": "MLAConfig", "usage_description": "query LoRA compression rank"},
                ],
                "submodule_slots": [
                    {"slot_name": "core_attention", "slot_type": "ParallelAttention", "default_class": "CoreAttention", "is_replaceable": True},
                    {"slot_name": "linear_q_proj", "slot_type": "Linear", "default_class": "ColumnParallelLinear", "is_replaceable": True},
                ],
                "weight_params": [
                    {"param_name": "linear_q_proj.weight", "shape_hint": "1536x4096", "dtype": "float16"},
                ],
            }
        },
        "config_classes": {
            "MLAConfig": {
                "class_name": "MLAConfig",
                "source_file": "megatron/core/transformer/hybrid_mla_attention.py",
                "fields": [
                    {"field_name": "q_lora_rank", "type_hint": "int", "default_value": "1536", "description": "Query LoRA rank"},
                ],
                "parent_classes": ["TransformerConfig"],
            }
        },
    }


def test_reference_impl_analysis_parses():
    d = _reference_impl_analysis_dict()
    model = ReferenceImplAnalysis.model_validate(d)
    assert model.megatron_family == "deepseek_v3"
    assert "MLASelfAttention" in model.modules
    m = model.modules["MLASelfAttention"]
    assert m.class_name == "MLASelfAttention"
    assert len(m.init_signature.params) == 2
    assert m.init_signature.params[0].name == "config"
    assert len(m.forward_signature.inputs) == 1
    assert m.forward_signature.inputs[0].name == "hidden_states"
    assert len(m.submodule_slots) == 2
    assert m.submodule_slots[0].slot_name == "core_attention"
    assert len(m.weight_params) == 1
    assert "MLAConfig" in model.config_classes


# ---------------------------------------------------------------------------
# Test 3: BridgeMapping parses a complete component_bridge with weight_map and gaps
# ---------------------------------------------------------------------------

def _bridge_mapping_dict() -> dict:
    return {
        "model": "DeepSeek-V3",
        "hf_source": "transformers/models/deepseek_v3",
        "megatron_family": "deepseek_v3",
        "component_bridge": [
            {
                "hf": "attention",
                "megatron": ["MLASelfAttention"],
                "strategy": "adapt_ref",
                "confidence": "medium",
                "weight_map": [
                    {"hf": "self_attn.q_a_proj.weight", "megatron": "linear_q_proj.weight", "shape_hint": "1536x4096", "reshape_required": ""},
                ],
                "behavioral_diff": [
                    {
                        "topic": "q_lora_rank",
                        "hf": "q_lora_rank: 1536",
                        "megatron": "q_lora_rank: absent",
                        "impact": "high",
                        "strategy": "adapt_ref with param addition",
                    }
                ],
                "delta": ["q_lora_rank: 1536 (new) -> absent (candidate lacks)"],
            },
            {
                "hf": "mtp",
                "megatron": None,
                "strategy": "new_impl",
                "confidence": "low",
                "weight_map": None,
                "behavioral_diff": [],
                "delta": [],
            },
        ],
        "gaps": [
            {
                "id": "G1",
                "component": "mtp",
                "hf": "DeepseekV3MTP",
                "megatron": "NEW",
                "decision": "New implementation required in LoongForge model-specific code",
                "impact": "critical",
                "phase1_guidance": "Implement multi-token prediction module; check Megatron issue #4468 for reference",
            }
        ],
        "validator_requirements": [
            "phase1-verify: confirm forward alignment with MLA attention",
            "phase2-conversion: verify weight mapping for q_a_proj -> linear_q_proj",
        ],
    }


def test_bridge_mapping_parses_complete():
    d = _bridge_mapping_dict()
    model = BridgeMapping.model_validate(d)
    assert model.model == "DeepSeek-V3"
    assert len(model.component_bridge) == 2
    assert model.component_bridge[0].hf == "attention"
    assert model.component_bridge[0].megatron == ["MLASelfAttention"]
    assert model.component_bridge[0].confidence == "medium"
    assert len(model.component_bridge[0].weight_map) == 1
    assert model.component_bridge[0].weight_map[0].hf == "self_attn.q_a_proj.weight"
    assert model.component_bridge[1].megatron is None
    assert model.component_bridge[1].weight_map is None
    assert len(model.gaps) == 1
    assert model.gaps[0].id == "G1"
    assert model.gaps[0].impact == "critical"
    assert len(model.validator_requirements) == 2


# ---------------------------------------------------------------------------
# Test 4: BridgeMapping rejects a gap entry missing required field 'impact'
# ---------------------------------------------------------------------------

def test_bridge_mapping_rejects_gap_without_impact():
    d = _bridge_mapping_dict()
    del d["gaps"][0]["impact"]
    with pytest.raises(ValidationError, match="impact"):
        BridgeMapping.model_validate(d)


# ---------------------------------------------------------------------------
# Test 5: HfAnalysis rejects unknown extra fields (extra='forbid')
# ---------------------------------------------------------------------------

def test_hf_analysis_extra_forbid():
    d = _hf_analysis_dict()
    d["unknown_field"] = "should be rejected"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HfAnalysis.model_validate(d)


# ---------------------------------------------------------------------------
# Additional coverage: component_bridge extra forbid, weight_map None for gaps
# ---------------------------------------------------------------------------

def test_component_bridge_extra_forbid():
    d = _bridge_mapping_dict()
    d["component_bridge"][0]["unknown_key"] = "bad"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BridgeMapping.model_validate(d)


def test_gap_entry_requires_phase1_guidance():
    d = _bridge_mapping_dict()
    del d["gaps"][0]["phase1_guidance"]
    with pytest.raises(ValidationError):
        BridgeMapping.model_validate(d)


def test_bridge_mapping_with_absorbed_reference_contract():
    """BridgeMapping can carry absorbed reference_contract fields per D-05."""
    d = _bridge_mapping_dict()
    d["implementation_contract"] = {"required_integration_level": "framework_extension"}
    d["conversion_requirements"] = {"target_checkpoint_format": "mcore"}
    d["phase3_reference_requirements"] = {"allowed_reference_types": ["hf", "megatron"]}
    model = BridgeMapping.model_validate(d)
    assert model.implementation_contract is not None
    assert model.conversion_requirements is not None
    assert model.phase3_reference_requirements is not None


def test_bridge_mapping_with_references():
    """BridgeMapping can carry migrated reference entries per D-05."""
    d = _bridge_mapping_dict()
    d["references"] = [
        {
            "id": "ref_0",
            "locator": "https://github.com/NVIDIA/Megatron-LM/issues/4468",
            "type": "issue",
            "priority": "advisory",
            "scope": ["architecture", "operator_semantics"],
            "trust_level": "upstream",
            "component_coverage": {"attention": "partial", "moe": "none"},
        }
    ]
    model = BridgeMapping.model_validate(d)
    assert len(model.references) == 1
    assert model.references[0].id == "ref_0"


def test_hf_analysis_low_confidence_candidate():
    """HfAnalysis supports low_confidence_candidate fields per D-12."""
    d = _hf_analysis_dict()
    d["low_confidence_candidate"] = True
    d["low_confidence_reason"] = "No KB entry for DS V4; candidate is best match"
    model = HfAnalysis.model_validate(d)
    assert model.low_confidence_candidate is True
    assert model.low_confidence_reason == "No KB entry for DS V4; candidate is best match"
