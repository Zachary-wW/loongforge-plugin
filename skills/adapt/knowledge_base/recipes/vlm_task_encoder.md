# VLM Task Encoder Generation Decision

> For use by Phase 1 Step 3f (VLM). Determines whether a new Task Encoder and Plugin need to be created.

---

## Baseline Implementation

`loongforge/data/multimodal/vlm_task_encoder.py` -> `VLMTaskEncoder`
(covers standard formats for Qwen2-VL / Qwen2.5-VL / Qwen3-VL series)

---

## Four-Dimensional Difference Comparison

| Dimension | Baseline (VLMTaskEncoder) | If Customization Needed |
|-----------|--------------------------|------------------------|
| 1. Image token placeholder | `<\|image_pad\|>`, wrapped with `<\|vision_start\|>...<\|vision_end\|>` | Define new `IMAGE_TOKEN / IMAGE_TOKEN_WITH_TAGS` constants |
| 2. Video token placeholder | `<\|video_pad\|>`, same as above | Define new `VIDEO_TOKEN / VIDEO_TOKEN_WITH_TAGS` constants |
| 3. Chat template token | No special im_user/im_end tokens | If the model has a dedicated chat template, override `_build_conversation()` |
| 4. Token expansion logic | Single placeholder corresponds to a fixed number of tokens (grid_thw calculation) | If placeholder semantics differ, override `_expand_media_tokens()` |

---

## Generation Decision

- All four dimensions match the baseline -> **No need to create new file**; specify `task_encoder: vlm_task_encoder.VLMTaskEncoder` in YAML
- Any dimension differs -> **Create new** `loongforge/data/multimodal/<family>_task_encoder.py`, inheriting `VLMTaskEncoder` and overriding differing methods
- Image/video preprocessing logic differs (resize strategy, patch calculation, etc.) -> **Additionally create new** `loongforge/data/<family>_plugin.py`, inheriting `MMPlugin`

---

## Example: Kimi K2.5

- Difference 1/2: `<\|media_begin\|>image<\|media_content\|><\|media_pad\|><\|media_end\|>` replaces the standard format
- Difference 3: `<\|im_user\|>/<\|im_middle\|>/<\|im_end\|>/<\|im_assistant\|>` dedicated chat template
- Difference 4: `<\|media_content\|>` single placeholder, needs to be expanded into multiple `<\|media_pad\|>` in the Task Encoder based on grid_thw
- Generated files: `kimi_task_encoder.py` (inherits VLMTaskEncoder) + `kimi_k25_plugin.py` (inherits MMPlugin)
