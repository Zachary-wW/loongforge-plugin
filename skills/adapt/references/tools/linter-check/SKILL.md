---
name: linter-check
description: >
  Execute R001-R020 rule static checks on LoongForge model network construction code, output ERROR items for the fix loop.
  Called after each file is generated in Phase 1, checking specification compliance of _config.py, _layer_spec.py, _model.py, etc.
  Use when checking whether generated code conforms to LoongForge specification, or executing linter static review.
---

# linter_check -- Code Specification Check Tool

## Responsibility

Execute R001-R020 rule checks on generated LoongForge model code files.

## Invocation

> The `loongforge_rules.py` executable script has been removed; linter rules are maintained in document form at `knowledge_base/linter_rules/RULES.md`.
> The Agent executes static checks via **manual item-by-item verification**, with check items in the rule quick reference table below.

Execution steps:
1. Read `knowledge_base/linter_rules/RULES.md`
2. Check the target file item by item according to the rule quick reference table
3. For structural rules such as R001 (Config inheritance), R008 (fields without default values), R014 (model_spec/model_type), refer to the corresponding templates under `knowledge_base/templates/config/` to verify expected structure
4. For component rules such as R002/R003 (layer_spec import), R007 (`_get_mlp_module_spec`), refer to the corresponding templates under `knowledge_base/templates/attention/` and `templates/ffn/` to verify expected import paths
5. Record all ERROR items and process them through the fix loop

## Output Format

```
<file>:<line>: [RuleID] <message>

Total N errors
```

## Rule Quick Reference

For the complete R001-R020 rule quick reference table, see `knowledge_base/linter_rules/RULES.md`.

## Fix Loop

When linter reports errors, read the error message -> fix the corresponding file -> re-run linter.
Maximum 3 rounds; if the same category of error remains unfixed for 3 consecutive rounds, trigger outer retry or `human_needed`.
