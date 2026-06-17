# Copyright 2026 The LoongForge Authors.
# SPDX-License-Identifier: Apache-2.0

"""DeepSeek-V4 Attention with Compressor, Indexer, and Grouped Output Projection.

V4 attention architecture:
- MLA: Q low-rank (wq_a -> q_norm -> wq_b), single-stage KV (wkv -> kv_norm)
- Per-head QK-norm (rsqrt normalization)
- Learnable attention sink (per-head logit bias, applied via SDPA mask sink column)
- Token-level KV Compressor (gated softmax pooling with optional overlap for CSA)
- Lightning Indexer (sparse KV selection via BF16 scoring + top-k)
- Grouped output projection (wo_a -> wo_b)
- Sliding window local KV branch for all layer types

Attention compute is performed via standard SDPA for all layer variants:
- SWA layers (compress_ratio=0): full KV with sliding-window causal mask.
- CSA/HCA layers: window KV + compressor-emitted compressed KV concatenated;
  mask combines window causality with per-query causal-on-chunks (and indexer
  top-k selection for CSA).
"""

from dataclasses import dataclass
from typing import Optional, Union

import math

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from megatron.core import parallel_state
from megatron.core.transformer.module import MegatronModule
from megatron.core.transformer.spec_utils import ModuleSpec, build_module
from megatron.core.transformer.enums import AttnMaskType
from megatron.core.transformer.transformer_config import TransformerConfig
from megatron.core.packed_seq_params import PackedSeqParams


# ---------------------------------------------------------------------------
# RoPE inv_freq helpers (U5 — dual rope per layer type)
#
# Upstream HF transformers (SHA a25b8ef) builds TWO rope pools per model:
#   - "main":    rope_type="default", plain θ=10000, no scaling — used by
#                sliding_attention layers.
#   - "compress": rope_type="yarn", θ=160000, factor=16,
#                original_max_position_embeddings=65536, beta_fast=32,
#                beta_slow=1, attention_factor=1.0 — used by CSA/HCA layers
#                for BOTH main Q/K rope AND their internal Compressor/Indexer.
#
# AIAK's BaseGPTModel does not build rotary_pos_emb when
# multi_latent_attention=True, so DeepseekV4Attention owns its rope state.
# ---------------------------------------------------------------------------

def _plain_inv_freq(base: float, dim: int,
                    dtype: torch.dtype = torch.float32) -> Tensor:
    """Default (plain) RoPE inverse frequencies: 1 / base^(2i/dim)."""
    return 1.0 / (base ** (torch.arange(0, dim, 2, dtype=dtype) / dim))


def _yarn_inv_freq(
    base: float,
    dim: int,
    factor: float,
    original_max_position_embeddings: int,
    beta_fast: float = 32.0,
    beta_slow: float = 1.0,
    truncate: bool = True,
    dtype: torch.dtype = torch.float32,
) -> Tensor:
    """YaRN-scaled inverse frequencies.

    Mirrors upstream `_compute_yarn_parameters` in
    transformers/modeling_rope_utils.py at SHA a25b8ef. attention_factor is
    forced to 1.0 in DS V4 compress rope config, so we only return inv_freq
    here (no cos/sin mscale multiplier).
    """
    pos_freqs = base ** (torch.arange(0, dim, 2, dtype=dtype) / dim)
    inv_freq_extrapolation = 1.0 / pos_freqs
    inv_freq_interpolation = 1.0 / (factor * pos_freqs)

    def _find_correction_dim(num_rotations, d, b, max_pos):
        return (d * math.log(max_pos / (num_rotations * 2 * math.pi))) / (2 * math.log(b))

    def _find_correction_range(low_rot, high_rot, d, b, max_pos, trunc):
        low = _find_correction_dim(low_rot, d, b, max_pos)
        high = _find_correction_dim(high_rot, d, b, max_pos)
        if trunc:
            low = math.floor(low)
            high = math.ceil(high)
        return max(low, 0), min(high, d - 1)

    low, high = _find_correction_range(
        beta_fast, beta_slow, dim, base,
        original_max_position_embeddings, truncate,
    )
    if low == high:
        high = high + 0.001
    linear_func = (torch.arange(dim // 2, dtype=dtype) - low) / (high - low)
    ramp = torch.clamp(linear_func, 0.0, 1.0)
    extrap_factor = 1.0 - ramp
    return (
        inv_freq_interpolation * (1.0 - extrap_factor)
        + inv_freq_extrapolation * extrap_factor
    )


def _compress_yarn_inv_freq(config, rope_dim: int,
                            dtype: torch.dtype = torch.float32) -> Tensor:
    """Build the compress-path YaRN inv_freq from a TransformerConfig."""
    return _yarn_inv_freq(
        base=float(getattr(config, "csa_compress_rotary_base", 160000.0)),
        dim=rope_dim,
        factor=float(getattr(config, "rotary_scaling_factor", 16.0)),
        original_max_position_embeddings=int(
            getattr(config, "original_max_position_embeddings", 65536)
        ),
        beta_fast=float(getattr(config, "beta_fast", 32.0)),
        beta_slow=float(getattr(config, "beta_slow", 1.0)),
        truncate=True,
        dtype=dtype,
    )


# ---------------------------------------------------------------------------
# Submodule specs
# ---------------------------------------------------------------------------

@dataclass
class DeepseekV4CompressorSubmodules:
    """Submodules for token-level KV Compressor."""
    linear_wkv: Union[ModuleSpec, type] = None
    linear_wgate: Union[ModuleSpec, type] = None
    norm: Union[ModuleSpec, type] = None


@dataclass
class DeepseekV4IndexerSubmodules:
    """Submodules for Lightning Indexer."""
    linear_wq_b: Union[ModuleSpec, type] = None
    linear_weights_proj: Union[ModuleSpec, type] = None
    compressor: Union[ModuleSpec, type] = None  # Internal Compressor


@dataclass
class DeepseekV4AttentionSubmodules:
    """Submodules for DeepSeek-V4 MLA Attention."""
    linear_q_down_proj: Union[ModuleSpec, type] = None
    q_layernorm: Union[ModuleSpec, type] = None
    linear_q_up_proj: Union[ModuleSpec, type] = None
    linear_kv_proj: Union[ModuleSpec, type] = None
    kv_layernorm: Union[ModuleSpec, type] = None
    core_attention: Union[ModuleSpec, type] = None
    linear_wo_a: Union[ModuleSpec, type] = None
    linear_wo_b: Union[ModuleSpec, type] = None
    compressor: Optional[Union[ModuleSpec, type]] = None
    indexer: Optional[Union[ModuleSpec, type]] = None


# ---------------------------------------------------------------------------
# Compressor
# ---------------------------------------------------------------------------

class DeepseekV4Compressor(MegatronModule):
    """Token-level KV Compressor using gated softmax pooling.

    For CSA layers (compress_ratio == 4), overlap=True doubles the projection
    output dimension (coff=2) and uses overlapping windows to avoid boundary
    artifacts between adjacent chunks.

    Parameters:
        wkv:   Linear hidden_size → coff * kv_dim
        wgate: Gating linear hidden_size → coff * kv_dim
        ape:   Absolute positional embedding [compress_ratio, coff * kv_dim]
        norm:  RMSNorm on kv_dim output
    """

    def __init__(
        self,
        config: TransformerConfig,
        submodules: DeepseekV4CompressorSubmodules,
        compress_ratio: int,
        kv_dim: int,
    ):
        super().__init__(config)
        self.compress_ratio = compress_ratio
        self.kv_dim = kv_dim
        # HF: overlap=True when compress_ratio==4 (CSA); coff doubles projection dim
        self.overlap = (compress_ratio == 4)
        self.coff = 1 + self.overlap
        coff_kv_dim = self.coff * kv_dim

        # HF: wkv/wgate project from hidden_size (4096) → coff * kv_dim
        self.linear_wkv = build_module(
            submodules.linear_wkv,
            config.hidden_size, coff_kv_dim,
            config=config,
            init_method=config.init_method,
            bias=False,
            skip_bias_add=False,
            is_expert=False,
            parallel_mode='duplicated',
            skip_weight_param_allocation=False,
        )
        self.linear_wgate = build_module(
            submodules.linear_wgate,
            config.hidden_size, coff_kv_dim,
            config=config,
            init_method=config.init_method,
            bias=False,
            skip_bias_add=False,
            is_expert=False,
            parallel_mode='duplicated',
            skip_weight_param_allocation=False,
        )
        self.norm = build_module(
            submodules.norm,
            config=config,
            hidden_size=kv_dim,
        )

        # HF: ape shape [compress_ratio, coff * kv_dim] — no extra broadcast dim
        self.ape = nn.Parameter(torch.zeros(compress_ratio, coff_kv_dim))

        # Compress RoPE: apply positional encoding to compressed KV (last qk_rope_head_dim dims)
        # HF uses rope_theta=160000 for compress rotary with YaRN scaling
        # (factor=16, original_max_position_embeddings=65536, beta_fast=32,
        # beta_slow=1, attention_factor=1.0). See U5 in the upstream HEAD diff.
        self.qk_rope_head_dim = config.qk_pos_emb_head_dim  # 64
        inv_freq = _compress_yarn_inv_freq(config, self.qk_rope_head_dim)
        self.register_buffer('compress_inv_freq', inv_freq, persistent=False)

    def _overlap_transform(self, tensor: Tensor, fill: float) -> Tensor:
        """Transform [n_chunks, ratio, batch, 2*kv_dim] → [n_chunks, 2*ratio, batch, kv_dim].

        Each output chunk has 2*ratio slots:
          [ratio:]  ← current chunk's second kv_dim dims  (current context)
          [:ratio]  ← previous chunk's first kv_dim dims  (overlap context)
        First chunk's [:ratio] slots stay at `fill` (no previous chunk).
        """
        n_chunks, ratio, batch, double_d = tensor.shape
        d = double_d // 2
        out = tensor.new_full((n_chunks, 2 * ratio, batch, d), fill)
        out[:, ratio:, :, :] = tensor[:, :, :, d:]       # current chunk (second half of dims)
        out[1:, :ratio, :, :] = tensor[:-1, :, :, :d]    # previous chunk (first half of dims)
        return out

    def forward(self, x: Tensor) -> Optional[Tensor]:
        """Compress hidden states via gated softmax pooling.

        Args:
            x: [seq_len, batch, hidden_size]

        Returns:
            compressed_kv: [n_chunks, batch, kv_dim], or None if seq_len < compress_ratio
        """
        seq_len, batch, _ = x.shape
        ratio = self.compress_ratio
        n_chunks = seq_len // ratio
        if n_chunks == 0:
            return None

        # Truncate tail: drop tokens that don't fill a complete chunk
        x_cut = x[:n_chunks * ratio]  # [n_chunks*ratio, batch, hidden_size]

        # Project: hidden_size → coff * kv_dim
        proj, _ = self.linear_wkv(x_cut)     # [n_chunks*ratio, batch, coff*kv_dim]
        score, _ = self.linear_wgate(x_cut)  # [n_chunks*ratio, batch, coff*kv_dim]

        coff_kv_dim = self.coff * self.kv_dim

        # Reshape to [n_chunks, ratio, batch, coff*kv_dim]
        proj = proj.view(n_chunks, ratio, batch, coff_kv_dim)
        score = score.view(n_chunks, ratio, batch, coff_kv_dim)

        # Add positional embedding: ape [ratio, coff*kv_dim] → [1, ratio, 1, coff*kv_dim]
        score = score + self.ape[None, :, None, :]

        if self.overlap:
            # [n_chunks, ratio, batch, 2*kv_dim] → [n_chunks, 2*ratio, batch, kv_dim]
            proj = self._overlap_transform(proj, fill=0.0)
            score = self._overlap_transform(score, fill=float('-inf'))

        # Softmax pooling over ratio (or 2*ratio) dimension.
        # HF parity: compute softmax in fp32 so small gate differences don't collapse in bf16
        # (modular_deepseek_v4.py DeepseekV4CSACompressor.forward: `new_gate.softmax(dim=2, dtype=torch.float32).to(new_kv.dtype)`).
        kv_pooled = (proj * score.softmax(dim=1, dtype=torch.float32).to(proj.dtype)).sum(dim=1)  # [n_chunks, batch, kv_dim]
        normed = self.norm(kv_pooled)  # [n_chunks, batch, kv_dim]

        # Apply compress RoPE to last qk_rope_head_dim dims (HF: rotary at compress positions)
        # Positions: each chunk represents compress_ratio tokens, so pos = i * compress_ratio
        positions = torch.arange(n_chunks, device=normed.device, dtype=torch.float32) * ratio
        freqs = torch.outer(positions, self.compress_inv_freq)
        cos_c = freqs.cos()[:, None, :]  # [n_chunks, 1, half_rope_dim]
        sin_c = freqs.sin()[:, None, :]  # [n_chunks, 1, half_rope_dim]
        rope_dim = self.qk_rope_head_dim
        kv_nope = normed[..., :-rope_dim]
        kv_rope = normed[..., -rope_dim:]
        kv_rope = DeepseekV4Attention._apply_rotary(kv_rope, cos_c, sin_c)
        return torch.cat([kv_nope, kv_rope], dim=-1)


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

class DeepseekV4Indexer(MegatronModule):
    """Lightning Indexer for sparse KV selection.

    Parameters:
        wq_b: Query projection for index scoring
        weights_proj: Attention weight projection
        compressor: Internal Compressor for KV compression before indexing
    """

    def __init__(
        self,
        config: TransformerConfig,
        submodules: DeepseekV4IndexerSubmodules,
        index_head_dim: int,
        index_n_heads: int,
        index_topk: int,
        q_lora_rank: int,
        kv_dim: int,
        compress_ratio: int,
    ):
        super().__init__(config)
        self.index_head_dim = index_head_dim
        self.index_n_heads = index_n_heads
        self.index_topk = index_topk

        # Q projection for indexing: q_lora_rank -> index_n_heads * index_head_dim
        self.linear_wq_b = build_module(
            submodules.linear_wq_b,
            q_lora_rank, index_n_heads * index_head_dim,
            config=config,
            init_method=config.init_method,
            bias=False,
            skip_bias_add=False,
            is_expert=False,
            parallel_mode='duplicated',
            skip_weight_param_allocation=False,
        )

        # Weight projection: hidden_size -> index_n_heads (HF: weights_proj(dim, n_heads))
        self.linear_weights_proj = build_module(
            submodules.linear_weights_proj,
            config.hidden_size, index_n_heads,
            config=config,
            init_method=config.init_method,
            bias=False,
            skip_bias_add=False,
            is_expert=False,
            parallel_mode='duplicated',
            skip_weight_param_allocation=False,
        )

        # Internal compressor for KV before indexing
        # compress_ratio and kv_dim are already in the ModuleSpec.params
        self.compressor = build_module(
            submodules.compressor,
            config=config,
        )

        # Compress RoPE for indexer queries (same YaRN-scaled config as compressor)
        self.qk_rope_head_dim = config.qk_pos_emb_head_dim  # 64
        inv_freq = _compress_yarn_inv_freq(config, self.qk_rope_head_dim)
        self.register_buffer('compress_inv_freq', inv_freq, persistent=False)

    def forward(self, hidden_states: Tensor, q_compressed: Tensor,
                compressed_kv: Optional[Tensor]) -> Tensor:
        """Compute top-k indices for sparse attention.

        Implements Lightning Indexer scoring (paper eq.13-17):
            c^Q_t  = q_compressed (already computed upstream)
            q^I_t  = c^Q_t · W^IUQ          [wq_b]
            w^I_t  = h_t · W^w               [weights_proj]
            I_{t,s} = Σ_h w^I_{t,h} · ReLU(q^I_{t,h} · K^IComp_s)
            topk_idxs = top-k(I_{t,:})

        Args:
            hidden_states:  [seq_len, batch, hidden_size]
            q_compressed:   [seq_len, batch, q_lora_rank]  (shared with attention Q path)
            compressed_kv:  [n_chunks, batch, index_head_dim] from internal Compressor,
                            or None if seq_len < compress_ratio

        Returns:
            topk_indices: [batch, seq_len, topk]  int32, -1 for invalid (causal pad)
        """
        seq_len, batch, _ = hidden_states.shape

        # --- Indexer queries: q_lora_rank -> n_heads * index_head_dim ---
        # wq_b is ColumnParallel; gather to full dim before use
        iq, _ = self.linear_wq_b(q_compressed)   # [seq_len, batch, n_heads * head_dim]
        if iq.size(-1) != self.index_n_heads * self.index_head_dim:
            from megatron.core.tensor_parallel.mappings import gather_from_tensor_model_parallel_region
            iq = gather_from_tensor_model_parallel_region(iq)
        # [seq_len, batch, n_heads, head_dim]
        iq = iq.view(seq_len, batch, self.index_n_heads, self.index_head_dim)

        # Apply compress RoPE to indexer queries (last qk_rope_head_dim dims)
        # HF: queries get compress RoPE at their actual position_ids
        q_positions = torch.arange(seq_len, device=iq.device, dtype=torch.float32)
        q_freqs = torch.outer(q_positions, self.compress_inv_freq)  # [seq_len, half_rope_dim]
        q_cos = q_freqs.cos()[:, None, None, :]  # [seq_len, 1, 1, half_rope_dim]
        q_sin = q_freqs.sin()[:, None, None, :]  # [seq_len, 1, 1, half_rope_dim]
        rope_dim = self.qk_rope_head_dim
        if self.index_head_dim >= rope_dim:
            iq_nope = iq[..., :-rope_dim]
            iq_rope = iq[..., -rope_dim:]
            iq_rope = DeepseekV4Attention._apply_rotary(iq_rope, q_cos, q_sin)
            iq = torch.cat([iq_nope, iq_rope], dim=-1)

        # --- Per-head weights: hidden_size -> n_heads ---
        iw, _ = self.linear_weights_proj(hidden_states)  # [seq_len, batch, n_heads]

        # --- Internal Compressor for indexer keys ---
        # compressed_kv: [n_chunks, batch, index_head_dim] or None
        if compressed_kv is None:
            # seq too short for any compressed block; return all-invalid indices
            topk = min(self.index_topk, 1)
            indices = torch.full(
                (batch, seq_len, topk), -1,
                dtype=torch.int32, device=hidden_states.device,
            )
            return indices

        n_chunks = compressed_kv.size(0)

        # BF16 indexer expects:
        #   q: [batch, seq_len, n_heads, head_dim]  bfloat16
        #   k: [batch, n_chunks, head_dim]          bfloat16
        #   weights: [seq_len, batch, n_heads]      bfloat16
        iq_b = iq.permute(1, 0, 2, 3).to(torch.bfloat16).contiguous()   # [b, sq, h, d]
        ck_b = compressed_kv.permute(1, 0, 2).to(torch.bfloat16).contiguous()  # [b, n_chunks, d]
        iw_b = iw.to(torch.bfloat16).contiguous()                        # [sq, b, h]

        # I_{t,s} = Σ_h w_h · ReLU(q_h · k_s)
        # (Lightning Indexer BF16 CUDA kernel was removed — kept only the
        # equivalent pure-PyTorch reduction since the kernel was permanently
        # disabled due to a tilelang NestedLoopChecker bug.)
        logits = torch.einsum('bqhd,bsd->bqhs', iq_b.float(), ck_b.float())  # [b,sq,h,nc]
        scores = (torch.relu(logits) * iw_b.permute(1, 0, 2).unsqueeze(-1).float()).sum(dim=2)  # [b,sq,nc]

        # Upstream HF (post-fix) DOES apply per-query causal masking to indexer
        # scores: a query at position t may only attend to compressed chunks
        # whose index w satisfies t >= (w+1) * compress_rate, i.e. w < (t+1)//m.
        # Pre-topk we mask ineligible chunks to -inf; post-topk we replace any
        # picks that still land past the causal threshold with a -1 sentinel so
        # downstream gather/mask can drop them. See upstream
        # modular_deepseek_v4.py DeepseekV4Indexer.forward (SHA a25b8ef).
        compress_rate = self.compressor.compress_ratio
        q_pos = torch.arange(seq_len, device=scores.device)
        causal_threshold = (q_pos + 1) // compress_rate  # [sq]
        entry_idx = torch.arange(n_chunks, device=scores.device)  # [nc]
        future_mask = entry_idx.view(1, 1, -1) >= causal_threshold.view(1, -1, 1)  # [1, sq, nc]
        scores = scores.masked_fill(future_mask, float("-inf"))

        # Top-k selection
        topk = min(self.index_topk, n_chunks)
        _, topk_indices = torch.topk(scores, topk, dim=-1, sorted=False)  # [b, sq, topk]

        # Picks past causal_threshold (e.g. early queries with too few ready blocks,
        # where topk must pad beyond the -inf-masked region) get a -1 sentinel.
        invalid = topk_indices >= causal_threshold.view(1, -1, 1)
        topk_indices = torch.where(
            invalid, torch.full_like(topk_indices, -1), topk_indices
        )

        return topk_indices.to(torch.int32)


# ---------------------------------------------------------------------------
# DeepSeek-V4 Attention
# ---------------------------------------------------------------------------

class DeepseekV4Attention(MegatronModule):
    """DeepSeek-V4 MLA Attention with grouped output projection.

    Architecture:
    - Q: wq_a (down-proj) -> q_norm -> wq_b (up-proj) -> per-head QK-norm
    - KV: wkv (single-stage proj) -> kv_norm -> apply RoPE to last dims
    - Attention: SDPA with sliding-window/CSA/HCA mask depending on layer type
    - Output: wo_a -> wo_b (grouped low-rank output projection)
    - attn_sink: learnable per-head logit bias, applied as an extra zero-value
      KV column with bias-only logits
    """

    def __init__(
        self,
        config: TransformerConfig,
        submodules: DeepseekV4AttentionSubmodules,
        layer_number: int,
        attn_mask_type: AttnMaskType = AttnMaskType.causal,
        attention_type: str = "self",
        attention_dropout: float = None,
        **kwargs,
    ):
        super().__init__(config)
        self.config = config
        self.layer_number = layer_number
        self.attn_mask_type = attn_mask_type

        # Dimensions from config
        self.hidden_size = config.hidden_size
        self.num_heads = config.num_attention_heads
        self.q_lora_rank = config.q_lora_rank
        self.head_dim = config.kv_channels  # V4 unified head_dim = 512
        self.qk_rope_head_dim = config.qk_pos_emb_head_dim  # 64
        self.o_groups = getattr(config, 'o_groups', None) or 8
        self.o_lora_rank = getattr(config, 'o_lora_rank', None) or 1024
        self.qk_layernorm = config.qk_layernorm
        self.layernorm_epsilon = config.layernorm_epsilon
        # Sliding window size: used for SWA layers (ratio=0) and as the local branch
        # of CSA/HCA layers (compressed KV is concatenated in Phase 4).
        # DeepseekV4Config exposes this as `csa_window_size` (default 128);
        # `sliding_window` is NOT a valid field and was silently falling through
        # to the `or 128` default on every config.
        self.window_size = getattr(config, 'csa_window_size', 128)

        # ---- Q path: down-proj -> norm -> up-proj ----
        self.linear_q_down_proj = build_module(
            submodules.linear_q_down_proj,
            self.hidden_size, self.q_lora_rank,
            config=config,
            init_method=config.init_method,
            gather_output=False,
            bias=config.add_bias_linear,
            skip_bias_add=False,
            is_expert=False,
        )

        if self.qk_layernorm:
            self.q_layernorm = build_module(
                submodules.q_layernorm,
                config=config,
                hidden_size=self.q_lora_rank,
            )
        else:
            self.q_layernorm = None

        self.linear_q_up_proj = build_module(
            submodules.linear_q_up_proj,
            self.q_lora_rank, self.num_heads * self.head_dim,
            config=config,
            init_method=config.init_method,
            gather_output=False,
            bias=config.add_bias_linear,
            skip_bias_add=False,
            is_expert=False,
        )

        # ---- KV path: single-stage projection -> norm ----
        self.linear_kv_proj = build_module(
            submodules.linear_kv_proj,
            self.hidden_size, self.head_dim,
            config=config,
            init_method=config.init_method,
            bias=config.add_bias_linear,
            skip_bias_add=False,
            is_expert=False,
            parallel_mode='duplicated',
            skip_weight_param_allocation=False,
        )

        if self.qk_layernorm:
            self.kv_layernorm = build_module(
                submodules.kv_layernorm,
                config=config,
                hidden_size=self.head_dim,
            )
        else:
            self.kv_layernorm = None

        # ---- Core attention ----
        self.core_attention = build_module(
            submodules.core_attention,
            config=config,
            layer_number=layer_number,
            attn_mask_type=attn_mask_type,
            attention_type=attention_type,
            attention_dropout=attention_dropout if attention_dropout is not None else config.attention_dropout,
            softmax_scale=1.0 / (self.head_dim ** 0.5),
            k_channels=self.head_dim,
            v_channels=self.head_dim,
        )

        # ---- Grouped output projection: wo_a -> wo_b ----
        total_head_dim = self.num_heads * self.head_dim
        grouped_intermediate = self.o_groups * self.o_lora_rank
        # HF: wo_a input is total_head_dim // n_groups — block-diagonal, each group sees
        # only its own head slice.  LoongForge stores the full-size dim here so checkpoint
        # conversion does not need special treatment; forward uses an einsum on .weight.
        wo_a_in_dim = total_head_dim // self.o_groups
        self.wo_a_in_dim = wo_a_in_dim
        self.linear_wo_a = build_module(
            submodules.linear_wo_a,
            wo_a_in_dim, grouped_intermediate,
            config=config,
            init_method=config.init_method,
            gather_output=False,
            bias=False,
            skip_bias_add=False,
            is_expert=False,
        )
        self.linear_wo_b = build_module(
            submodules.linear_wo_b,
            grouped_intermediate, self.hidden_size,
            config=config,
            init_method=config.output_layer_init_method,
            bias=config.add_bias_linear,
            input_is_parallel=True,
            skip_bias_add=True,
            is_expert=False,
        )

        # ---- Attention sink: learnable per-head logit bias ----
        # HF applies attn_sink inside its custom sparse_attn CUDA kernel by adding
        # a per-head bias to the softmax denominator. Here we emulate that by
        # appending a zero-valued KV column whose logits are set to local_sinks
        # in the SDPA additive mask (see attention compute below). The parameter
        # is registered for ckpt mapping AND consumed at runtime; do not delete
        # it under the assumption that it's only here for checkpoint compat.
        self.attn_sink = nn.Parameter(torch.zeros(self.num_heads))

        # ---- Optional: Compressor and Indexer ----
        self.has_compressor = submodules.compressor is not None
        self.has_indexer = submodules.indexer is not None

        if self.has_compressor:
            self.compressor = build_module(submodules.compressor, config=config)

        if self.has_indexer:
            self.indexer = build_module(submodules.indexer, config=config)

        # ---- U5: dual rope per layer type ----
        # Upstream HF selects rope per layer_type:
        #   sliding_attention → "main"  (plain θ=rotary_base=10000, no scaling)
        #   CSA/HCA          → "compress" (YaRN, θ=csa_compress_rotary_base=160000,
        #                                  factor=rotary_scaling_factor=16,
        #                                  original_max_position_embeddings=65536,
        #                                  beta_fast=32, beta_slow=1,
        #                                  attention_factor=1.0)
        # In AIAK, CSA/HCA layers are exactly the ones with a compressor, so we
        # key the selection off `self.has_compressor`. Also note: when
        # multi_latent_attention=True, BaseGPTModel skips the external rotary
        # builder, so rotary_pos_emb arrives as None — rope must be owned here.
        if self.qk_rope_head_dim > 0:
            main_inv_freq = _plain_inv_freq(
                float(config.rotary_base), self.qk_rope_head_dim,
            )
            self.register_buffer('main_inv_freq', main_inv_freq, persistent=False)
            compress_inv_freq = _compress_yarn_inv_freq(
                config, self.qk_rope_head_dim,
            )
            self.register_buffer(
                'compress_attn_inv_freq', compress_inv_freq, persistent=False,
            )
        self.rope_layer_type = "compress" if self.has_compressor else "main"

    def forward(
        self,
        hidden_states: Tensor,
        attention_mask: Tensor,
        key_value_states: Tensor = None,
        inference_params=None,
        rotary_pos_emb: Tensor = None,
        packed_seq_params: PackedSeqParams = None,
        **kwargs,
    ):
        """Forward pass for DeepSeek-V4 attention.

        Args:
            hidden_states: [seq_len, batch, hidden_size]
            attention_mask: [batch, 1, seq_len, seq_len]
            rotary_pos_emb: Tuple of (cos, sin) for RoPE

        Returns:
            (output, bias): output [seq_len, batch, hidden_size], bias or None
        """
        seq_len, batch, _ = hidden_states.shape
        tp = parallel_state.get_tensor_model_parallel_world_size()
        local_num_heads = self.num_heads // tp

        # ---- Q path ----

        q_compressed, _ = self.linear_q_down_proj(hidden_states)

        # linear_q_down_proj is ColumnParallelLinear with gather_output=False, so output is
        # sharded to [s, b, q_lora_rank/TP] when TP>1. Gather before q_layernorm to restore
        # [s, b, q_lora_rank], matching Megatron MLA reference (multi_latent_attention.py:854).
        if q_compressed.size(-1) != self.q_lora_rank:
            from megatron.core.tensor_parallel.mappings import gather_from_tensor_model_parallel_region
            q_compressed = gather_from_tensor_model_parallel_region(q_compressed)
            # When ColumnParallelLinear with SP gathers the sequence dimension (s/TP -> s),
            # we must scatter back after the TP feature gather so that q_up_proj receives
            # SP-split input [s/TP, b, q_lora_rank] instead of [s, b, q_lora_rank].
            # Otherwise q_up_proj would re-gather the sequence, producing [s*TP, b, h/TP].
            if self.config.sequence_parallel:
                from megatron.core.tensor_parallel.mappings import scatter_to_sequence_parallel_region
                q_compressed = scatter_to_sequence_parallel_region(q_compressed)

        if self.q_layernorm is not None:
            q_compressed = self.q_layernorm(q_compressed)
        query, _ = self.linear_q_up_proj(q_compressed)
        # TE ColumnParallelLinear with SP gathers the sequence dimension internally,
        # producing [s, b, h/TP]. Scatter back to [s/TP, b, h/TP] for SP consistency.
        if self.config.sequence_parallel:
            from megatron.core.tensor_parallel.mappings import scatter_to_sequence_parallel_region
            query = scatter_to_sequence_parallel_region(query)

        # linear_q_up_proj is ColumnParallel+gather_output=False: output is
        # [seq/TP, batch, local_num_heads * head_dim] where local_num_heads = num_heads // TP

        query = query.reshape(seq_len, batch, local_num_heads, self.head_dim)

        # Per-head QK-norm: q / sqrt(mean(q^2) + eps).  HF parity (modular_deepseek_v4.py
        # DeepseekV4UnweightedRMSNorm.forward): variance & rsqrt computed in fp32, then
        # cast back to the activation dtype.  Doing this in bf16 accumulates ~1% error
        # per layer which compounds across 43 layers.
        q_norm = torch.rsqrt(
            query.float().square().mean(dim=-1, keepdim=True) + self.layernorm_epsilon
        ).to(query.dtype)
        query = query * q_norm

        # ---- Compressor / Indexer ----
        # For CSA/HCA layers: Compressor produces compressed_kv used as long-range KV.
        # Indexer (CSA only) selects top-k compressed KV entries via Lightning Indexer.
        compressed_kv = None
        topk_indices = None
        if self.has_compressor:
            compressed_kv = self.compressor(hidden_states)  # [n_chunks, batch, head_dim] or None
        if self.has_indexer:
            # Internal Compressor inside Indexer produces index keys at index_head_dim.
            # The main compressed_kv (at kv_dim=512) is used for actual attention.
            indexer_compressed_kv = self.indexer.compressor(hidden_states)
            topk_indices = self.indexer(hidden_states, q_compressed, indexer_compressed_kv)  # [b, sq, topk]

        # ---- KV path ----
        kv, _ = self.linear_kv_proj(hidden_states)  # [seq_len, batch, head_dim]
        if self.kv_layernorm is not None:
            kv = self.kv_layernorm(kv)

        # ---- Apply RoPE to last qk_rope_head_dim dims ----
        # U5: build cos/sin internally from the per-layer-type inv_freq buffer
        # (main for SWA layers, compress/YaRN for CSA/HCA layers). Any external
        # `rotary_pos_emb` argument is ignored — with multi_latent_attention=True
        # BaseGPTModel doesn't build one anyway, and we always want the matching
        # per-layer rope for correctness.
        apply_rope = self.qk_rope_head_dim > 0
        cos = sin = None
        if apply_rope:
            rope_dim = self.qk_rope_head_dim
            if self.rope_layer_type == "compress":
                inv_freq = self.compress_attn_inv_freq
            else:
                inv_freq = self.main_inv_freq
            inv_freq = inv_freq.to(device=hidden_states.device, dtype=torch.float32)
            positions = torch.arange(
                seq_len, device=hidden_states.device, dtype=torch.float32,
            )
            freqs = torch.outer(positions, inv_freq)  # [seq_len, rope_dim/2]
            cos = freqs.cos()[:, None, None, :]  # [seq_len, 1, 1, half]
            sin = freqs.sin()[:, None, None, :]

            # Apply to Q rope portion
            q_rope = query[..., -rope_dim:]
            q_rope = self._apply_rotary(q_rope, cos, sin)
            query = torch.cat([query[..., :-rope_dim], q_rope], dim=-1)

            # Apply to KV rope portion (KV is single-head, expand for broadcast)
            kv_rope = kv[..., -rope_dim:]
            kv_rope = self._apply_rotary(kv_rope.unsqueeze(2), cos, sin).squeeze(2)
            kv = torch.cat([kv[..., :-rope_dim], kv_rope], dim=-1)

        # ---- Core attention format ----
        # DotProductAttention expects sbhd / thd layouts.
        qkv_format = getattr(packed_seq_params, 'qkv_format', 'sbhd') if packed_seq_params is not None else 'sbhd'

        # ---- Build sliding-window local KV ----
        # CSA/HCA layers use full local KV (window mask is built later via
        # `win_valid` in the SDPA path); SWA layers also pass full KV here and
        # build their own sliding-window causal mask in the SDPA path.
        win = self.window_size
        kv_win = kv

        # ---- Attention compute: standard SDPA path ----
        # The sparse_mla CUDA kernel branch was removed because the sparse_mla
        # backward kernel expects d_qk=576 while V4 uses d=512, AND the kernel is
        # only built for SM100; CSA/HCA layers therefore compute via SDPA over
        # the concatenation [kv_win, compressed_kv] using a per-query causal +
        # window-aware mask. This also keeps CSA/HCA differentiable end-to-end.
        # For CSA/HCA layers (has_compressor=True), concatenate window KV with compressed KV
        # and build appropriate mask. For SWA layers, just use sliding window.
        if self.has_compressor and compressed_kv is not None:
            # CSA/HCA layer: combine window KV + compressed KV
            # Window KV: kv_win [win, batch, head_dim] (last win tokens)
            # Compressed KV: compressed_kv [n_comp, batch, head_dim]
            n_comp = compressed_kv.shape[0]
            n_win = kv_win.shape[0]  # min(win, seq_len)
            # Concatenate: [n_win + n_comp, batch, head_dim]
            combined_kv = torch.cat([kv_win, compressed_kv], dim=0)
            skv = n_win + n_comp
            # Build attention mask [1, 1, sq, skv]
            # First n_win positions are window KV (global pos = seq_len-n_win .. seq_len-1)
            # Next n_comp positions are compressed chunks (chunk c = tokens [c*ratio, (c+1)*ratio))
            # For query at global pos i:
            #   Window key j (global pos = seq_len - n_win + j): attend if in [i-win+1, i]
            #   Compressed chunk c: attend if (c+1)*ratio <= i (chunk fully in past)
            compress_ratio = self.compressor.compress_ratio
            q_pos = torch.arange(seq_len, device=hidden_states.device)  # [sq]
            # Window mask: [sq, n_win]
            # global pos of window keys
            win_glob = (seq_len - n_win) + torch.arange(
                n_win, device=hidden_states.device
            )
            win_valid = (
                (q_pos.unsqueeze(1) >= win_glob.unsqueeze(0))
                & (q_pos.unsqueeze(1) - win_glob.unsqueeze(0) < win)
            )  # causal + window
            # Compressed mask: [sq, n_comp] — upstream HF (post-fix) enforces
            # per-query causality on compressed chunks: query at global pos t
            # may attend to compressed chunk c iff (c+1)*compress_rate <= t,
            # i.e. c < (t+1)//compress_rate. Previously we set this to all-True
            # which leaked future compressed state into every query. See
            # upstream modular_deepseek_v4.py HCACompressor / CSACompressor
            # (SHA a25b8ef) for the block_bias definition.
            comp_pos = torch.arange(n_comp, device=hidden_states.device)
            causal_threshold_comp = (q_pos + 1) // compress_ratio  # [sq]
            comp_valid = comp_pos.unsqueeze(0) < causal_threshold_comp.unsqueeze(1)  # [sq, n_comp]
            # If indexer provided topk_indices, only attend to selected chunks
            if topk_indices is not None:
                # topk_indices: [batch, sq, topk] - which compressed chunks each query attends to
                # Build per-query sparse mask for compressed positions
                # For simplicity with SDPA, convert topk to dense mask
                comp_mask_dense = torch.zeros(batch, seq_len, n_comp, dtype=torch.bool, device=hidden_states.device)
                for b_idx in range(batch):
                    idx = topk_indices[b_idx]  # [sq, topk]
                    valid = (idx >= 0) & (idx < n_comp)
                    # Scatter valid indices
                    for t in range(seq_len):
                        valid_idx = idx[t][valid[t]]
                        if valid_idx.numel() > 0:
                            comp_mask_dense[b_idx, t, valid_idx.long()] = True
                # Combine with causal: must be both causally valid AND selected by indexer
                comp_valid = comp_valid.unsqueeze(0) & comp_mask_dense  # [batch, sq, n_comp]
                # Combined mask: [batch, sq, n_win + n_comp]
                win_valid_exp = win_valid.unsqueeze(0).expand(batch, -1, -1)  # [batch, sq, n_win]
                combined_mask = torch.cat([win_valid_exp, comp_valid], dim=2)  # [batch, sq, skv]
                attn_mask_for_call = combined_mask.unsqueeze(1)  # [batch, 1, sq, skv]
            else:
                # HCA: attend to all causally valid compressed chunks
                combined_mask = torch.cat([win_valid, comp_valid], dim=1)  # [sq, skv]
                attn_mask_for_call = combined_mask.unsqueeze(0).unsqueeze(0)  # [1, 1, sq, skv]
            key   = combined_kv.unsqueeze(2)   # [skv, batch, 1, head_dim]
            value = key.clone()
        else:
            # SWA layers: use full kv with sliding window mask
            if seq_len > win:
                q_idx  = torch.arange(seq_len, device=hidden_states.device).unsqueeze(1)
                k_idx  = torch.arange(seq_len, device=hidden_states.device).unsqueeze(0)
                dist   = q_idx - k_idx
                sw_mask_sq = ((dist >= 0) & (dist < win)).unsqueeze(0).unsqueeze(0)  # [1,1,sq,sq]
                attn_mask_for_call = sw_mask_sq
            else:
                attn_mask_for_call = attention_mask
            key   = kv.unsqueeze(2)   # [seq_len, batch, 1, head_dim]
            value = key.clone()       # same shape

        if qkv_format == 'thd':
            query_3d = query.reshape(-1, query.shape[2], query.shape[3])
            key_3d   = key.reshape(-1, key.shape[2], key.shape[3])
            value_3d = value.reshape(-1, value.shape[2], key.shape[3])
            # Expand KV heads for GQA: [n_tok, 1, head_dim] -> [n_tok, local_num_heads, head_dim]
            key_3d   = key_3d.expand(-1, local_num_heads, -1)
            value_3d = value_3d.expand(-1, local_num_heads, -1)
            # SDPA expects [batch, n_heads, seq, head_dim]
            q_sdpa = query_3d.transpose(0, 1).unsqueeze(0)   # [1, local_num_heads, n_tok, head_dim]
            k_sdpa = key_3d.transpose(0, 1).unsqueeze(0)
            v_sdpa = value_3d.transpose(0, 1).unsqueeze(0)
            attn_output = torch.nn.functional.scaled_dot_product_attention(
                q_sdpa, k_sdpa, v_sdpa, attn_mask=attention_mask,
            )
            attn_output = attn_output.squeeze(0).transpose(0, 1)  # [n_tok, local_num_heads, head_dim]
            attn_output = attn_output.reshape(attn_output.shape[0], -1)
        else:
            # Expand KV heads for GQA: [s, b, 1, d] -> [s, b, local_num_heads, d]
            key   = key.expand(-1, -1, local_num_heads, -1).contiguous()
            value = value.expand(-1, -1, local_num_heads, -1).contiguous()
            # SDPA with attention sink via dummy KV position
            q_sdpa = query.permute(1, 2, 0, 3).contiguous()   # [b, h, sq, d]
            k_sdpa = key.permute(1, 2, 0, 3).contiguous()     # [b, h, skv, d]
            v_sdpa = value.permute(1, 2, 0, 3).contiguous()   # [b, h, skv, d]
            # Add dummy zero-KV entry for sink (value=0 so it absorbs prob mass without contributing)
            sink_k = torch.zeros(batch, local_num_heads, 1, self.head_dim, dtype=k_sdpa.dtype, device=k_sdpa.device)
            sink_v = torch.zeros(batch, local_num_heads, 1, self.head_dim, dtype=v_sdpa.dtype, device=v_sdpa.device)
            k_sdpa = torch.cat([k_sdpa, sink_k], dim=2)  # [b, h, skv+1, d]
            v_sdpa = torch.cat([v_sdpa, sink_v], dim=2)  # [b, h, skv+1, d]
            # Build mask including sink position
            is_causal = (attn_mask_for_call is None or attn_mask_for_call is attention_mask)
            tp_rank = parallel_state.get_tensor_model_parallel_rank()
            local_sinks = self.attn_sink[tp_rank * local_num_heads:(tp_rank + 1) * local_num_heads]
            if not is_causal and attn_mask_for_call is not None:
                # attn_mask_for_call: True=attend, False=block -> additive mask
                sdpa_mask = torch.zeros(
                    batch, local_num_heads, q_sdpa.shape[2], k_sdpa.shape[2],
                    dtype=q_sdpa.dtype, device=q_sdpa.device,
                )
                # Existing KV mask (without sink column)
                sdpa_mask[..., :-1] = sdpa_mask[..., :-1].masked_fill(
                    ~attn_mask_for_call, float('-inf')
                )
                # Sink column: set to sink logit value (always visible, per-head bias)
                sdpa_mask[..., -1:] = local_sinks.reshape(
                    1, local_num_heads, 1, 1
                ).expand(batch, -1, q_sdpa.shape[2], 1)
            elif is_causal:
                # Build full causal mask + sink column
                sq_len = q_sdpa.shape[2]
                skv_len = k_sdpa.shape[2]  # includes sink
                sdpa_mask = torch.zeros(
                    batch, local_num_heads, sq_len, skv_len,
                    dtype=q_sdpa.dtype, device=q_sdpa.device,
                )
                # Causal for original KV positions
                causal_mask = torch.ones(
                    sq_len, skv_len - 1,
                    dtype=torch.bool, device=q_sdpa.device,
                ).triu(diagonal=(skv_len - 1) - sq_len + 1)
                sdpa_mask[..., :-1] = sdpa_mask[..., :-1].masked_fill(
                    causal_mask.unsqueeze(0).unsqueeze(0), float('-inf')
                )
                # Sink column always visible with per-head bias
                sdpa_mask[..., -1:] = local_sinks.reshape(
                    1, local_num_heads, 1, 1
                ).expand(batch, -1, sq_len, 1)
            else:
                # No mask case: just sink bias
                sq_len = q_sdpa.shape[2]
                skv_len = k_sdpa.shape[2]
                sdpa_mask = torch.zeros(
                    batch, local_num_heads, sq_len, skv_len,
                    dtype=q_sdpa.dtype, device=q_sdpa.device,
                )
                sdpa_mask[..., -1:] = local_sinks.reshape(
                    1, local_num_heads, 1, 1
                ).expand(batch, -1, sq_len, 1)
            attn_output = torch.nn.functional.scaled_dot_product_attention(
                q_sdpa, k_sdpa, v_sdpa,
                attn_mask=sdpa_mask,
                is_causal=False,  # we handle causality in the mask
            )
            # Remove contribution of sink position from output (it's zero-valued, so no-op)
            attn_output = attn_output.permute(2, 0, 1, 3).contiguous()  # [s, b, h, d]
            attn_output = attn_output.reshape(seq_len, batch, -1)

        # ---- Inverse RoPE on attention output ----
        # De-rotate the last rope_dim dims of the output to remove absolute position encoding
        # carried by the value vectors (HF: apply_rotary_emb(o[..., -rd:], freqs_cis, inverse=True)).
        if apply_rope:
            rope_dim = self.qk_rope_head_dim
            if qkv_format == 'thd':
                n_tok = attn_output.shape[0]
                attn_out_4d = attn_output.view(n_tok, local_num_heads, self.head_dim)
                o_rope = self._apply_rotary(attn_out_4d[..., -rope_dim:], cos, sin, inverse=True)
                attn_output = torch.cat([attn_out_4d[..., :-rope_dim], o_rope], dim=-1).view(n_tok, -1)
            else:
                attn_out_4d = attn_output.view(seq_len, batch, local_num_heads, self.head_dim)
                o_rope = self._apply_rotary(attn_out_4d[..., -rope_dim:], cos, sin, inverse=True)
                attn_output = torch.cat([attn_out_4d[..., :-rope_dim], o_rope], dim=-1).view(seq_len, batch, -1)

        # ---- Grouped output projection ----
        # HF: o.view(b,s,n_groups,-1) then einsum with wo_a.weight reshaped to
        # [n_groups, o_lora_rank, per_group_dim] — block-diagonal, group g operates
        # only on heads g*(n_heads//n_groups) .. (g+1)*(n_heads//n_groups).
        # Under TP, linear_wo_a is ColumnParallel: weight is sharded on output dim
        # (o_groups * o_lora_rank / TP rows). local_o_groups and local_o_lora_rank
        # correspond to the per-TP-rank slice.
        wo_a_in = self.wo_a_in_dim  # (num_heads // o_groups) * head_dim  — full, not TP-split
        local_grouped_intermediate = self.linear_wo_a.weight.shape[0]  # o_groups*o_lora_rank / TP
        # Determine local o_groups and o_lora_rank from actual weight shape.
        # Keep it simple: factor as (local_o_groups, o_lora_rank) where
        # local_o_groups = local_grouped_intermediate // o_lora_rank.
        local_o_lora_rank = self.o_lora_rank
        local_o_groups = local_grouped_intermediate // local_o_lora_rank
        wo_a_weight = self.linear_wo_a.weight
        if hasattr(wo_a_weight, 'dequantize'):
            wo_a_weight = wo_a_weight.dequantize()
        # Cast to activation dtype so einsum below works under recompute without autocast
        # (e.g. FP8-off bf16 path where the raw weight may be fp32 master).
        wo_a_weight = wo_a_weight.to(attn_output.dtype)
        wo_a_w = wo_a_weight.view(local_o_groups, local_o_lora_rank, wo_a_in)
        if qkv_format == 'thd':
            n_tok = attn_output.shape[0]
            o_grouped = attn_output.view(n_tok, local_o_groups, wo_a_in)
            wo_a_output = torch.einsum("tgd,grd->tgr", o_grouped, wo_a_w).flatten(1)
        else:
            o_grouped = attn_output.view(seq_len, batch, local_o_groups, wo_a_in)
            wo_a_output = torch.einsum("sbgd,grd->sbgr", o_grouped, wo_a_w).flatten(2)
        # linear_wo_b is RowParallelLinear with input_is_parallel=True and SP.
        # It internally scatters the sequence dim on output (s -> s/TP).
        # But wo_a_output already has seq_len=s/TP because the grouped einsum
        # bypasses TE's ColumnParallelLinear (which would have gathered s).
        # Gather s/TP -> s so that the subsequent SP scatter gives s/TP back.
        if self.config.sequence_parallel:
            from megatron.core.tensor_parallel.mappings import gather_from_sequence_parallel_region
            wo_a_output = gather_from_sequence_parallel_region(wo_a_output)
        output, output_bias = self.linear_wo_b(wo_a_output)

        return output, output_bias

    @staticmethod
    def _apply_rotary(x: Tensor, cos: Tensor, sin: Tensor, inverse: bool = False) -> Tensor:
        """Apply (or invert) interleaved rotary position embedding (V4 style).

        V4 uses interleaved RoPE: consecutive pairs (0,1), (2,3), ... share a
        rotation frequency.  cos/sin from Megatron's RotaryEmbedding are
        half-sized (one entry per pair); we expand via repeat_interleave(2)
        before applying the interleaved rotate_half.

        Args:
            x: [..., rope_dim]
            cos, sin: broadcastable rotary embeddings (half-sized or full-sized)
            inverse: if True, apply conjugate rotation (de-rotate); used on attn output
        """
        rope_dim = x.shape[-1]

        # Expand half-sized cos/sin (one per pair) to full rope_dim via
        # repeat_interleave, matching HF's  cos.repeat_interleave(2, dim=-1).
        if cos.shape[-1] * 2 == rope_dim:
            cos = cos.repeat_interleave(2, dim=-1)
            sin = sin.repeat_interleave(2, dim=-1)
        elif cos.shape[-1] > rope_dim:
            # Trim if somehow larger
            cos = cos[..., :rope_dim]
            sin = sin[..., :rope_dim]

        if inverse:
            sin = -sin  # Conjugate rotation: pass -sin (HF: apply_rotary_pos_emb(o, cos, -sin))

        # Interleaved rotate_half: pairs (0,1), (2,3), ...
        # rotate_half(x)[2i]   = -x[2i+1]
        # rotate_half(x)[2i+1] =  x[2i]
        x_even = x[..., 0::2]
        x_odd  = x[..., 1::2]
        rotated = torch.stack((-x_odd, x_even), dim=-1).flatten(-2)

        return (x.float() * cos + rotated.float() * sin).to(x.dtype)
