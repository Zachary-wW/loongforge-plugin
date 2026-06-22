---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
verified: 2026-06-22T09:30:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 1: Loop Foundation -- Contracts, Schemas & Safety Plumbing Verification Report

**Phase Goal:** A run can collect the four URL inputs, persist them in extended schemas, pre-flight against GitHub (or skip in `--dry-run`), and any text bound for external repos passes through a hardened redactor -- all without touching loop behavior. FakeGhClient interface is in place from day one so later phases can be developed and tested offline. Establishes plumbing later phases layer on without rewriting.
**Verified:** 2026-06-22T09:30:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

Derived from ROADMAP.md Success Criteria and PLAN must_haves:

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `loongforge-adapt` with all 4 URL flags + `--dry-run` produces `run_inputs.yml` containing `repos:` (4 sub-blocks) and `loop:` (4 budget fields) blocks; legacy invocation without those flags still produces a valid run dir. | VERIFIED | CLI round-trip subprocess test: v2 exits 0, YAML contains repos/loop blocks with correct URLs and budget defaults; legacy exits 0, YAML has source/paths/options only. |
| 2 | Pre-flight fails fast with precise error when `gh auth status` is not OK, write permissions on either external repo are missing, the ckpt URL is unreachable, or branch protection rules are incompatible with auto-merge. | VERIFIED | test_preflight_dry_run.py: 34 tests covering auth fail-fast, missing push, ckpt unreachable, hard-fail branch protection (approving reviews, restrictions, lock_branch); all pass. |
| 3 | Pydantic v2 models reject `run_inputs.yml` v2 missing required `repos.*.url` fields and accept legacy v1 inputs unchanged; round-trip test (TEST-03) passes for both shapes. | VERIFIED | test_schema.py: 20 tests; schema rejects missing url and extra fields (ValidationError); v1 and v2 round-trip stable. |
| 4 | Redaction filter strips `Bearer `, `hf_`, `ghp_`, `AKIA`, `/home/<user>/`, and configured internal-domain patterns from any string before any GitHub post; snapshot tests (TEST-02) match expected output and a residual secret causes post-rejection. | VERIFIED | test_redact.py: 15 tests covering all 10 hardcoded patterns, multi-pattern corpus, residual post-check, internal domains; redact() returns accept=False when pattern survives. |
| 5 | `validate_phase_completion.py` continues to pass legacy `phaseN_output.yml` without the `loop_engineering` flag (COMPAT-03), and the new `_validate_loop_evidence()` extension is callable but inert when the flag is absent; `attempts.jsonl` writes are append-only with no in-place edits (LOG-03). | VERIFIED | test_validate_loop_evidence.py: 7 tests for legacy compat, inert hook, malformed block rejection; test_jsonl_append_only.py: 6 tests for O_APPEND + fsync atomicity. |
| 6 | `--dry-run` flag and `GhClient` interface are wired (INPUT-04): `loongforge-adapt --dry-run` produces a valid run dir with `repos:`/`loop:` blocks, preflight skips live-write probes but enforces URL shape + Pydantic schema, and a `FakeGhClient` stub is selected when `--dry-run` is present. | VERIFIED | test_run_cli.py: V2Invocation tests produce valid dirs with repos/loop; test_preflight_dry_run.py: dry_run=True skips repo_permissions/branch_protection calls; run.py line 244: `gh = FakeGhClient() if dry_run else RealGhClient()`. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `skills/adapt/lib/schema.py` | Pydantic v2 models: RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget, LoopBlockOutput, PrBlockOutput, IssuesBlockOutput | VERIFIED | 142 lines; all models present with extra="forbid" (except PrBlockOutput/IssuesBlockOutput with extra="ignore"); LoopBudget ceilings enforced; loop_engineering_enabled property works |
| `skills/adapt/lib/redact.py` | redact() + RedactionResult; secret regex sweep with residual post-check | VERIFIED | 56 lines; 10 hardcoded patterns; residual post-check; internal_domains support |
| `skills/adapt/lib/jsonl.py` | append_attempt() + assert_append_only() -- O_APPEND atomic writer | VERIFIED | 38 lines; O_APPEND + fsync; assert_append_only test helper |
| `skills/adapt/lib/protected_paths.py` | PROTECTED_PATHS tuple + is_protected() | VERIFIED | 36 lines; 11 glob patterns; fnmatch-based is_protected() |
| `skills/adapt/lib/gh_client.py` | GhClient Protocol, GhResult, RealGhClient, FakeGhClient, FakeGhCall | VERIFIED | 138 lines; 10-method Protocol; RealGhClient preflight subset + 6 NotImplementedError stubs; FakeGhClient in-memory recorder with parameterizable failure modes |
| `skills/adapt/lib/preflight.py` | run_preflight() + PreflightResult + format_failures() | VERIFIED | 203 lines; dry_run skip-writes; branch protection compat (hard-fail + warn-only); stable failure-string prefixes |
| `skills/adapt/scripts/run.py` | Extended CLI: 8 URL flags + --dry-run; _build_run_inputs accepts repos/loop kwargs; init_run_dir invokes preflight | VERIFIED | 460 lines; 8 URL flags + --dry-run; all-or-nothing validation; preflight wired in init_run_dir (skipped on --resume); FakeGhClient selected on dry_run |
| `skills/adapt/scripts/validate_phase_completion.py` | Extended validator with _validate_loop_evidence() inert hook | VERIFIED | 153 lines; _validate_loop_evidence called as final step in validate_phase_output; inert when loop_engineering absent; local pydantic import preserves zero-cost legacy path |
| `skills/adapt/knowledge_base/redact_domains.yml` | Internal-domain config for redactor | VERIFIED | 9 lines; domains: [] placeholder; comments explain usage |
| `skills/adapt/SKILL.md` | SAFE-03 documentation note | VERIFIED | Line 143: "Bulk Log Externalization (SAFE-03)" section present with instructions |
| `requirements.txt` | pydantic>=2.9,<3 + pyyaml>=6.0 | VERIFIED | 2 lines; exact versions declared |

### Test Files

| Test File | Tests | Status |
|-----------|-------|--------|
| test_schema.py | 20 | PASS |
| test_redact.py | 15 | PASS |
| test_jsonl_append_only.py | 6 | PASS |
| test_protected_paths.py | 8 | PASS |
| test_preflight_dry_run.py | 34 | PASS |
| test_run_cli.py | 11 | PASS |
| test_validate_loop_evidence.py | 7 | PASS |
| test_loop_lint.py | 2 | PASS |
| **Total new** | **103** | **ALL PASS** |
| Existing (test_plugin_layout etc.) | 60 | ALL PASS |
| **Grand total** | **163** | **ALL PASS** |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `skills/adapt/scripts/run.py` | `skills/adapt/lib/schema.py` | `from skills.adapt.lib.schema import RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget` | WIRED | Import at line 39; ReposBlock constructed at line 428; model_dump at line 434 |
| `skills/adapt/scripts/run.py` | `skills/adapt/lib/preflight.py + gh_client.py` | `run_preflight(repos_block, dry_run=dry_run, gh=FakeGhClient() if dry_run else RealGhClient())` | WIRED | run_preflight imported at line 42; called at line 246; FakeGhClient/RealGhClient imported at line 43 |
| `skills/adapt/scripts/validate_phase_completion.py` | `skills/adapt/lib/schema.py` | `from skills.adapt.lib.schema import LoopBlockOutput` (local import inside function) | WIRED | Line 78: local import inside _validate_loop_evidence; preserves zero-cost legacy path |
| `skills/adapt/lib/preflight.py` | `skills/adapt/lib/gh_client.py` | `gh.auth_status()`, `gh.repo_view()`, `gh.repo_permissions()`, `gh.branch_protection()` | WIRED | Lines 122, 129, 134, 137, 152; all 4 preflight methods called |
| `skills/adapt/lib/redact.py` | `skills/adapt/knowledge_base/redact_domains.yml` | `_INTERNAL_DOMAIN_CONFIG` path constant | WIRED | Line 27: path constant defined; domains loaded at call time via internal_domains param |
| `skills/adapt/tests/lib/test_run_cli.py` | `skills/adapt/scripts/run.py:main` | Subprocess invocation | WIRED | CLI tests invoke run.py via subprocess; 11 tests covering legacy, v2, partial flags, resume |
| `skills/adapt/tests/lib/test_preflight_dry_run.py` | `preflight.py + gh_client.py` | `run_preflight(..., gh=FakeGhClient(...))` | WIRED | 34 tests; FakeGhClient parameterized for failure modes |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `run.py` -> `run_inputs.yml` | `repos_dict`, `loop_dict` | CLI args parsed via argparse -> ReposBlock.model_dump() / LoopBudget().model_dump() | Yes: Pydantic-validated URL strings + budget defaults from Field() | FLOWING |
| `run.py` -> preflight | `repos_block` | ReposBlock constructed from CLI args at line 428 | Yes: ReposBlock.model_validate succeeds before preflight call | FLOWING |
| `preflight.py` -> PreflightResult | `failures`, `warnings` | FakeGhClient/RealGhClient responses -> conditional appends | Yes: auth_status, repo_view, repo_permissions, branch_protection produce real failure/warning strings | FLOWING |
| `validate_phase_completion.py` -> _validate_loop_evidence | `loop_block` from phaseN_output.yml | YAML load -> LoopBlockOutput.model_validate | Yes: reads from actual YAML file, validates via Pydantic | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Schema v1/v2 round-trip | Python inline: RunInputs.model_validate(v1_data/v2_data) | v1.loop_engineering_enabled=False, v2=True | PASS |
| Redactor patterns | Python inline: redact() with Bearer, ghp_, hf_ | Correct [REDACTED:*] replacements, accept=True | PASS |
| GhClient Protocol shape | Python inline: dir(GhClient) | 10 methods present; RealGhClient stubs raise NotImplementedError("Phase 2") | PASS |
| JSONL append-only | Python inline: append_attempt x2, assert_append_only | 2 lines, trailing newline, O_APPEND survives truncation | PASS |
| LoopBudget ceilings | Python inline: LoopBudget(max_attempts_per_phase=51) | ValidationError raised for all 3 ceiling violations | PASS |
| CLI legacy round-trip | subprocess: loongforge-adapt /tmp/m | Exit 0, run_inputs.yml has source/paths/options, no repos/loop | PASS |
| CLI v2 round-trip | subprocess: loongforge-adapt + 8 URL flags + --dry-run | Exit 0, run_inputs.yml has repos (4 sub-blocks) + loop (4 budget fields) | PASS |
| Partial URL flags rejected | subprocess: --hf-impl-url only | Exit != 0, stderr contains "must all be provided together" | PASS |
| _validate_loop_evidence inert | Python inline: validate_phase_output with legacy output | No exception (inert when loop_engineering absent) | PASS |
| Preflight dry_run skips writes | Python inline: run_preflight(dry_run=True, gh=FakeGhClient()) | ok=True, no repo_permissions calls recorded | PASS |
| Full test suite | python3 -m pytest skills/adapt/tests/ -q --tb=no | 163 passed in 10.44s | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INPUT-01 | Plan 03 | Skill at startup collects four URL inputs | SATISFIED | 8 CLI flags in run.py (lines 354-367); all-or-nothing validation (lines 384-390) |
| INPUT-02 | Plan 03 | `run_inputs.yml` extended with `repos:` block | SATISFIED | ReposBlock model_validate + model_dump in run.py; repos block written to YAML |
| INPUT-03 | Plan 02 | Pre-flight checks at startup: gh auth, write perms, ckpt URL, branch protection | SATISFIED | run_preflight() in preflight.py; test_preflight_dry_run.py with 34 tests |
| INPUT-04 | Plan 02, 03 | `--dry-run` flag wired; FakeGhClient selected; preflight skips live-write probes | SATISFIED | --dry-run flag in run.py line 370; FakeGhClient selection line 244; dry_run=True skips repo_permissions/branch_protection |
| LOG-02 | Plan 01 | `phaseN_output.yml` extended with optional `pr`, `issues`, `loop`, `loop_engineering: true` blocks | SATISFIED | LoopBlockOutput, PrBlockOutput, IssuesBlockOutput in schema.py; extra="ignore" on PrBlockOutput/IssuesBlockOutput for forward-compat |
| LOG-03 | Plan 01 | Append-only writes to `attempts.jsonl` | SATISFIED | jsonl.py: O_APPEND + fsync; assert_append_only test helper; test_jsonl_append_only.py: 6 tests |
| SAFE-01 | Plan 01 | Mandatory redaction filter on every body posted to GitHub | SATISFIED | redact.py: 10 hardcoded patterns + internal_domains; residual post-check returns accept=False |
| SAFE-02 | Plan 04 | `loop_controller.py` never invokes `/loop`; lint check fails build | SATISFIED | test_loop_lint.py: 2 tests (scan + positive control); INVOKE_PATTERNS regexes |
| SAFE-03 | Plan 04 | Bulk log content externalized to files; only excerpts in chat context | SATISFIED | SKILL.md line 143: "Bulk Log Externalization (SAFE-03)" section |
| COMPAT-02 | Plan 03 | `run_state.json` legacy fields untouched | SATISFIED | test_run_cli.py: TestLegacyStateCompat verifies same key set; no repos/loop in run_state.json |
| COMPAT-03 | Plan 04 | Existing Phase 0-5 validator logic unchanged; `_validate_loop_evidence()` inert when flag absent | SATISFIED | test_validate_loop_evidence.py: TestLegacyCompat passes; _validate_loop_evidence returns early when loop_engineering is not True |
| TEST-02 | Plan 01 | Snapshot tests on redaction filter | SATISFIED | test_redact.py: 15 tests including multi-pattern corpus; individual pattern tests; residual check |
| TEST-03 | Plan 01 | Round-trip test for `run_inputs.yml v2` (with and without `repos:` block) | SATISFIED | test_schema.py: test_legacy_v1_round_trip + test_v2_round_trip; test_run_cli.py: TestLegacyInvocation + TestV2Invocation |

**Orphaned requirements:** None. All 13 requirement IDs mapped to Phase 1 in ROADMAP.md appear in at least one plan's `requirements` field.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `skills/adapt/lib/gh_client.py` | 65, 69, 74, 78 | `return {}` | Info | Correct behavior: empty dict on error/404 in repo_permissions and branch_protection; not a stub |

No TODO/FIXME/HACK/PLACEHOLDER comments found. No console.log-only implementations. No hardcoded empty props passed to rendered components.

The 6 `NotImplementedError("Phase 2")` in RealGhClient are intentional Phase 2 stubs per the Protocol-first design; FakeGhClient correctly implements all 10 methods with recording and ok-shaped returns.

### Human Verification Required

### 1. Visual review of preflight error messages

**Test:** Run `loongforge-adapt /tmp/m --hf-impl-url https://github.com/huggingface/transformers --hf-ckpt-url https://huggingface.co/x/y --loongforge-repo https://github.com/Zachary-wW/LoongForge --megatron-repo https://github.com/Zachary-wW/Loong-Megatron` on a machine without `gh` auth configured
**Expected:** Clear, actionable error message with "PREFLIGHT FAILED:" header and "Re-run with --dry-run" hint
**Why human:** Error message clarity is subjective; programmatic check only verifies the string contains expected substrings

### 2. Branch protection real-world behavior

**Test:** Run preflight against a real GitHub repo with actual branch protection rules
**Expected:** Correct classification of hard-fail vs warn-only items
**Why human:** Requires real `gh` CLI access and a repo with complex branch protection rules; FakeGhClient tests cover the logic but not real GitHub API behavior

### Gaps Summary

No gaps found. All 6 observable truths verified, all 11 required artifacts exist and are substantive, all 7 key links are wired, data flows through the pipeline correctly, all 13 requirements are satisfied, and no blocking anti-patterns were detected. The 163 tests all pass.

The phase delivers what it promises: foundation plumbing (schemas, redactor, JSONL writer, protected paths, GhClient interface, preflight, CLI extension, validator hook, /loop lint, SAFE-03 doc note) that later phases can layer on without rewriting.

---

_Verified: 2026-06-22T09:30:00Z_
_Verifier: Claude (gsd-verifier)_
