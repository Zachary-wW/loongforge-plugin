# [Phase 1] Generated Files Contain Non-Python Content Causing R1 SyntaxError

| Field | Value |
|-------|-------|
| Phase | 1 |
| Applicable Models | General (first recorded: mimo_7b_base, affected files: _config / _layer_spec / _model / __init__) |
| Triggered Rule | R1 (SyntaxError) |
| Date | 2026-04-01 |

## Symptom

Linter Step 4 reports errors; line 1 of 4 files (or some of them) triggers `R1: SyntaxError`:
- `invalid syntax`: file content is markdown prose instead of Python
- `invalid character 'U+2192'` (`->`): markdown arrow written into .py
- `invalid character 'U+2014'` (`--`): markdown dash written into .py

## Root Cause

When generating Python files, the Agent mistakenly writes "content description text" or "permission waiting prompt" as file content, instead of writing actual Python code. Typical scenarios:
- Tool call is rejected or pending, and the Agent writes the waiting explanation text into the file
- Generation order is wrong; placeholder text is written first, then waiting to modify

## Prevention

**Pre-write self-check before Step 3 (from RULES.md R001)**: Before each `.py` file Write, confirm:
1. The first non-comment line is valid Python (`import`, `from`, `class`, `def`, `"""`, etc.)
2. The file content does not contain any markdown symbols (`-> -- ## * \`\`\``)
3. If the current Write permission is not approved, **do not write placeholder content**; wait for permission approval before writing the formal content

## Fix

Re-generate each file: use the candidate Omni file with the same name as the base (`reuse_ref` strategy), only replacing family/class names, ensuring the output is pure Python. After fixing, re-execute the Linter (does not count toward the original 3-round limit; this type of error is an agent operational mistake, not an architectural issue).
