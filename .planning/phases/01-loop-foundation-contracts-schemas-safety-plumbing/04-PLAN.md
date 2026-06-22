---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
plan: 04
type: execute
wave: 2
depends_on:
  - "01-loop-foundation-contracts-schemas-safety-plumbing/01"
files_modified:
  - skills/adapt/scripts/validate_phase_completion.py
  - skills/adapt/SKILL.md
  - skills/adapt/tests/lib/test_validate_loop_evidence.py
  - skills/adapt/tests/lib/test_loop_lint.py
autonomous: true
requirements:
  - COMPAT-03
  - SAFE-02
  - SAFE-03
must_haves:
  truths:
    - "validate_phase_completion.py: legacy phaseN_output.yml (no `loop_engineering` flag) passes validate_phase_output unchanged."
    - "validate_phase_completion.py: phaseN_output.yml with `loop_engineering: true` and a malformed `loop:` block raises pydantic.ValidationError via _validate_loop_evidence."
    - "validate_phase_completion.py: phaseN_output.yml with `loop_engineering: true` and no `loop:` block passes (inert hook)."
    - "test_loop_lint.py: scanning skills/adapt/scripts, skills/adapt/lib, agents/ for /loop invocations finds zero hits (current code is clean)."
    - "skills/adapt/SKILL.md contains a SAFE-03 note: bulk log content externalized to files; only excerpts in chat context."
  artifacts:
    - path: "skills/adapt/scripts/validate_phase_completion.py"
      provides: "Extended validator with _validate_loop_evidence() called as final step in validate_phase_output."
      contains: "def _validate_loop_evidence"
    - path: "skills/adapt/tests/lib/test_validate_loop_evidence.py"
      provides: "COMPAT-03 inert-hook test + future-flag honoured test"
    - path: "skills/adapt/tests/lib/test_loop_lint.py"
      provides: "SAFE-02 grep guard against /loop invocations in skill code"
    - path: "skills/adapt/SKILL.md"
      provides: "SAFE-03 documentation note (small preamble edit)"
  key_links:
    - from: "skills/adapt/scripts/validate_phase_completion.py"
      to: "skills/adapt/lib/schema.py"
      via: "from skills.adapt.lib.schema import LoopBlockOutput"
      pattern: "LoopBlockOutput"
    - from: "skills/adapt/tests/lib/test_loop_lint.py"
      to: "skills/adapt/scripts + skills/adapt/lib + agents/"
      via: "rglob over directories scanning .py / .md / .sh"
      pattern: "SCAN_DIRS"
---

<objective>
Land the additive validator hook (`_validate_loop_evidence`) in `validate_phase_completion.py` (inert when `loop_engineering` flag absent — COMPAT-03), plus the SAFE-02 `/loop` lint test and a small SAFE-03 documentation note in `skills/adapt/SKILL.md`. No behavior change to legacy validator paths.

Purpose: Ship the inert hook now so Phase 3 fills the body without touching `validate_phase_output`'s control flow again. SAFE-02 lint runs in CI from day one to prevent `/loop` regression. SAFE-03 doc note tells phase agents to externalize bulk logs.

Output: Extended `validate_phase_completion.py` + 2 new test files + 1-line preamble edit in SKILL.md.

Parallelism: Wave 2, depends only on plan 01 (uses `LoopBlockOutput` from schema). Plan 03 (CLI extension) and this plan touch disjoint files (`scripts/run.py` vs `scripts/validate_phase_completion.py`). They run in parallel.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md
@skills/adapt/scripts/validate_phase_completion.py
@skills/adapt/SKILL.md
@skills/adapt/lib/schema.py

<interfaces>
<!-- LoopBlockOutput model from plan 01 (RESEARCH §2 lines 130-141): -->
```python
from skills.adapt.lib.schema import LoopBlockOutput
LoopBlockOutput.model_validate({
  "attempts": 0, "max_attempts": 5, "exit_reason": "validator_passed",
  "attempts_journal": "phases/phase1/attempts.jsonl"
})
```

<!-- Existing validate_phase_output (lines 66-114 in current validate_phase_completion.py).
     Add _validate_loop_evidence as the FINAL call inside validate_phase_output, AFTER all
     existing per-phase checks (RESEARCH §6 lines 320-327). -->
```python
def validate_phase_output(run_dir: Path, phase: int) -> None:
    data = _load_phase_output(run_dir, phase)
    _expect(data.get("status") == "passed", "phase status must be passed")
    _validate_step_gate(data)
    # ... existing per-phase checks ...
    _validate_loop_evidence(data)   # NEW — inert when flag absent
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 4.1: _validate_loop_evidence() inert hook + COMPAT-03 tests + SAFE-03 doc note</name>
  <read_first>
    - skills/adapt/scripts/validate_phase_completion.py (full file — note BLOCK_EXIT_CODE=2, validate_phase_output structure)
    - .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md (§6 _validate_loop_evidence insertion lines 301-331)
    - skills/adapt/SKILL.md (full file — preamble area for SAFE-03 note)
  </read_first>
  <behavior>
    - Test (legacy passes): write a phase1_output.yml with `{phase: 1, status: passed, step_gate: {mandatory_steps_complete: true}, steps: {step1: {status: passed, evidence: x}}, validator: {name: phase1-verify, status: passed}}` (NO loop_engineering field). `validate_phase_output(run_dir, 1)` returns None (no exception).
    - Test (loop_engineering=true, no loop block): same dict + `loop_engineering: true`. `validate_phase_output(run_dir, 1)` returns None (inert: no loop block to validate).
    - Test (loop_engineering=true, valid loop block): add `loop: {attempts: 1, max_attempts: 5, exit_reason: validator_passed, attempts_journal: phases/phase1/attempts.jsonl}`. Returns None.
    - Test (loop_engineering=true, malformed loop block): add `loop: {attempts: -1, max_attempts: 5, exit_reason: validator_passed, attempts_journal: ""}`. Calling `validate_phase_output` raises `pydantic.ValidationError` (negative attempts violates `Field(0, ge=0)`).
    - Test (loop_engineering=true, malformed exit_reason): add `loop: {..., exit_reason: "made_up_reason", ...}`. Raises `pydantic.ValidationError` (Literal mismatch).
    - Test (CLI gate exit code preserved): invoke `bin/loongforge-phase-gate --run-dir <tmp> --phase 1` against a malformed-loop YAML; exit code is `BLOCK_EXIT_CODE` (2) and stderr starts with `BLOCKED:`.
    - Test (SAFE-03 doc note): `grep -q "externalized" skills/adapt/SKILL.md` AND `grep -q "excerpts" skills/adapt/SKILL.md` confirm the preamble carries the note.
  </behavior>
  <action>
### Step A — Edit `skills/adapt/scripts/validate_phase_completion.py`

Insert the new function VERBATIM from RESEARCH §6 lines 306-319, BEFORE the existing `validate_phase_output` function (so it's defined first):

```python
def _validate_loop_evidence(data: dict[str, Any]) -> None:
    """Phase 1 lays this hook inert. Real checks land in Phase 3.

    When loop_engineering: true is set, this is where future checks for
    PR-merged status, validator-binary hash, log-mtime, attempts.jsonl
    presence, etc. will live (per VAL-04, REQ-LOG-01)."""
    if data.get("loop_engineering") is not True:
        return  # legacy output: skip silently
    loop_block = data.get("loop")
    if loop_block is not None:
        from skills.adapt.lib.schema import LoopBlockOutput
        LoopBlockOutput.model_validate(loop_block)
```

NOTE: keep the import LOCAL (inside the function) so `import validate_phase_completion` does NOT pay for `pydantic` at module load — keeps the legacy code path zero-cost.

### Step B — Add the call site at the END of `validate_phase_output`

Find the function `validate_phase_output(run_dir: Path, phase: int) -> None` (line 66 currently). Add `_validate_loop_evidence(data)` as the FINAL line of the function, AFTER all existing per-phase checks (after the phase==2 production_gate block, line 114). Single-line addition. Do NOT modify any of the existing `_expect` calls.

### Step C — Edit `skills/adapt/SKILL.md` for SAFE-03

In the existing SKILL.md preamble (after the "## Reading Order" section), add a small new section. Find the block ending around line 35 (`/loop` boundary discussion). Insert AFTER that block, BEFORE "## Input Schema Markers":

```markdown
## Bulk Log Externalization (SAFE-03)

Phase agents MUST externalize bulk log content (validator stdout/stderr, training logs, NCCL traces) to files under `phases/phaseN/logs/`, and quote only the relevant **excerpts** (last 50-200 lines or matched regex windows) into chat context. Reason: in-session context bloat (PITFALLS.md #19) degrades agent quality on long runs. Reference logs by relative path; never paste multi-MB blobs.
```

This is purely additive prose; do not remove or rewrite anything else in SKILL.md (would break test_plugin_layout.py).

### Step D — Create `skills/adapt/tests/lib/test_validate_loop_evidence.py`

Implement all sub-tests from `<behavior>`. Helper:

```python
import yaml, subprocess, sys
from pathlib import Path
import pytest
from skills.adapt.scripts.validate_phase_completion import validate_phase_output

REPO_ROOT = Path(__file__).resolve().parents[4]   # …/loongforge-plugin

def _write(run_dir: Path, phase: int, data: dict) -> None:
    (run_dir / "phases").mkdir(parents=True, exist_ok=True)
    (run_dir / "phases" / f"phase{phase}_output.yml").write_text(
        yaml.dump(data, sort_keys=False)
    )
```

Sub-tests:
1. `test_legacy_phase1_output_passes` — no `loop_engineering` field; `validate_phase_output` returns None.
2. `test_loop_engineering_true_no_loop_block_passes` — `loop_engineering: true` but no `loop:` key; returns None.
3. `test_loop_engineering_true_valid_loop_passes` — full valid loop block; returns None.
4. `test_loop_engineering_true_malformed_attempts_raises` — `loop.attempts: -1`; expects `pydantic.ValidationError`.
5. `test_loop_engineering_true_invalid_exit_reason_raises` — `loop.exit_reason: "made_up"`; expects `pydantic.ValidationError`.
6. `test_phase_gate_cli_blocks_malformed_loop` — subprocess invocation of `bin/loongforge-phase-gate --run-dir <tmp> --phase 1` against the malformed YAML; assert returncode == 2 and stderr starts with `BLOCKED:`.

### Step E — `skills/adapt/SKILL.md` — verify the runner-cli-smoke test still passes

The existing test `test_plugin_runner_cli_smoke` at `tests/test_plugin_layout.py:493` runs `bin/loongforge-adapt /tmp/model --run-dir <tmp>` and asserts `"/loongforge:adapt" in result.stdout`. Our SAFE-03 note doesn't touch that string. After editing SKILL.md, run the existing layout test to confirm.
  </action>
  <verify>
    <automated>cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin && PYTHONPATH=. python3 -m pytest skills/adapt/tests/lib/test_validate_loop_evidence.py skills/adapt/tests/test_plugin_layout.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "def _validate_loop_evidence" skills/adapt/scripts/validate_phase_completion.py`.
    - `grep -q "from skills.adapt.lib.schema import LoopBlockOutput" skills/adapt/scripts/validate_phase_completion.py`.
    - `grep -q "_validate_loop_evidence(data)" skills/adapt/scripts/validate_phase_completion.py` (the call inside validate_phase_output).
    - `grep -q "loop_engineering" skills/adapt/scripts/validate_phase_completion.py`.
    - `grep -q "Bulk Log Externalization" skills/adapt/SKILL.md` AND `grep -q "SAFE-03" skills/adapt/SKILL.md`.
    - `python3 -m pytest skills/adapt/tests/lib/test_validate_loop_evidence.py -x -q` exits 0.
    - `python3 -m pytest skills/adapt/tests/test_plugin_layout.py -x -q` exits 0 (no regression).
    - Negative invariant: legacy phase output (no `loop_engineering` field) MUST NOT trigger any pydantic import or validation. Verify with `python3 -c "import sys; sys.modules.pop('pydantic', None); from skills.adapt.scripts.validate_phase_completion import validate_phase_output; from pathlib import Path; import tempfile, yaml, os; d = Path(tempfile.mkdtemp()); (d/'phases').mkdir(); (d/'phases/phase1_output.yml').write_text(yaml.dump({'phase': 1, 'status': 'passed', 'step_gate': {'mandatory_steps_complete': True}, 'steps': {'s1': {'status': 'passed', 'evidence': 'x'}}, 'validator': {'name': 'phase1-verify', 'status': 'passed'}})); validate_phase_output(d, 1); assert 'pydantic' not in sys.modules, 'legacy path must not import pydantic'"`. Exit 0.
  </acceptance_criteria>
  <done>_validate_loop_evidence() defined and called as final step of validate_phase_output; legacy outputs unaffected; loop_engineering=true outputs validate against LoopBlockOutput schema; SAFE-03 note in SKILL.md; all existing tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4.2: SAFE-02 /loop lint test (test_loop_lint.py)</name>
  <read_first>
    - .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md (§8 /loop lint, full code block lines 380-429)
    - skills/adapt/SKILL.md (line ~34: existing /loop boundary discussion — these are PROSE mentions and must be allowed by the lint)
  </read_first>
  <behavior>
    - Test (current code is clean): `test_no_loop_invocation_in_skill_code` scans `skills/adapt/scripts`, `skills/adapt/lib`, and `agents/`; finds zero hits matching the INVOKE_PATTERNS regexes; assertion passes.
    - The lint MUST NOT flag prose mentions like "the /loop boundary" or "/loop may be used only" inside SKILL.md (it's an allowlisted file via ALLOWED_FILES).
    - Test (positive control — synthetic injection): in a tmp directory, write a Python file containing `SlashCommand("/loop fix-everything")`; manually run the `_scan_file` helper; assert it returns at least one hit. (This proves the regex actually matches forbidden patterns; protects against a tautological lint that would pass even if /loop were invoked.)
  </behavior>
  <action>
**Create `skills/adapt/tests/lib/test_loop_lint.py`** — copy the code block from RESEARCH §8 lines 380-429 verbatim, with these exact contents:

```python
"""SAFE-02: /loop must NOT appear as an invocation in skill code paths.

Allowed: prose mentions in SKILL.md and references/* (e.g. "the /loop boundary").
Forbidden: actual invocation patterns — `/loop <args>`, SlashCommand("/loop..."),
loop_command = "/loop..."."""
from __future__ import annotations
import pathlib
import re
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]   # …/loongforge-plugin
SCAN_DIRS = [
    REPO_ROOT / "skills" / "adapt" / "scripts",
    REPO_ROOT / "skills" / "adapt" / "lib",
    REPO_ROOT / "agents",
]
ALLOWED_FILES = {
    REPO_ROOT / "skills" / "adapt" / "SKILL.md",
}

INVOKE_PATTERNS = (
    re.compile(r"^/loop\b"),                            # /loop at line start
    re.compile(r"SlashCommand\s*\(\s*['\"]/loop"),      # programmatic invoke
    re.compile(r"loop_command\s*=\s*['\"]/loop"),
)


def _scan_file(p: pathlib.Path) -> list[tuple[int, str]]:
    if p.is_dir() or p.suffix not in {".py", ".md", ".sh"}:
        return []
    if "references" in p.parts:
        return []  # references/* allowed to mention /loop freely
    out: list[tuple[int, str]] = []
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return []
    for i, line in enumerate(text.splitlines(), start=1):
        for pat in INVOKE_PATTERNS:
            if pat.search(line):
                out.append((i, line.strip()))
                break
    return out


def test_no_loop_invocation_in_skill_code():
    """SAFE-02: /loop must not appear as an invocation in skill code paths."""
    hits: list[tuple[pathlib.Path, int, str]] = []
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p in ALLOWED_FILES:
                continue
            hits.extend([(p, ln, line) for ln, line in _scan_file(p)])
    assert not hits, "/loop invocation found in skill code:\n" + "\n".join(
        f"  {p}:{ln}  {line}" for p, ln, line in hits
    )


def test_lint_regex_actually_catches_invocations(tmp_path):
    """Positive control: prove the regex catches a forbidden invocation.
    Without this, the main test could pass tautologically if regexes were broken."""
    f = tmp_path / "evil.py"
    f.write_text('SlashCommand("/loop fix-everything")\n')
    hits = _scan_file(f)
    assert hits, "INVOKE_PATTERNS failed to match a known-bad invocation"
```

**Important deviation from RESEARCH §8:** the original first regex `re.compile(r"\b/loop\b\s+\S")` would falsely flag SKILL.md prose like `"/loop may be used only"`. We tighten to `^/loop\b` (line-start) per the safer interpretation, since real invocations appear at line start in shell or in code. This also matches the pytest-only nature of the check (per RESEARCH §8 final paragraph).

Note: `SCAN_DIRS` and `ALLOWED_FILES` resolve from `REPO_ROOT = parents[4]` because the file lives at `skills/adapt/tests/lib/test_loop_lint.py`. Verify the parent count is correct: `tests/lib/file.py → tests → adapt → skills → loongforge-plugin` is 4 parents.
  </action>
  <verify>
    <automated>cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin && PYTHONPATH=. python3 -m pytest skills/adapt/tests/lib/test_loop_lint.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -m pytest skills/adapt/tests/lib/test_loop_lint.py -x -q` exits 0 (both `test_no_loop_invocation_in_skill_code` and `test_lint_regex_actually_catches_invocations` pass).
    - `grep -q "SlashCommand" skills/adapt/tests/lib/test_loop_lint.py` AND `grep -q "loop_command" skills/adapt/tests/lib/test_loop_lint.py`.
    - `grep -q "ALLOWED_FILES" skills/adapt/tests/lib/test_loop_lint.py` AND SKILL.md is in the allowlist (`grep -q "SKILL.md" skills/adapt/tests/lib/test_loop_lint.py`).
    - The positive-control test exists: `grep -q "test_lint_regex_actually_catches_invocations" skills/adapt/tests/lib/test_loop_lint.py`.
  </acceptance_criteria>
  <done>SAFE-02 lint test ships with positive-control test that prevents tautological pass; current code is clean; SKILL.md prose mentions are allowed via ALLOWED_FILES.</done>
</task>

</tasks>

<verification>
After both tasks complete, run from repo root:

```
cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin
PYTHONPATH=. python3 -m pytest skills/adapt/tests/ -x -q
```

ALL existing tests + the new `test_validate_loop_evidence.py` + `test_loop_lint.py` MUST exit 0.

Phase-1-level invariant (after plans 01–04 all merge): `python3 -m pytest skills/adapt/tests/lib/ -x -q` exits 0; `python3 -m pytest skills/adapt/tests/test_plugin_layout.py -x -q` exits 0.
</verification>

<success_criteria>
- COMPAT-03: existing Phase 0–5 validator and step-gate logic unchanged; new `_validate_loop_evidence()` runs only when `loop_engineering: true` flag present; legacy outputs unaffected.
- SAFE-02: `loop_controller.py` (when added in Phase 3) and any code path scanned by the lint cannot use `/loop`; current code is clean and the lint enforces it from day one with a positive-control sanity check.
- SAFE-03: SKILL.md preamble carries the bulk-log-externalization note; phase agents reading the skill see the directive.
- No regressions in `test_plugin_layout.py`.
</success_criteria>

<output>
After completion, create `.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/04-SUMMARY.md` summarizing:
- validate_phase_completion.py edit (function added + call-site line)
- SKILL.md preamble paragraph added (paste verbatim)
- test_loop_lint.py deviation from RESEARCH §8 (line-start regex tightening)
- Test counts and pass status
</output>
