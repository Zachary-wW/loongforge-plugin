# HF Model Directory File Classification Rules

> For use by Phase 0 Step 1. Traverse top-level files in `hf_path/` (do not recurse into subdirectories) and classify them according to the table below.

| Type | Matching Rule | Processing |
|------|--------------|------------|
| **JSON Config** | `config.json` / `tokenizer_config.json` / `preprocessor_config.json` / `generation_config.json` | Read in full, store in memory |
| **README** | `README.md` | Read in full, extract architecture description |
| **Architecture Source** | `modeling_*.py` | Record path, used by Step 2 |
| **Config Class** | `configuration_*.py` | Record path, used by Step 2 |
| **Tokenizer** | `tokenization_*.py` | Record path |
| **Processor** | `*processor*.py` / `*vision_processing*.py` | Record path |
| **Auxiliary Utilities** | `media_utils.py` / `*utils.py` / `tool_declaration*.py` | Record path |
| **Chat template** | `chat_template.jinja` | Record path |
| **Weight Index** | `model.safetensors.index.json` / `pytorch_model.bin.index.json` | Record path, used by Step 3 |
| **Binary Weights** | `*.safetensors` / `*.bin` / `*.pt` | **Skip** |
| **Other Docs** | `*.md` (not README) / `LICENSE` | **Skip** |
| **Other .py** | Does not match any rule above | Record path, scan as needed |
