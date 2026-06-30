from __future__ import annotations

import json
from pathlib import Path

import yaml

from skills.adapt.scripts.phase1_codegen import generate_phase1_fallback
from skills.adapt.scripts.validate_phase_completion import validate_phase_output


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _minimal_megatron_tree(root: Path) -> None:
    _write(root / "megatron/core/transformer/transformer_config.py", '''from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TransformerConfig:
    experimental_attention_variant: Optional[str] = None
''')
    _write(root / "megatron/core/transformer/moe/moe_utils.py", '''import torch


def topk_routing_with_score_function(logits, topk, score_function="softmax", expert_bias=None):
    def compute_topk(scores, topk, num_groups=None, group_topk=None):
        return torch.topk(scores, k=topk, dim=1)
    num_groups = None
    group_topk = None
    if score_function == "softmax":
        scores, top_indices = compute_topk(logits, topk, num_groups, group_topk)
        probs = torch.softmax(scores, dim=-1, dtype=torch.float32).type_as(logits)
    elif score_function == "sigmoid":
        scores = torch.sigmoid(logits.float()).type_as(logits)
        if expert_bias is not None:
            scores_for_routing = scores + expert_bias
            _, top_indices = compute_topk(scores_for_routing, topk, num_groups, group_topk)
            scores = torch.gather(scores, dim=1, index=top_indices).type_as(logits)
        else:
            scores, top_indices = compute_topk(scores, topk, num_groups, group_topk)
        probs = scores / (scores.sum(dim=-1, keepdim=True) + 1e-20) if topk > 1 else scores
    else:
        raise ValueError(f"Invalid score_function: {score_function}")
    return probs, top_indices


def compute_routing_scores_for_aux_loss(logits, topk, score_function):
    if score_function == "softmax":
        scores = torch.softmax(logits, dim=-1, dtype=torch.float32)
    elif score_function == "sigmoid":
        scores = torch.sigmoid(logits)
        scores = scores / (scores.sum(dim=-1, keepdim=True) + 1e-20)
    else:
        raise ValueError(f"Invalid score_function: {score_function}")
    return scores
''')
    _write(root / "megatron/core/transformer/moe/router.py", '''class TopKRouter:
    pass
''')
    _write(root / "megatron/core/transformer/moe/moe_layer.py", '''from typing import Optional
import torch


class MoELayer:
    def router_and_preprocess(self, hidden_states: torch.Tensor):
        probs, routing_map = self.router(hidden_states)
        return hidden_states, probs, hidden_states

    def forward(self, hidden_states: torch.Tensor):
        def custom_forward(hidden_states):
            hidden_states, probs, residual = self.router_and_preprocess(hidden_states)
            return hidden_states, None
        def custom_forward_exclude_shared_experts(hidden_states):
            hidden_states, probs, residual = self.router_and_preprocess(hidden_states)
            return hidden_states, None
        return custom_forward(hidden_states)
''')
    _write(root / "megatron/core/transformer/transformer_layer.py", '''import logging
from typing import Optional
from torch import Tensor


class TransformerLayer:
    def forward(self, *args, **kwargs):
        kwargs.pop("dynamic_inference_decode_only", None)
        output = self._forward_mlp(
            args[0],
            kwargs.get("inference_context", None),
            is_last_layer_in_recompute_block=False,
        )
        return output, None

    def _forward_mlp(
        self,
        hidden_states,
        inference_context=None,
        padding_mask=None,
        mhc_recompute_manager=None,
        is_last_layer_in_recompute_block: bool = False,
    ):
        if self.recompute_mlp:
            pass
        elif False:
            outputs = [self.mlp(chunk) for chunk in chunks]
        else:
            mlp_output_with_bias = self.mlp(hidden_states)
        return mlp_output_with_bias
''')
    _write(root / "megatron/core/models/gpt/gpt_model.py", '''class GPTModel:
    def forward(self, decoder_input, attention_mask=None, extra_block_kwargs=None, input_ids=None):
        # Run decoder.
        hidden_states = self.decoder(
            hidden_states=decoder_input,
            attention_mask=attention_mask,
            **(extra_block_kwargs or {}),
        )
        return hidden_states
''')
    _write(root / "megatron/core/models/gpt/experimental_attention_variant_module_specs.py", '''def get_experimental_attention_variant_module_spec_for_backend(
    backend,
    experimental_attention_variant=None,
    qk_layernorm=False,
    qk_l2_norm=False,
    multi_latent_attention=False,
    num_experts=None,
    mlp=None,
    enable_hyper_connection=False,
):
    if experimental_attention_variant == "dsa":
        return "dsa"
    raise ValueError(f"Invalid experimental attention variant: {experimental_attention_variant}")


def get_dsa_module_spec_for_backend(*args, **kwargs):
    return "dsa"
''')


def test_phase1_codegen_generates_deepseek_v4_fallback_and_gate_passes(tmp_path):
    run_dir = tmp_path / "run"
    omni = run_dir / "sources" / "LoongForge"
    megatron = run_dir / "sources" / "Loong-Megatron"
    (run_dir / "phases" / "phase0").mkdir(parents=True)
    (run_dir / "phases" / "phase1" / "logs").mkdir(parents=True)
    _minimal_megatron_tree(megatron)

    (run_dir / "run_inputs.yml").write_text(yaml.dump({
        "schema_version": "2",
        "source": {"hf_ckpt_path": "/tmp/DeepSeek-V4"},
        "paths": {
            "hf_modeling_path": "/tmp/transformers/models/deepseek_v4",
            "omni_path": str(omni),
            "megatron_path": str(megatron),
        },
        "options": {"model_name": "DeepSeek-V4-Flash"},
    }))
    (run_dir / "phases" / "phase0" / "bridge_mapping.yaml").write_text(yaml.dump({
        "model": "deepseek_v4",
        "component_bridge": [
            {"hf": "DeepseekV4Attention", "strategy": "new_impl", "confidence": "low"},
        ],
        "gaps": [
            {"id": "G1", "component": "hybrid_csa_hca_attention", "phase1_guidance": "implement"},
        ],
    }))
    (run_dir / "phases" / "phase0_output.yml").write_text(yaml.dump({
        "phase": 0,
        "status": "passed",
        "artifacts": {"bridge_mapping_path": "phases/phase0/bridge_mapping.yaml"},
    }))

    assert generate_phase1_fallback(run_dir) is True

    generated = json.loads((run_dir / "phases" / "phase1" / "generated_files.json").read_text())
    assert len(generated) >= 30
    assert "loongforge/models/foundation/deepseek_v4/deepseek_v4_config.py" in generated
    assert "loongforge/models/foundation/deepseek_v4/deepseek_v4_csa.py" in generated
    assert "examples/deepseek_v4/pretrain/pretrain_deepseek_v4_fp8.sh" in generated
    assert "megatron/core/transformer/experimental_attention_variant/deepseek_v4_hybrid_attention.py" in generated
    assert "megatron/core/transformer/experimental_attention_variant/csa.py" in generated
    assert "megatron/core/fusions/fused_mla_yarn_rope_apply.py" in generated
    assert (megatron / "megatron/core/transformer/experimental_attention_variant/csa.py").exists()

    output = yaml.safe_load((run_dir / "phases" / "phase1_output.yml").read_text())
    assert output["status"] == "passed"
    assert output["checks"]["bridge_mapping_consumed"] is True
    assert output["checks"]["code_generated"] is True
    assert output["validation_scope"] == "native_codegen_l0"
    assert output["checks"]["forward_alignment_passed"] is True
    assert output["artifacts"]["example_pretrain_script"] == "examples/deepseek_v4/pretrain/pretrain_deepseek_v4_fp8.sh"

    validate_phase_output(run_dir, phase=1)
