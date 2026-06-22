---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - skills/adapt/lib/__init__.py
  - skills/adapt/lib/schema.py
  - skills/adapt/lib/redact.py
  - skills/adapt/lib/protected_paths.py
  - skills/adapt/lib/jsonl.py
  - skills/adapt/knowledge_base/redact_domains.yml
  - skills/adapt/tests/__init__.py
  - skills/adapt/tests/lib/__init__.py
  - skills/adapt/tests/lib/test_schema.py
  - skills/adapt/tests/lib/test_redact.py
  - skills/adapt/tests/lib/test_jsonl_append_only.py
  - skills/adapt/tests/lib/test_protected_paths.py
  - requirements.txt
autonomous: true
requirements:
  - LOG-02
  - LOG-03
  - SAFE-01
  - TEST-02
  - TEST-03
must_haves:
  truths:
    - "Pydantic v2 models accept legacy v1 run_inputs.yml (no repos:/loop:) and a v2 dict (with repos: and loop:) — round-trip stable."
    - "Redactor strips ghp_, github_pat_, hf_, AKIA, Bearer, /home/<user>/, gho_, ghu_, ghs_, aws_secret_access_key from text and returns accept=False if any pattern survives."
    - "append_attempt() writes one JSON line per call, fsync'd, ending in \\n; assert_append_only enforces the invariant for tests."
    - "is_protected('skills/adapt/scripts/validate_phase_completion.py') is True; is_protected('README.md') is False; PROTECTED_PATHS is non-empty."
    - "pydantic>=2.9,<3 declared in requirements.txt and importable."
    - "PrBlockOutput and IssuesBlockOutput skeleton models exist in lib/schema.py with extra='ignore' so Phase 2 only fills field details and Phase 3 can read pr/issues blocks before Phase 2 lands (LOG-02 forward-compat)."
  artifacts:
    - path: "skills/adapt/lib/__init__.py"
      provides: "Package marker for skills.adapt.lib"
    - path: "skills/adapt/lib/schema.py"
      provides: "Pydantic v2 models: RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput"
      contains: "class RunInputs"
    - path: "skills/adapt/lib/redact.py"
      provides: "redact() + RedactionResult; secret regex sweep with residual post-check"
      contains: "def redact"
    - path: "skills/adapt/lib/protected_paths.py"
      provides: "PROTECTED_PATHS tuple + is_protected()"
      contains: "PROTECTED_PATHS"
    - path: "skills/adapt/lib/jsonl.py"
      provides: "append_attempt() + assert_append_only() — O_APPEND atomic writer"
      contains: "def append_attempt"
    - path: "skills/adapt/knowledge_base/redact_domains.yml"
      provides: "Internal-domain config for redactor (extensible without code change)"
    - path: "requirements.txt"
      provides: "pydantic>=2.9,<3 + pyyaml dep declaration"
      contains: "pydantic"
  key_links:
    - from: "skills/adapt/lib/schema.py"
      to: "pydantic v2.9"
      via: "from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator"
      pattern: "from pydantic import"
    - from: "skills/adapt/lib/redact.py"
      to: "skills/adapt/knowledge_base/redact_domains.yml"
      via: "_INTERNAL_DOMAIN_CONFIG path constant"
      pattern: "knowledge_base/redact_domains.yml"
    - from: "skills/adapt/tests/lib/test_redact.py"
      to: "skills/adapt/lib/redact.py"
      via: "import"
      pattern: "from skills.adapt.lib.redact import"
---

<objective>
Foundation libraries for Phase 1: Pydantic v2 schema models, secret redactor, append-only JSONL writer, validator-protected-paths data module, and the pydantic dependency declaration. No CLI changes, no preflight, no validator hook — this plan ships ONLY the importable substrate that plans 02–04 build on.

Purpose: Plans 02 (preflight), 03 (CLI), 04 (validator hook) all import from `skills/adapt/lib/`. Shipping these in Wave 1 unblocks both Wave 2 plans (03, 04) and plan 02 in parallel (02 only needs `lib/redact.py` is not strictly required for 02, but it imports nothing from this plan — they share no files, so they parallelize).

Output: 5 new modules under `skills/adapt/lib/`, 4 unit-test files under `skills/adapt/tests/lib/`, 2 `__init__.py` markers, 1 YAML config, and `requirements.txt` with `pydantic>=2.9,<3` and `pyyaml`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md
@.planning/research/PITFALLS.md
@skills/adapt/scripts/run.py
@skills/adapt/tests/test_plugin_layout.py

<interfaces>
<!-- Existing run_inputs.yml shape (from skills/adapt/scripts/run.py:_build_run_inputs lines 35-67). Schema models MUST accept this verbatim as legacy v1: -->
```python
{
  "source": {"hf_ckpt_path": str},
  "paths": {"hf_modeling_path": str, "hf_transformers_path": str,
            "omni_path": str, "megatron_path": str},
  "options": {"model_name": str, "gpu_execution_mode": "local_gpu"|"k8s",
              "enable_slice_ckpt": "true"|"false", "k8s_yaml_path": str,
              "k8s_launch_cmd": str, "wip_code_paths": str},
}
```

<!-- The new optional v2 blocks (from RESEARCH §2). repos: present == loop_engineering_enabled. -->
```python
{
  ...legacy v1 keys...,
  "repos": {
    "hf_impl":   {"url": HttpUrl, "ref": str, "subpath": str|None},
    "hf_ckpt":   {"url": HttpUrl, "revision": str},
    "loongforge": {"url": HttpUrl, "base_ref": str, "work_branch": str, "subpath": str|None},
    "megatron":   {"url": HttpUrl, "base_ref": str, "work_branch": str, "subpath": str|None},
  },
  "loop": {
    "max_attempts_per_phase": 5,    # ge=1, le=50
    "max_attempts_per_run":   25,   # ge=1, le=500
    "max_wallclock_minutes":  240,  # ge=10, le=10080
    "escalation": "human_needed"|"autonomous_blocked",
  },
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1.1: Schema, JSONL writer, protected-paths, package markers, dep declaration</name>
  <read_first>
    - .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md (§2 Pydantic v2 schema, §7 Append-only attempts.jsonl, §9 Validator-protected-paths)
    - skills/adapt/scripts/run.py (lines 35-67 for legacy v1 _build_run_inputs shape)
    - skills/adapt/tests/test_plugin_layout.py (existing tests must continue to pass — do not break)
  </read_first>
  <behavior>
    - Test: A legacy dict {"source": {"hf_ckpt_path": "/tmp/m"}, "paths": {"hf_modeling_path": "", ...}, "options": {"model_name": "x", "gpu_execution_mode": "local_gpu", ...}} round-trips through RunInputs.model_validate(...).model_dump(exclude_none=True) and re-validates equal.
    - Test: A v2 dict adding repos: with all 4 sub-blocks (hf_impl, hf_ckpt, loongforge, megatron each with valid HttpUrl) AND loop: with budget fields validates; .loop_engineering_enabled is True.
    - Test: extra="forbid" rejects {"repo": {...}} (missing "s") with pydantic.ValidationError.
    - Test: LoopBudget(max_attempts_per_phase=51) raises ValidationError (Field le=50 ceiling); LoopBudget(max_attempts_per_run=501) raises; LoopBudget(max_wallclock_minutes=10081) raises.
    - Test: append_attempt(tmp_path/"a.jsonl", {"k":"v"}) creates file ending with "\n"; calling 3 times yields exactly 3 newline-terminated lines; assert_append_only(path, expected_min_lines=3) returns None; assert_append_only(path, expected_min_lines=4) raises AssertionError.
    - Test: is_protected("skills/adapt/scripts/validate_phase_completion.py") is True; is_protected("bin/loongforge-phase-gate") is True; is_protected("skills/adapt/references/phases/phase1/verify.md") is True; is_protected("README.md") is False; len(PROTECTED_PATHS) >= 1.
    - Test (LOG-02 forward-compat): `PrBlockOutput.model_validate({"number": 7, "url": "https://x", "unknown_future": "ok"})` succeeds (extra="ignore"); resulting `.number == 7`, `.url == "https://x"`, `.merged_sha is None`. Same shape test for `IssuesBlockOutput.model_validate({"opened": [1,2], "closed": [], "escalated": [], "future_key": "ok"})`.
  </behavior>
  <action>
Create the following files VERBATIM from RESEARCH §2, §7, §9 (do not paraphrase — copy the code):

**File 1: `skills/adapt/lib/__init__.py`** — single line: `"""skills.adapt.lib — Phase 1 loop-engineering foundation modules."""`

**File 2: `skills/adapt/lib/schema.py`** — copy the code block from RESEARCH §2 lines 43-141 verbatim. Models: `RepoSpec`, `HFImplSpec`, `HFCkptSpec`, `ReposBlock`, `LoopBudget`, `SourceBlock`, `PathsBlock`, `OptionsBlock`, `RunInputs` (with `loop_engineering_enabled` property and `_v2_sanity` model_validator), `LoopBlockOutput`. Use `from __future__ import annotations`. Every model MUST set `model_config = ConfigDict(extra="forbid")`. `LoopBudget` MUST use `Field(5, ge=1, le=50)`, `Field(25, ge=1, le=500)`, `Field(240, ge=10, le=10_080)`. `LoopBlockOutput.exit_reason` MUST be `Literal["validator_passed", "validator_passed_after_fix", "exhausted", "escalated", "base_only", "human_needed"]`.

Additionally — for LOG-02 forward-compat (W2) — add TWO skeleton models so Phase 2 only fills field details and Phase 3 can read these blocks before Phase 2 lands:

```python
class PrBlockOutput(BaseModel):
    """Skeleton for the optional `pr:` block in phaseN_output.yml.
    Phase 1 ships fields-as-known; extra="ignore" lets Phase 2 add more keys without breaking Phase 1 readers."""
    model_config = ConfigDict(extra="ignore")
    number: Optional[int] = None         # PR number once opened
    url: Optional[str] = None            # PR HTML URL
    head: Optional[str] = None           # head branch (work_branch)
    base: Optional[str] = None           # base branch (base_ref)
    state: Optional[Literal["open", "closed", "merged"]] = None
    merged_sha: Optional[str] = None     # commit sha after merge
    idempotency_key: Optional[str] = None

class IssuesBlockOutput(BaseModel):
    """Skeleton for the optional `issues:` block in phaseN_output.yml.
    Same forward-compat policy as PrBlockOutput."""
    model_config = ConfigDict(extra="ignore")
    opened: list[int] = Field(default_factory=list)   # issue numbers opened by the loop
    closed: list[int] = Field(default_factory=list)   # issue numbers auto-closed on success
    escalated: list[int] = Field(default_factory=list) # issue numbers handed to humans
```

Add `from typing import Optional` to the imports if not already present. These two classes MUST be defined AFTER `LoopBlockOutput` so the file ends with the loop-evidence model trio (loop / pr / issues). They are NOT yet wired into `RunInputs` — Phase 2 wires them. Phase 1 only ships the importable types so downstream plans can `from skills.adapt.lib.schema import PrBlockOutput, IssuesBlockOutput`.

**File 3: `skills/adapt/lib/jsonl.py`** — copy the code block from RESEARCH §7 lines 339-368 verbatim. Functions: `append_attempt(path, record) -> None` (uses `os.open(..., os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o644)`, then `os.write` + `os.fsync` + `os.close`); `assert_append_only(path, expected_min_lines) -> None` (raises AssertionError on missing file, missing trailing `\n`, or fewer lines than expected). `mkdir(parents=True, exist_ok=True)` on parent.

**File 4: `skills/adapt/lib/protected_paths.py`** — copy the code block from RESEARCH §9 lines 440-470 verbatim. Module-level `PROTECTED_PATHS: tuple[str, ...]` containing exactly these glob patterns:
```
"skills/adapt/references/phases/*/verify.md",
"skills/adapt/references/phases/*/loss_diff.md",
"skills/adapt/references/phases/*/feature_compat.md",
"skills/adapt/references/phases/*/kb_consistency.md",
"skills/adapt/scripts/validate_phase_completion.py",
"bin/loongforge-phase-gate",
"skills/adapt/lib/redact.py",
"skills/adapt/lib/protected_paths.py",
"skills/adapt/lib/preflight.py",
"skills/adapt/scripts/perf_review.py",
"skills/adapt/scripts/hf_forward.py",
```
Function `is_protected(repo_relative_path: str) -> bool` uses `fnmatch.fnmatch` over each pattern.

**File 5: `skills/adapt/tests/__init__.py`** — empty file (just `touch`-equivalent: write `""`).

**File 6: `skills/adapt/tests/lib/__init__.py`** — empty file.

**File 7: `requirements.txt`** at repo root (`/Users/weizhihao/workspace/agent_skills/loongforge-plugin/requirements.txt`). Create new file with:
```
pydantic>=2.9,<3
pyyaml>=6.0
```
Install with `python3 -m pip install -r requirements.txt` so subsequent tests/tasks can import pydantic.

**File 8: `skills/adapt/tests/lib/test_schema.py`** — TEST-03 + COMPAT-02 (legacy round-trip). Build the test cases listed in `<behavior>` above. Use inline Python dicts (no fixture files needed for this size). Assert exact pydantic.ValidationError on the negative cases. Round-trip helper: `assert RunInputs.model_validate(d).model_dump(exclude_none=True, mode="json") == d` for both legacy v1 and v2 inputs (use `mode="json"` so HttpUrl serializes back to str cleanly).

Also add LOG-02 forward-compat tests in the same file: a `test_pr_block_skeleton_forward_compat` that validates a `PrBlockOutput` dict carrying an unknown future key and asserts the unknown key is silently ignored AND the known fields are populated; analogous `test_issues_block_skeleton_forward_compat` for IssuesBlockOutput. These prove `extra="ignore"` on the skeletons.

**File 9: `skills/adapt/tests/lib/test_jsonl_append_only.py`** — LOG-03. Three sub-tests: (a) write 3 records, assert 3 lines + trailing newline; (b) `assert_append_only` succeeds for expected count and raises AssertionError for expected_min_lines exceeding actual; (c) after `path.write_bytes(b"")` truncate, next `append_attempt` still results in single line — i.e. O_APPEND survives external truncation.

**File 10: `skills/adapt/tests/lib/test_protected_paths.py`** — assertions listed in `<behavior>`.
  </action>
  <verify>
    <automated>cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin && python3 -m pip install -r requirements.txt --quiet && python3 -m pytest skills/adapt/tests/lib/test_schema.py skills/adapt/tests/lib/test_jsonl_append_only.py skills/adapt/tests/lib/test_protected_paths.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -c "from skills.adapt.lib.schema import RunInputs, ReposBlock, LoopBudget, LoopBlockOutput; print('ok')"` prints `ok` (run from repo root).
    - `python3 -c "from skills.adapt.lib.schema import LoopBudget; LoopBudget(max_attempts_per_phase=51)"` exits non-zero (ValidationError).
    - `grep -q "extra=\"forbid\"" skills/adapt/lib/schema.py` AND `grep -q "loop_engineering_enabled" skills/adapt/lib/schema.py` AND `grep -q "LoopBlockOutput" skills/adapt/lib/schema.py`.
    - LOG-02 forward-compat (W2): `grep -q "class PrBlockOutput" skills/adapt/lib/schema.py` AND `grep -q "class IssuesBlockOutput" skills/adapt/lib/schema.py` AND `grep -q "extra=\"ignore\"" skills/adapt/lib/schema.py` (skeletons use forward-compat config).
    - LOG-02 forward-compat: `python3 -c "from skills.adapt.lib.schema import PrBlockOutput, IssuesBlockOutput; PrBlockOutput.model_validate({'number': 1, 'unknown_future_field': 'x'}); IssuesBlockOutput.model_validate({'opened': [1, 2], 'unknown_future_field': 'x'})"` exits 0 (extra fields silently ignored — forward-compat invariant).
    - `grep -q "os.O_APPEND" skills/adapt/lib/jsonl.py` AND `grep -q "os.fsync" skills/adapt/lib/jsonl.py`.
    - `grep -q "loongforge-phase-gate" skills/adapt/lib/protected_paths.py` AND `grep -q "validate_phase_completion.py" skills/adapt/lib/protected_paths.py`.
    - `grep -E "^pydantic>=2\\.9,<3" requirements.txt` matches.
    - The three new test files all pass under pytest (exit 0).
    - `python3 -m pytest skills/adapt/tests/test_plugin_layout.py -x -q` still passes (no regression).
  </acceptance_criteria>
  <done>Schema, JSONL writer, protected-paths data module, package markers, and pydantic dep are all in place; their unit tests pass; existing test_plugin_layout.py is unaffected.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 1.2: Redactor + redact_domains.yml + snapshot tests</name>
  <read_first>
    - .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md (§5 Redactor, §11 test approach for test_redact)
    - .planning/research/PITFALLS.md (Pitfall 9 — Secrets in PR/issue bodies)
    - skills/adapt/lib/redact.py (will not exist yet — that's fine, this task creates it)
  </read_first>
  <behavior>
    - Test: redact("Bearer abc123def456ghi789jkl") replaces with "[REDACTED:bearer_header]" and accept=True.
    - Test: redact("token=ghp_1234567890ABCDEFGHIJ") replaces "ghp_..." with "[REDACTED:github_pat_v1]"; accept=True.
    - Test: redact("hf_AAAAAAAAAAAAAAAAAAAAAA") → "[REDACTED:hf_token]"; accept=True.
    - Test: redact("aws=AKIAIOSFODNN7EXAMPLE other=AKIA1234567890ABCDEF") → both replaced with "[REDACTED:aws_access_key]"; matches reports `("aws_access_key", 2)`.
    - Test: redact("/home/alice/secret.txt") → "[REDACTED:home_path]" replaces the prefix.
    - Test: redact("plain text no secrets") → cleaned == original; matches == []; accept=True.
    - Test (residual): redact("ghp_BEFORE then ghp_AFTER") with first call. After single substitution, no residual remains; accept=True. Construct adversarial case where a pattern's replacement itself looks like another pattern — e.g. a redaction marker should NOT trigger residual; verify accept=True.
    - Test (multi-pattern): a contrived corpus containing all 10 hardcoded prefixes redacts each with its own name and accept=True.
    - Test (internal_domains): redact("internal.example.corp", internal_domains=("internal.example.corp",)) → "[REDACTED:internal_domain]"; accept=True.
  </behavior>
  <action>
**File 1: `skills/adapt/lib/redact.py`** — copy the code block from RESEARCH §5 lines 246-292 verbatim. Required exact contents:

- `import re` at top, `from dataclasses import dataclass`.
- Module-level `_SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...]` containing EXACTLY these 10 named patterns in this order:
  1. `("github_pat_v2", re.compile(r"github_pat_[A-Za-z0-9_]{20,}"))`
  2. `("github_pat_v1", re.compile(r"ghp_[A-Za-z0-9]{20,}"))`
  3. `("github_oauth",  re.compile(r"gho_[A-Za-z0-9]{20,}"))`
  4. `("github_user",   re.compile(r"ghu_[A-Za-z0-9]{20,}"))`
  5. `("github_server", re.compile(r"ghs_[A-Za-z0-9]{20,}"))`
  6. `("aws_access_key",re.compile(r"AKIA[0-9A-Z]{16}"))`
  7. `("hf_token",      re.compile(r"hf_[A-Za-z0-9]{20,}"))`
  8. `("bearer_header", re.compile(r"Bearer\s+[A-Za-z0-9._\-+/]{16,}"))`
  9. `("home_path",     re.compile(r"/home/[a-zA-Z0-9_\-\.]+(/|$)"))`
  10. `("aws_secret_kv",re.compile(r"(?i)aws_secret(_access)?_key\s*[:=]\s*[A-Za-z0-9/+=]{30,}"))`
- Module-level constant: `_INTERNAL_DOMAIN_CONFIG = "skills/adapt/knowledge_base/redact_domains.yml"`.
- `@dataclass(frozen=True) class RedactionResult` with fields `cleaned: str`, `matches: list[tuple[str, int]]`, `accept: bool`.
- `def redact(text: str, *, internal_domains: tuple[str, ...] = ()) -> RedactionResult:` body iterates patterns, calling `pat.subn(f"[REDACTED:{name}]", cleaned)`; tracks counts; then iterates `internal_domains` doing `re.escape(dom)` substitution with replacement `"[REDACTED:internal_domain]"`; finally runs residual sweep `residual = any(p.search(cleaned) for _, p in _SECRET_PATTERNS)`; returns `RedactionResult(cleaned=cleaned, matches=list(counts.items()), accept=not residual)`.

**File 2: `skills/adapt/knowledge_base/redact_domains.yml`** — new file with this exact content:
```yaml
# Internal domain patterns redacted from any text bound for external GitHub posts.
# Add literal substrings (not regexes); they are escaped at load time.
# Phase 1 ships with a commented placeholder. Operators add real internal
# hostnames here without touching code.
#
# Example:
# - corp.internal
# - intranet.example.com
domains: []
```

**File 3: `skills/adapt/tests/lib/test_redact.py`** — TEST-02. Implement all sub-tests from `<behavior>` above. Use parametrize where ergonomic. Each test asserts:
  1. `result.cleaned` equals expected literal string,
  2. `result.matches` contains expected `(name, count)` pairs,
  3. `result.accept` matches expected boolean.
  Add one snapshot-style "all secrets in one corpus" test:
  ```python
  corpus = (
      "Authorization: Bearer abcdef1234567890XYZ\n"
      "GH_TOKEN=ghp_AAAAAAAAAAAAAAAAAAAA\n"
      "PAT=github_pat_BBBBBBBBBBBBBBBBBBBB\n"
      "HF=hf_CCCCCCCCCCCCCCCCCCCC\n"
      "AWS=AKIAIOSFODNN7EXAMPLE\n"
      "PATH=/home/alice/secret\n"
  )
  ```
  Assert each `[REDACTED:<name>]` marker appears in `result.cleaned` and `result.accept is True`.
  </action>
  <verify>
    <automated>cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin && python3 -m pytest skills/adapt/tests/lib/test_redact.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -c "from skills.adapt.lib.redact import redact, RedactionResult; r = redact('Bearer ' + 'a'*32); assert r.cleaned == '[REDACTED:bearer_header]'; assert r.accept is True"` exits 0.
    - `grep -c "re.compile" skills/adapt/lib/redact.py` returns at least 10 (one per hardcoded pattern).
    - `grep -q "github_pat_" skills/adapt/lib/redact.py` AND `grep -q "AKIA" skills/adapt/lib/redact.py` AND `grep -q "/home/" skills/adapt/lib/redact.py` AND `grep -q "Bearer" skills/adapt/lib/redact.py`.
    - `test -f skills/adapt/knowledge_base/redact_domains.yml` AND `grep -q "domains:" skills/adapt/knowledge_base/redact_domains.yml`.
    - `python3 -m pytest skills/adapt/tests/lib/test_redact.py -x -q` exits 0.
  </acceptance_criteria>
  <done>Redactor + YAML config + snapshot tests in place; SAFE-01 (mandatory redaction filter) and TEST-02 (snapshot tests) both satisfied at the lib layer.</done>
</task>

</tasks>

<verification>
After both tasks complete, run from repo root:

```
cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin
python3 -m pip install -r requirements.txt --quiet
python3 -m pytest skills/adapt/tests/lib/ -x -q
python3 -m pytest skills/adapt/tests/test_plugin_layout.py -x -q   # no regression
```

All four new test files (`test_schema.py`, `test_redact.py`, `test_jsonl_append_only.py`, `test_protected_paths.py`) MUST pass; existing layout test MUST still pass.
</verification>

<success_criteria>
- Modules `skills.adapt.lib.{schema,redact,jsonl,protected_paths}` are importable from repo root.
- `pydantic>=2.9,<3` and `pyyaml>=6.0` declared in `requirements.txt`.
- `LoopBudget` Field ceilings (`le=50`, `le=500`, `le=10_080`) defang Pitfall #2 at parse time.
- `RunInputs` accepts legacy v1 dict unchanged AND v2 dict with `repos:` + `loop:`; `extra="forbid"` rejects typos.
- `redact()` strips all 10 hardcoded patterns + configurable internal domains; `accept=False` when any residual remains after substitution.
- `append_attempt` is `O_APPEND`-only with `fsync`; truncation by another writer cannot cause partial-line corruption on next append.
- `is_protected()` returns True for the canonical protected-paths set, False for unrelated files.
- LOG-02 forward-compat: `PrBlockOutput` and `IssuesBlockOutput` skeleton models are importable from `skills.adapt.lib.schema`; both use `extra="ignore"` so Phase 2 fills field details without breaking Phase 1 readers; Phase 3 can read pr/issues data before Phase 2 lands.
- Existing `test_plugin_layout.py` unaffected.
</success_criteria>

<output>
After completion, create `.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-SUMMARY.md` summarizing:
- Files created (paths)
- Public API of each `lib/` module (one line per exported name)
- Test counts and pass status
- Any deviations from RESEARCH §2/§5/§7/§9
</output>
