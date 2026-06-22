---
phase: 01-loop-foundation-contracts-schemas-safety-plumbing
plan: 03
type: execute
wave: 2
depends_on:
  - "01-loop-foundation-contracts-schemas-safety-plumbing/01"
  - "01-loop-foundation-contracts-schemas-safety-plumbing/02"
files_modified:
  - skills/adapt/scripts/run.py
  - skills/adapt/tests/lib/test_run_cli.py
autonomous: true
requirements:
  - INPUT-01
  - INPUT-02
  - INPUT-04
  - COMPAT-02
must_haves:
  truths:
    - "loongforge-adapt --hf-impl-url ... --hf-ckpt-url ... --loongforge-repo ... --megatron-repo ... --dry-run produces a run_inputs.yml with both `repos:` (with all 4 sub-blocks) and `loop:` (with 4 budget fields) blocks."
    - "Legacy invocation `loongforge-adapt <hf_path>` (no URL flags) still produces a valid run_inputs.yml WITHOUT `repos:` and WITHOUT `loop:`."
    - "Providing some-but-not-all URL flags triggers parser.error: '--hf-impl-url, --hf-ckpt-url, --loongforge-repo, --megatron-repo must all be provided together'."
    - "Preflight is invoked from init_run_dir when repos: is built; --resume path does NOT call run_preflight."
    - "W5: a runtime test asserts the v2-init code path triggers run_preflight() (via a tracable monkeypatched stub setting a module flag) AND a subsequent --resume of the same run_dir does NOT trigger it."
    - "run_state.json legacy fields are unchanged (COMPAT-02): same key set as before."
  artifacts:
    - path: "skills/adapt/scripts/run.py"
      provides: "Extended CLI: 8 URL flags + --dry-run; _build_run_inputs accepts repos/loop kwargs; init_run_dir invokes preflight (skipped on --resume)."
    - path: "skills/adapt/tests/lib/test_run_cli.py"
      provides: "Round-trip CLI tests: legacy v1 invocation and v2 invocation with all flags + --dry-run."
  key_links:
    - from: "skills/adapt/scripts/run.py"
      to: "skills/adapt/lib/schema.py"
      via: "import RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget"
      pattern: "from skills\\.adapt\\.lib\\.schema import"
    - from: "skills/adapt/scripts/run.py"
      to: "skills/adapt/lib/preflight.py + skills/adapt/lib/gh_client.py"
      via: "run_preflight(repos, dry_run=args.dry_run, gh=FakeGhClient() if args.dry_run else RealGhClient())"
      pattern: "run_preflight"
    - from: "skills/adapt/tests/lib/test_run_cli.py"
      to: "skills/adapt/scripts/run.py:main"
      via: "subprocess invocation of python -m skills.adapt.scripts.run"
      pattern: "skills\\.adapt\\.scripts\\.run|scripts/run\\.py"
---

<objective>
Extend `skills/adapt/scripts/run.py` with the 8 URL flags + `--dry-run` from RESEARCH §3, build `repos:` and `loop:` blocks in `_build_run_inputs`, and call `run_preflight` from `init_run_dir` (NOT from the `--resume` path). Backward compat MUST hold: the legacy positional `hf_path` invocation continues to produce a valid run dir without `repos:`/`loop:` blocks.

Purpose: This is the user-facing surface for INPUT-01 (4 URL inputs collected) + INPUT-02 (run_inputs.yml extended with `repos:` block) + INPUT-04 (`--dry-run` substrate). COMPAT-02 demands `run_state.json` legacy fields untouched.

Output: Extended `run.py` + 1 new CLI test covering legacy and v2 invocations.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md
@skills/adapt/scripts/run.py
@skills/adapt/tests/test_plugin_layout.py
@skills/adapt/lib/schema.py
@skills/adapt/lib/preflight.py
@skills/adapt/lib/gh_client.py

<interfaces>
<!-- From plan 01 (RESEARCH §2): RunInputs / ReposBlock / LoopBudget. Use these for in-memory validation
     and for typing kwargs to _build_run_inputs. -->
```python
from skills.adapt.lib.schema import (
    RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget,
)
```

<!-- From plan 02 (RESEARCH §4, §10): preflight + gh client substrate. -->
```python
from skills.adapt.lib.preflight import run_preflight, format_failures, PreflightResult
from skills.adapt.lib.gh_client import GhClient, RealGhClient, FakeGhClient
```

<!-- Existing run.py exit codes / patterns:
     - BLOCK_EXIT_CODE = 2 (validate_phase_completion.py:17)
     - argparse.ArgumentParser → mutually exclusive group on hf_path / --resume
     - main() returns None today; subprocess tests check returncode == 0
-->
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 3.1: Add 8 URL flags + --dry-run; build repos/loop blocks; wire preflight from init path</name>
  <read_first>
    - skills/adapt/scripts/run.py (full file — argparse setup at lines 285-372, _build_run_inputs at 35-67, init_run_dir at 186-217)
    - .planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/01-RESEARCH.md (§3 CLI surface lines 153-193, §4 preflight integration)
    - skills/adapt/tests/test_plugin_layout.py (test_plugin_runner_cli_smoke at line 493, test_resume_from_phase_does_not_require_existing_legacy_state at line 511 — these MUST keep passing)
  </read_first>
  <behavior>
    - Test (legacy positional only): `python -m skills.adapt.scripts.run /tmp/m --run-dir <tmp>` exits 0; `<tmp>/run_inputs.yml` is parseable YAML; the dict has keys `{source, paths, options}` and does NOT have `repos` or `loop`.
    - Test (all 4 URL flags + --dry-run): `python -m skills.adapt.scripts.run /tmp/m --run-dir <tmp> --hf-impl-url https://github.com/huggingface/transformers --hf-ckpt-url https://huggingface.co/x/y --loongforge-repo https://github.com/Zachary-wW/LoongForge --megatron-repo https://github.com/Zachary-wW/Loong-Megatron --dry-run` exits 0; `run_inputs.yml` has BOTH `repos:` (with `hf_impl.url`, `hf_ckpt.url`, `loongforge.url`, `megatron.url` set to the provided URLs) AND `loop:` (with `max_attempts_per_phase`, `max_attempts_per_run`, `max_wallclock_minutes`, `escalation` defaults).
    - Test (partial URL flags rejected): supplying ONLY `--hf-impl-url ...` (without the other 3) exits non-zero with stderr containing `"--hf-impl-url, --hf-ckpt-url, --loongforge-repo, --megatron-repo must all be provided together"`.
    - Test (resume skips preflight, legacy form — pre-existing): `--resume <existing_run_dir>` does NOT call `run_preflight`; subprocess call exits 0 even with no network and no `gh` CLI installed (FakeGhClient is not used here — preflight just isn't called).
    - Test (W5 — v2 init triggers preflight, --resume does NOT, runtime-traced): an in-process pytest test that:
        1. Monkey-patches `skills.adapt.scripts.run.run_preflight` with a stub that sets a module-level boolean flag (`_preflight_called = True`) and returns a fake `PreflightResult(ok=True, failures=[], warnings=[], branch_protection={})`.
        2. Monkey-patches `skills.adapt.scripts.run.RealGhClient` and `skills.adapt.scripts.run.FakeGhClient` to no-op constructors so no real network/gh is touched.
        3. Calls `main([hf_path, "--run-dir", str(tmp_path/"r"), "--hf-impl-url", "https://github.com/h/t", "--hf-ckpt-url", "https://huggingface.co/x/y", "--loongforge-repo", "https://github.com/a/b", "--megatron-repo", "https://github.com/c/d", "--dry-run"])` directly (no subprocess) — asserts `_preflight_called is True` after init.
        4. Resets `_preflight_called = False`, then calls `main([..., "--resume", str(tmp_path/"r")])` (or whatever the existing resume CLI shape is); asserts `_preflight_called is False` after resume.
      Equivalent factoring: if monkey-patching `run.run_preflight` directly is awkward (e.g. it's imported at function scope), factor the preflight call into a small wrapper function and patch that. The point is observable runtime tracing, not a subprocess black-box exit-code check.
    - Test (run_state.json legacy fields untouched, COMPAT-02): after the all-URL-flags invocation, `run_state.json` MUST contain exactly the legacy keys (`hf_path, model_name, run_dir, version, current_state, model_type, hf_modeling_path, omni_path, megatron_path, gpu_execution_mode, enable_slice_ckpt, k8s_yaml_path, k8s_launch_cmd, wip_code_paths, phases`) and MUST NOT have a top-level `repos` or `loop` key.
  </behavior>
  <action>
**Edit `skills/adapt/scripts/run.py`** with the following SPECIFIC changes (do not refactor unrelated code):

### Step A — Imports
Near the top, after existing `import yaml`, add:
```python
from skills.adapt.lib.schema import (
    RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget,
)
from skills.adapt.lib.preflight import run_preflight, format_failures
from skills.adapt.lib.gh_client import RealGhClient, FakeGhClient
```

### Step B — Extend `_build_run_inputs`
Add two new keyword args at the end of the existing signature: `repos: dict | None = None`, `loop: dict | None = None`. After building the existing return dict, conditionally inject:
```python
result = {
    "source": {...},
    "paths": {...},
    "options": {...},
}
if repos is not None:
    result["repos"] = repos
if loop is not None:
    result["loop"] = loop
return result
```

### Step C — Argparse: add 8 URL flags + --dry-run (place AFTER existing `--wip-code-paths` and BEFORE `--from-phase`)
Copy verbatim from RESEARCH §3 lines 156-176:
```python
repos_group = parser.add_argument_group("repos (loop engineering)")
repos_group.add_argument("--hf-impl-url", default=None,
    help="HF model impl repo URL (e.g. https://github.com/huggingface/transformers)")
repos_group.add_argument("--hf-impl-ref", default="main", help="HF impl branch/tag/sha")
repos_group.add_argument("--hf-impl-subpath", default=None,
    help="Path within HF impl repo (e.g. src/transformers/models/deepseek_v4)")
repos_group.add_argument("--hf-ckpt-url", default=None,
    help="HF Hub ckpt URL (e.g. https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base)")
repos_group.add_argument("--hf-ckpt-revision", default="main")
repos_group.add_argument("--loongforge-repo", default=None,
    help="LoongForge repo URL")
repos_group.add_argument("--loongforge-base-ref", default="main")
repos_group.add_argument("--megatron-repo", default=None,
    help="Loong-Megatron repo URL")
repos_group.add_argument("--megatron-base-ref", default="loong-main/core_v0.15.0")

dryrun_group = parser.add_argument_group("dry run")
dryrun_group.add_argument("--dry-run", action="store_true",
    help="Use FakeGhClient; skip live gh writes; still validate URL shape and schema")
```

### Step D — All-or-nothing URL validation (RESEARCH §3 lines 183-188)
After `args = parser.parse_args(argv)`, BEFORE the `if args.resume` branch:
```python
url_flags = [args.hf_impl_url, args.hf_ckpt_url, args.loongforge_repo, args.megatron_repo]
loop_engineering = any(url_flag is not None for url_flag in url_flags)
if loop_engineering and not all(url_flag is not None for url_flag in url_flags):
    parser.error(
        "--hf-impl-url, --hf-ckpt-url, --loongforge-repo, --megatron-repo "
        "must all be provided together"
    )
```

### Step E — Build repos/loop dicts when loop_engineering
Inside the `else` (init) branch of `main`, BEFORE calling `init_run_dir(...)`, build:
```python
repos_dict = None
loop_dict = None
if loop_engineering:
    # Validate URL shape via Pydantic (raises ValidationError on bad URL).
    repos_block = ReposBlock(
        hf_impl=HFImplSpec(url=args.hf_impl_url, ref=args.hf_impl_ref, subpath=args.hf_impl_subpath),
        hf_ckpt=HFCkptSpec(url=args.hf_ckpt_url, revision=args.hf_ckpt_revision),
        loongforge=RepoSpec(url=args.loongforge_repo, base_ref=args.loongforge_base_ref),
        megatron=RepoSpec(url=args.megatron_repo, base_ref=args.megatron_base_ref),
    )
    repos_dict = repos_block.model_dump(exclude_none=True, mode="json")
    loop_dict = LoopBudget().model_dump(mode="json")  # defaults: 5/25/240/human_needed
```

### Step F — Extend `init_run_dir` to accept repos/loop and to invoke preflight
Update `init_run_dir(...)` signature to accept `repos: dict | None = None`, `loop: dict | None = None`, `dry_run: bool = False`. Pass them through to `_build_run_inputs`. After `save_run_inputs(run_dir, inputs)` and BEFORE `save_legacy_state(...)`, add:
```python
if repos is not None:
    gh = FakeGhClient() if dry_run else RealGhClient()
    result = run_preflight(repos_block, dry_run=dry_run, gh=gh)
    if not result.ok:
        import sys
        print(format_failures(result), file=sys.stderr)
        raise SystemExit(2)
```
NOTE: `repos_block` must be reconstructed inside `init_run_dir` from the `repos` dict (`ReposBlock.model_validate(repos)`) since this function may be called from places that pass a dict not a model. Do this inside the `if repos is not None:` block.

### Step G — Wire init_run_dir call site
In `main()`, the existing `inputs = init_run_dir(hf_ckpt_path=..., model_name=..., run_dir=..., ...)` call: append `repos=repos_dict, loop=loop_dict, dry_run=args.dry_run`.

### Step H — `--resume` MUST NOT call preflight (RESEARCH §12 R4)
The `if args.resume:` branch in `main()` only calls `resume_run_dir(...)`. Do NOT add a preflight call there. Add a clarifying comment: `# Preflight is intentionally skipped on --resume; the original init already passed it.`

### Step I — `save_legacy_state` MUST NOT include repos/loop (COMPAT-02)
Inspect `_inputs_to_legacy_state` (lines 86-105). It already only reads `source/paths/options`. Do NOT add repos/loop reads. Verify by grep after editing.

### Step J — Create `skills/adapt/tests/lib/test_run_cli.py`
Cover all sub-tests in `<behavior>`. Use `subprocess.run([sys.executable, str(repo_root / "skills/adapt/scripts/run.py"), ...], capture_output=True, text=True, cwd=repo_root)` so imports work. Skip the "module" form to avoid PYTHONPATH issues — invoke run.py as a script. Set `env={**os.environ, "PYTHONPATH": str(repo_root)}` so `from skills.adapt.lib...` resolves.

For the partial-flags test, assert `result.returncode != 0` AND `"must all be provided together" in result.stderr`.

For the legacy resume-skip-preflight test, do an init invocation first (legacy form, no URL flags — so no preflight runs anyway), then a `--resume <run_dir>` invocation; assert exit 0. (We don't need to prove preflight was skipped for non-loop runs because preflight isn't called there to begin with; the test asserts the no-regression invariant.)

**W5 — runtime-traced v2 vs resume preflight test (NEW):** add an in-process pytest test (NOT subprocess) that imports `skills.adapt.scripts.run as run_mod` and monkey-patches `run_mod.run_preflight` to a tracer stub. To make this patchable, Step A's import MUST be `from skills.adapt.lib.preflight import run_preflight, format_failures` at MODULE level (not inside a function), so `run_mod.run_preflight` is the binding the code will call. The init_run_dir code site (Step F) MUST reference `run_preflight(...)` by bare name (resolved through the module's global), NOT re-import it locally — otherwise the monkey-patch won't take. Concretely:

```python
# in init_run_dir (Step F), use the MODULE-level name so monkey-patch on
# skills.adapt.scripts.run.run_preflight intercepts the call:
if repos is not None:
    gh = FakeGhClient() if dry_run else RealGhClient()
    repos_block = ReposBlock.model_validate(repos)
    result = run_preflight(repos_block, dry_run=dry_run, gh=gh)   # <-- module-level name
    if not result.ok:
        import sys
        print(format_failures(result), file=sys.stderr)
        raise SystemExit(2)
```

The W5 test (sketch):

```python
def test_v2_init_calls_preflight_resume_does_not(tmp_path, monkeypatch):
    import skills.adapt.scripts.run as run_mod
    from skills.adapt.lib.preflight import PreflightResult

    called = {"flag": False}
    def _trace(*args, **kwargs):
        called["flag"] = True
        return PreflightResult(ok=True, failures=[], warnings=[], branch_protection={})
    monkeypatch.setattr(run_mod, "run_preflight", _trace)

    rd = tmp_path / "r"
    run_mod.main([
        "/tmp/m", "--run-dir", str(rd),
        "--hf-impl-url", "https://github.com/h/t",
        "--hf-ckpt-url", "https://huggingface.co/x/y",
        "--loongforge-repo", "https://github.com/a/b",
        "--megatron-repo", "https://github.com/c/d",
        "--dry-run",
    ])
    assert called["flag"] is True, "v2-init path MUST invoke run_preflight"

    called["flag"] = False
    run_mod.main(["--resume", str(rd)])    # adapt to actual resume CLI shape
    assert called["flag"] is False, "--resume path MUST NOT invoke run_preflight"
```

If the actual `main()` signature differs (e.g. needs different positional placement for `--resume`), match the existing argparse layout. The acceptance criterion is observable monkey-patch tracing, not subprocess.
  </action>
  <verify>
    <automated>cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin && PYTHONPATH=. python3 -m pytest skills/adapt/tests/lib/test_run_cli.py skills/adapt/tests/test_plugin_layout.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "from skills.adapt.lib.schema import" skills/adapt/scripts/run.py` AND `grep -q "from skills.adapt.lib.preflight import run_preflight" skills/adapt/scripts/run.py` AND `grep -q "from skills.adapt.lib.gh_client import" skills/adapt/scripts/run.py`.
    - `grep -q "\\-\\-hf-impl-url" skills/adapt/scripts/run.py` AND `grep -q "\\-\\-hf-ckpt-url" skills/adapt/scripts/run.py` AND `grep -q "\\-\\-loongforge-repo" skills/adapt/scripts/run.py` AND `grep -q "\\-\\-megatron-repo" skills/adapt/scripts/run.py` AND `grep -q "\\-\\-dry-run" skills/adapt/scripts/run.py`.
    - `grep -q "must all be provided together" skills/adapt/scripts/run.py`.
    - `grep -q "ReposBlock(" skills/adapt/scripts/run.py` AND `grep -q "LoopBudget()" skills/adapt/scripts/run.py`.
    - `grep -q "run_preflight" skills/adapt/scripts/run.py`.
    - `grep -q "FakeGhClient() if" skills/adapt/scripts/run.py` (dry_run-aware client selection).
    - In the `if args.resume:` branch, NO call to `run_preflight` — verify with: `python3 -c "import re; src=open('skills/adapt/scripts/run.py').read(); resume_idx = src.index('if args.resume'); end_idx = src.index('else:', resume_idx); seg = src[resume_idx:end_idx]; assert 'run_preflight' not in seg, 'preflight must not be called on --resume'"`
    - W5 (runtime trace): the new test in `test_run_cli.py` (`test_v2_init_calls_preflight_resume_does_not` or equivalent) MUST pass — i.e. monkey-patching `skills.adapt.scripts.run.run_preflight` proves the v2-init path triggers it AND --resume does NOT.
    - W5 (module-level binding): `python3 -c "import skills.adapt.scripts.run as m; assert hasattr(m, 'run_preflight'), 'run_preflight must be a module-level attribute for monkey-patching'"` exits 0.
    - `python3 -m pytest skills/adapt/tests/lib/test_run_cli.py -x -q` exits 0.
    - `python3 -m pytest skills/adapt/tests/test_plugin_layout.py -x -q` still exits 0 (no regression).
    - Verify legacy run_state.json shape via grep: `grep -q "\"phases\":" skills/adapt/scripts/run.py` (exists), and `grep -q "\"repos\":" skills/adapt/scripts/run.py` returns nothing (we never wrote repos into legacy state).
  </acceptance_criteria>
  <done>CLI accepts 8 URL flags + --dry-run; legacy positional invocation still works; `repos:` + `loop:` blocks emitted to run_inputs.yml when loop-engineering; preflight invoked only on init (not --resume); run_state.json legacy schema unchanged; existing test_plugin_layout.py still passes.</done>
</task>

</tasks>

<verification>
After this task completes, run from repo root:

```
cd /Users/weizhihao/workspace/agent_skills/loongforge-plugin
PYTHONPATH=. python3 -m pytest skills/adapt/tests/ -x -q
```

ALL existing tests + the new `test_run_cli.py` MUST exit 0.

Manual smoke (optional):
```
PYTHONPATH=. python3 skills/adapt/scripts/run.py /tmp/model --run-dir /tmp/lf_legacy
PYTHONPATH=. python3 skills/adapt/scripts/run.py /tmp/model --run-dir /tmp/lf_v2 \
  --hf-impl-url https://github.com/huggingface/transformers \
  --hf-ckpt-url https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base \
  --loongforge-repo https://github.com/Zachary-wW/LoongForge \
  --megatron-repo https://github.com/Zachary-wW/Loong-Megatron \
  --dry-run
diff <(yq '.repos' /tmp/lf_legacy/run_inputs.yml) <(echo "null")    # legacy: no repos
yq '.repos.hf_impl.url' /tmp/lf_v2/run_inputs.yml                   # v2: prints URL
yq '.loop.max_attempts_per_phase' /tmp/lf_v2/run_inputs.yml         # 5
```
</verification>

<success_criteria>
- INPUT-01: 4 URL inputs collected via dedicated flags (8 flags total counting ref/subpath siblings).
- INPUT-02: `run_inputs.yml` extended with top-level `repos:` block carrying all four URLs; downstream phases read from this single source.
- INPUT-04: `--dry-run` flag wired; FakeGhClient selected when `--dry-run`; preflight skips remote-write checks but still validates URL shape + Pydantic schema.
- COMPAT-02: `run_state.json` legacy fields unchanged; new orchestration state lives in `run_inputs.yml` only.
- Existing layout/runner tests in `test_plugin_layout.py` still pass.
- New `test_run_cli.py` passes.
</success_criteria>

<output>
After completion, create `.planning/phases/01-loop-foundation-contracts-schemas-safety-plumbing/03-SUMMARY.md` summarizing:
- run.py edit diff regions (function names + line ranges touched)
- New CLI flag list with exact spelling
- Confirmation that preflight is NOT called from --resume (paste the relevant 3-5 lines)
- Test counts and pass status
</output>
