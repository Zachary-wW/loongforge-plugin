# Phase 1 Step 7 Forward Debug Manual

> For use by Phase 1 Step 7b/7c. Includes: PHASE1_VERIFY hook, error classification, code self-check checklist, tensor dump.

---

## PHASE1_VERIFY Hook

Injected into the `forward()` entry of `<family>_model.py` to fix inputs for reproducible forward comparison:

```python
def forward(self, input_ids, ...):
    # PHASE1_VERIFY: fix inputs for Step 7 forward comparison
    import os as _os
    if _os.environ.get("OMNI_PHASE1_VERIFY"):
        import torch as _torch
        input_ids = _torch.arange(
            100, 100 + input_ids.shape[-1],
            dtype=_torch.long, device=input_ids.device,
        ).unsqueeze(0)
    # ... original forward logic
```

---

## Error Classification Table (Step 7b)

| Error Type | Log Signature | Fix Direction |
|-----------|--------------|---------------|
| RuntimeError / crash | traceback | Locate error line -> fix `_model.py` or `_layer_spec.py` |
| ImportError | `ModuleNotFoundError` / `cannot import` | Check `__init__.py` exports and import paths |
| Shape mismatch | `size mismatch` / `Expected ... got ...` | Check config field mapping (hidden_size / head_dim / kv_channels) |
| Loss precision exceeds threshold (`abs_diff >= 1e-2`) | `abs_diff = X.XX` | Code self-check first (checklist below); if inconclusive, then tensor dump |
| NaN / Inf loss | `loss = nan` / `loss = inf` | Check layernorm epsilon / embedding initialization / vocab_size |
| Omni no output | Log is empty / process exit code non-zero | Check whether `--mock-data` / `--train-iters 1` are effective |

---

## Code Self-Check Checklist (Step 7c, preferred when precision exceeds threshold)

Compare against the HF implementation by reading the `hf_file / hf_line` of the component in `model_spec.yaml`:

1. `head_dim`: Does HF use `hidden_size // num_heads` or is it explicitly specified in config? Is Omni `kv_channels` consistent?
2. `rope_theta / rotary_base`: Is the HF config.json value consistent with Omni YAML `rotary_base`?
3. `add_qkv_bias`: Is HF `attention_bias` mapped to Omni `add_qkv_bias`?
4. Attention mask: Does HF forward have special mask logic?
5. `position_ids`: Does HF explicitly construct them?
6. YAML values: Verify `num_layers / hidden_size / ffn_hidden_size / vocab_size` one by one (see `schema/HF_OMNI_FIELD_MAP.md`)
7. `reuse_megatron` components: Are the field names passed from layer_spec to Megatron modules consistent with Megatron's interface?
8. `wrap_megatron` components: Is the output shape of overridden methods consistent with what the base class expects?

---

## Tensor Dump (fallback when code self-check cannot pinpoint, after Step 7c)

```python
def dump(name, t):
    print(f"[DUMP][{name}] shape={t.shape} "
          f"mean={t.float().mean():.6f} std={t.float().std():.6f}")
```

Starting from the embedding output, dump layer by layer forward, find the first diverging layer, then narrow the granularity within that layer. After fixing, delete all dump code.
