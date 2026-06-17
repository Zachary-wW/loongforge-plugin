# LoongForge Perf Rules Reference

Version: v0.1 (draft, batch 1)
Purpose: Static perf/memory rules applied **after** R001-R021 pass.
Scope: Hot path of generated `_attention.py`, `_model.py`, `_layer_spec.py`,
       and any new module file produced via `new_impl` / `wrap_megatron`.
Status model: every rule has a status field — `draft` / `warn-only` / `enforced`.
       The reviewer reads the status and refuses to upgrade severity above what
       the rule's own status allows.

> P-series rules **do not replace** R-series. R is "does it run?"; P is "does it
> run well?". A file that passes R001-R021 can still trip P-series.

## Provenance requirement

Every rule below includes a `Provenance` block. New rules MAY NOT be merged
without a `Provenance.observed_in` entry pointing at a real generated file
(commit + line range) and a `Provenance.fix_evidence` entry showing a known-
good replacement (commit + line range, or recipe path).

## Status promotion gate

| from → to | Required evidence |
|---|---|
| draft → warn-only | corpus dry-run: 0 FAIL across known-good files |
| warn-only → enforced | corpus dry-run: 0 FAIL; ≥3 real adapt runs flagged this rule with ≥1 confirmed-true positive; static finding can be corroborated by Step 7c probe (when applicable) |

The reviewer SHALL NOT raise severity above what `status` permits, regardless
of how confident the static check is.

---

## Rules Quick Reference

| ID | Status | Applicable Files | Check | Default Severity |
|----|--------|-----------------|-------|------------------|
| P001 | draft | `*_model.py` | LM-head logits in CE path must be chunked when `vocab_size > 32K` | FAIL |
| P002 | draft | `*_model.py`, `*_attention.py` | Activations declared in `scale_signature.activations` must reach a chunk/offload primitive when `scales_with` includes `seq_len^2` or `seq_len*expert_num` | FAIL |
| P003 | draft | `*_attention.py` | MLA latent_kv / MTP-branch / sparse-attention activations must not be materialised in full when `scale_signature` flags them | FAIL |
| P004 | draft | hot path of any generated `.py` | Two nested Python `for` loops driving tensor ops (excluding well-known vectorised loops: layer index, expert index in routed MoE Megatron path) | FAIL |
| P005 | draft | hot path | `value = key.clone()` / unconditional `.clone()` of K or V where the model unifies V==K | FAIL |
| P006 | draft | hot path | Redundant `.contiguous()` / `.clone()` / `.to(dtype)` chain on the same tensor; `.item()` / `.cpu()` / `.numpy()` / `.tolist()` on activations | WARN |
| P007 | draft | hot path | Repeated `torch.cat` / `torch.stack` building a list inside a loop; per-forward fresh allocation of buffers that could be cached | WARN |
| P008 | draft | hot path | Hand-written RMSNorm / SwiGLU / SDPA / softmax-then-matmul when `multiacc_modules` exposes a fused equivalent | WARN |
| P009 | draft | hot path | Bare `nn.Linear` + manual `all_reduce` where a `Column/RowParallelLinear` would express the same and integrate with TP/SP | FAIL |
| P010 | draft | hot path | Component is in `model_spec.special_features.large_activation: true` but no recompute hint and no chunk primitive applied | WARN |
| P011 | draft | hot path | KV / mask / score tensors materialised at full `[b, h, sq, skv]` when a broadcast view, GQA flag, or sparse path exists | FAIL |
| P012 | draft | hot path | Attention sink / per-head bias implemented via extra KV column (`torch.cat`-ing zero K/V) or via additive mask sized to full skv | FAIL |
| P013 | draft | hot path | `.dequantize()` on a `Linear.weight` inside forward (defeats FP8 GEMM) | FAIL |
| P014 | draft | hot path | `torch.einsum` / matmul reading `.weight` of a `ColumnParallelLinear` / `RowParallelLinear` directly (bypasses TE GEMM, FP8, autocast, TP overlap) | FAIL |
| P015 | draft | hot path | RoPE `inv_freq → cos/sin` recomputed inside forward instead of cached (buffer or Megatron `RotaryEmbedding`) | WARN |

---

## Rule Details

### P001 — LM-head logits must be chunked when vocab is large

- **Trigger**: file matches `*_model.py`; AST contains `Linear(...) @ ...`-style
  call producing a tensor whose final dim equals `vocab_size`, followed by a
  `cross_entropy` / loss site, AND `vocab_size > 32K` per `model_spec.yaml`.
- **Why**: Materialising `[b, sq, vocab]` logits in fp32 dominates LM training
  memory at long context.
- **Fix**: enable `--cross-entropy-loss-fusion --cross-entropy-fusion-impl linear`
  (Megatron fused linear CE), or apply chunked CE.

```python
# Bad — full logits materialised
logits = self.lm_head(hidden)                      # [b, s, V]
loss = F.cross_entropy(logits.view(-1, V), labels.view(-1))

# Good — fused linear CE owns the chunking
loss = fused_linear_cross_entropy(hidden, self.lm_head.weight, labels)
```

**Provenance**:
- `observed_in: <pending — corpus scan>`
- `fix_evidence: loongforge/models/foundation/<corpus>/...` (to be filled at
  rule promotion)

---

### P002 / P003 — Scale-signature-driven materialisation check

- **Trigger**: the component has a `structural_tag` whose
  `knowledge_base/scale_signatures/<tag>.yaml` declares an activation with
  `scales_with` containing one of `seq_len^2`, `seq_len*expert_num`,
  `seq_len*n_chunks`. Reviewer scans the file for tensor allocations whose
  shape matches that activation pattern AND no chunk / sparse / offload
  primitive applied.
- **Fix direction**: see the `fix_recipe` field of the matched signature.

P002 covers MoE / large-vocab / hybrid layers. P003 covers MLA / sparse-MLA /
MTP. They share the engine; the split is for severity tuning.

**Provenance**:
- DS V4 attention witness, lines 442-443 (indexer logits einsum) — see
  `eval/witnesses/deepseek_v4_flash/expected_perf_findings.yml#A1`.

---

### P004 — Nested Python `for` driving tensor ops

- **Trigger**: AST contains a `for` whose body contains another `for` whose body
  contains a `Subscript`/`Call` writing to a tensor (not iterating
  `range(num_layers)` / `for expert in ...` over a Megatron-vectorised path).
- **Allowed exceptions**: top-level layer construction loops in `__init__`,
  expert-loop in MoE _init_, recipe-listed legitimate cases.

```python
# Bad
for b in range(batch):
    for t in range(seq_len):
        mask[b, t, idx[b, t]] = True

# Good
mask.scatter_(2, idx, True)
```

**Provenance**:
- DS V4 attention witness, lines 837-844 — `expected_perf_findings.yml#B1`.

---

### P005 — Don't clone K to make V when V==K

```python
# Bad
key = kv.unsqueeze(2)
value = key.clone()                          # doubles KV memory

# Good
key = value = kv.unsqueeze(2)
# or pass the same tensor as both args to SDPA
```

**Provenance**:
- DS V4 attention witness, lines 856 / 868 — `expected_perf_findings.yml#A5`.

---

### P006 — Redundant op chains in hot path

- `.contiguous()` immediately after a no-op layout change
- `.to(dtype)` on the same tensor more than once between two ops
- `.permute(...).contiguous()` chains repeated for Q/K/V when the kernel can
  take the original layout
- `.item()` / `.cpu()` / `.numpy()` / `.tolist()` on any tensor reachable from
  forward (causes host sync)

```python
# Bad
q_sdpa = query.permute(1, 2, 0, 3).contiguous()
k_sdpa = key.permute(1, 2, 0, 3).contiguous()
v_sdpa = value.permute(1, 2, 0, 3).contiguous()

# Good — choose a layout once and stick with it; let SDPA take sbhd if it can
```

**Provenance**:
- DS V4 attention witness, lines 891-893 — `expected_perf_findings.yml#B2`,
  L434-442 (`#B8`), L988-991 (`#B4`).

---

### P007 — Allocation in loop / per-forward fresh buffers

- `torch.cat([...])` or `torch.stack([...])` over a list grown by `append` in a
  loop
- `tensor.new_full(...)` / `torch.zeros(...)` allocated each forward for a
  shape that could be precomputed at init or cached in a buffer

**Provenance**:
- DS V4 attention witness, lines 241-246 (`_overlap_transform`) —
  `expected_perf_findings.yml#A7`.

---

### P008 — Use fused primitives when available

- Hand-written RMSNorm when `multiacc_modules.RMSNorm` / `TENorm` exists
- Hand-written SwiGLU when `multiacc_modules` exposes a fused MLP
- Manual `softmax(qk/sqrt(d)) @ v` instead of SDPA
- Manual `dropout` after attention when SDPA does it

---

### P009 — Don't bypass TP-aware linears

```python
# Bad
self.proj = nn.Linear(...)
out = self.proj(x)
torch.distributed.all_reduce(out, group=tp_group)

# Good
self.proj = ColumnParallelLinear(...)        # or RowParallelLinear
out, _ = self.proj(x)
```

---

### P010 — Recompute hint required for large activations

- **Trigger**: component's `structural_tags` ∈ {`mla`, `moe`,
  `sparse_attention`, `mtp`, `large_vocab`} AND the generated module does not
  declare a `recompute_modules` candidate name AND no fine-grained offload tag.
- **Why**: Phase 4 selective-recompute / offload rows can't reach the
  activation if it isn't named.

---

### P011 — Mask / KV / score tensors must not be materialised at full size

- **Trigger** examples:
  - `[b, h, sq, skv]` additive mask in activation dtype
  - `.expand(...).contiguous()` on K / V to fan out to per-head copies (use
    `enable_gqa=True` in SDPA, or pass broadcasted view)
  - dense `[b, sq, n_comp]` mask built from sparse top-k indices

```python
# Bad
key = key.expand(-1, -1, local_num_heads, -1).contiguous()
sdpa_mask = torch.zeros(b, h, sq, skv, dtype=q.dtype, device=q.device)
# ... fill with -inf / bias ...

# Good
attn_out = F.scaled_dot_product_attention(
    q, k, v,                # k, v are single-head broadcast views
    attn_mask=compact_mask, # [1, 1, sq, skv] or None with is_causal=True
    enable_gqa=True,
    is_causal=True,
)
```

**Provenance**:
- DS V4 attention witness — `expected_perf_findings.yml#A2 #A3 #A4`.

---

### P012 — Attention sink / per-head bias must be a logit bias, not a KV column

```python
# Bad
sink_k = torch.zeros(b, h, 1, d, dtype=k.dtype, device=k.device)
sink_v = torch.zeros(b, h, 1, d, dtype=v.dtype, device=v.device)
k = torch.cat([k, sink_k], dim=2)            # extends sequence; reallocates
v = torch.cat([v, sink_v], dim=2)
# ... and then add per-head bias on the sink column of an additive mask ...

# Good
# Add the per-head sink term to attention logits / softmax denominator via
# Megatron's TEDotProductAttention sink-token API or an additive scalar bias.
```

**Provenance**:
- DS V4 attention witness, lines 895-947 — `expected_perf_findings.yml#A6 #A3`.

---

### P013 — No `.dequantize()` in forward

- **Trigger**: any call to `.dequantize()` on a parameter / weight inside a
  function reachable from forward.
- **Why**: nullifies FP8 GEMM. If you can't use the FP8 GEMM directly, the
  module should not be FP8.

**Provenance**:
- DS V4 attention witness, line 988 — `expected_perf_findings.yml#B3`.

---

### P014 — Don't matmul on `.weight` of a TP linear directly

- **Trigger**: `torch.einsum(..., <linear>.weight, ...)` /
  `torch.matmul(<linear>.weight, ...)` / `<linear>.weight @ ...` where
  `<linear>` is a `ColumnParallelLinear`, `RowParallelLinear`, or any TE
  variant.
- **Why**: bypasses TE GEMM (loses FP8), bypasses autocast, bypasses TP comm
  overlap, bypasses gradient bucketing, makes weight conversion fragile.
- **Fix**: express the operation as a normal Linear call (reshape inputs as
  needed) or use `wrap_megatron` to subclass with the desired math.

**Provenance**:
- DS V4 attention witness, lines 996-999 — `expected_perf_findings.yml#B5`.

---

### P015 — RoPE `inv_freq` / `cos` / `sin` must be cached

- **Trigger**: `torch.outer(positions, inv_freq)` / `freqs.cos()` /
  `freqs.sin()` called inside forward (transitively).
- **Allowed**: precompute up to `max_position_embeddings` in a buffer at
  `__init__`; or use Megatron's `RotaryEmbedding` and pass `rotary_pos_emb`.

**Provenance**:
- DS V4 attention witness, lines 292 / 403 / 759 —
  `expected_perf_findings.yml#B6`.

---

## Reviewer integration (informational)

`code-review/SKILL.md` is updated to:

1. After R001-R021 pass, run a P-series pass.
2. For each rule whose `status == draft`, emit at most `INFO`.
3. For each rule whose `status == warn-only`, cap severity at `WARN`.
4. For `enforced`, emit declared severity.
5. When `Step 7c` (dynamic probe) artefact is present, cross-check:
   - if a `FAIL` finding's `needs_dynamic_corroboration_for_enforced: true` and
     no matching `top_tensor` slot is reported, demote to `WARN`.
   - if a `WARN` finding has matching `top_tensor` over threshold, it MAY
     promote to `FAIL` only if the rule's status is `enforced`.

This is described informationally here; the actual handshake schema lives in
`references/tools/perf-reviewer/SKILL.md` (batch 2) and
`references/tools/perf-probe/SKILL.md` (batch 3).

---

## What this file is NOT

- Not a replacement for Phase 3 loss-diff (numerical correctness).
- Not a profiler — performance numbers come from `perf-probe`.
- Not a Megatron-internal review — only reviews generated model code.

For Megatron-side bug-fixes, follow `feedback_megatron_modification_policy`:
keep model-specific perf workarounds in Omni; touch shared Megatron only with
explicit framework-bugfix authorisation.
