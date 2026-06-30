#!/usr/bin/env python3
"""
LoongForge Model Adaptation Runner.

Responsibilities: Initialize run_dir / write run_inputs.yml / load existing state /
      print next-step operation hints.
This runner does not execute Phase agents. Actual phase execution is driven by the Agent via the /loongforge:adapt plugin skill.

Usage:
  loongforge-adapt <hf_path> [--model-name <name>] [--run-dir <dir>]
  loongforge-adapt --resume <run_dir>

Optional configuration parameters:
  --hf-modeling-path <path>    HF network implementation path
  --omni-path <path>           LoongForge code root directory
  --megatron-path <path>       Megatron-LM code root directory
  --gpu-execution-mode <mode>  GPU execution mode: local_gpu (default) | k8s
  --enable-slice-ckpt <bool>   Whether to slice Checkpoint: true | false (default)
  --k8s-yaml-path <path>       K8s job YAML configuration file path
  --k8s-launch-cmd <cmd>       K8s job launch command
  --wip-code-paths <paths>    WIP reference implementation paths (path1|type1,path2|type2)
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

# When invoked via bin/loongforge-adapt, the project root is not on sys.path.
# Insert it so `from skills.adapt.lib.*` resolves correctly.
_PLUGIN_ROOT = str(Path(__file__).resolve().parents[3])  # .../loongforge-plugin
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

import yaml

from skills.adapt.lib.schema import (
    RunInputs, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec, LoopBudget,
)
from skills.adapt.lib.preflight import run_preflight, format_failures
from skills.adapt.lib.gh_client import RealGhClient, FakeGhClient
from skills.adapt.scripts.phase0_bootstrap import bootstrap_phase0


# -- run_inputs.yml schema ---------------------------------------------------

def _build_run_inputs(
    hf_ckpt_path: str,
    model_name: str,
    hf_modeling_path: str = "",
    hf_transformers_path: str = "",
    omni_path: str = "",
    megatron_path: str = "",
    gpu_execution_mode: str = "local_gpu",
    enable_slice_ckpt: str = "false",
    k8s_yaml_path: str = "",
    k8s_launch_cmd: str = "",
    wip_code_paths: str = "",
    repos: dict | None = None,
    loop: dict | None = None,
    schema_version: str = "2",
) -> dict:
    """Build the run_inputs.yml dict from collected parameters."""
    result = {
        "schema_version": schema_version,
        "source": {
            "hf_ckpt_path": hf_ckpt_path,
        },
        "paths": {
            "hf_modeling_path": hf_modeling_path,
            "hf_transformers_path": hf_transformers_path,
            "omni_path": omni_path,
            "megatron_path": megatron_path,
        },
        "options": {
            "model_name": model_name,
            "gpu_execution_mode": gpu_execution_mode,
            "enable_slice_ckpt": enable_slice_ckpt,
            "k8s_yaml_path": k8s_yaml_path,
            "k8s_launch_cmd": k8s_launch_cmd,
            "wip_code_paths": wip_code_paths,
        },
    }
    if repos is not None:
        result["repos"] = repos
    if loop is not None:
        result["loop"] = loop
    return result


def save_run_inputs(run_dir: str, inputs: dict) -> None:
    """Write run_inputs.yml to run_dir."""
    path = Path(run_dir) / "run_inputs.yml"
    path.write_text(yaml.dump(inputs, default_flow_style=False, allow_unicode=True, sort_keys=False))


def load_run_inputs(run_dir: str) -> dict:
    """Load run_inputs.yml from run_dir."""
    path = Path(run_dir) / "run_inputs.yml"
    if not path.exists():
        raise FileNotFoundError(f"run_inputs.yml not found in {run_dir}")
    return yaml.safe_load(path.read_text())


# -- Legacy run_state.json (backward compat during migration) ----------------

def _inputs_to_legacy_state(run_dir: str, inputs: dict, current_state: str = "INIT", phases: dict | None = None) -> dict:
    """Convert run_inputs dict to legacy run_state.json format."""
    wip_raw = inputs.get("options", {}).get("wip_code_paths", "")
    return {
        "hf_path": inputs.get("source", {}).get("hf_ckpt_path", ""),
        "model_name": inputs.get("options", {}).get("model_name", ""),
        "run_dir": run_dir,
        "version": "2.0",
        "current_state": current_state,
        "model_type": "llm",
        "hf_modeling_path": inputs.get("paths", {}).get("hf_modeling_path", ""),
        "omni_path": inputs.get("paths", {}).get("omni_path", ""),
        "megatron_path": inputs.get("paths", {}).get("megatron_path", ""),
        "gpu_execution_mode": inputs.get("options", {}).get("gpu_execution_mode", "local_gpu"),
        "enable_slice_ckpt": inputs.get("options", {}).get("enable_slice_ckpt", "false"),
        "k8s_yaml_path": inputs.get("options", {}).get("k8s_yaml_path", ""),
        "k8s_launch_cmd": inputs.get("options", {}).get("k8s_launch_cmd", ""),
        "wip_code_paths": wip_raw,
        "phases": phases or {},
    }


def save_legacy_state(run_dir: str, inputs: dict, current_state: str = "INIT", phases: dict | None = None) -> None:
    """Write run_state.json for backward compatibility."""
    path = Path(run_dir) / "run_state.json"
    state = _inputs_to_legacy_state(run_dir, inputs, current_state, phases)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def load_legacy_state(run_dir: str) -> dict:
    """Load legacy run_state.json."""
    path = Path(run_dir) / "run_state.json"
    if not path.exists():
        raise FileNotFoundError(f"run_state.json not found in {run_dir}")
    return json.loads(path.read_text())


def _legacy_state_to_inputs(state: dict) -> dict:
    """Convert legacy run_state.json fields into run_inputs.yml schema."""
    return _build_run_inputs(
        hf_ckpt_path=state.get("hf_path", ""),
        model_name=state.get("model_name", ""),
        hf_modeling_path=state.get("hf_modeling_path", ""),
        hf_transformers_path=state.get("hf_transformers_path", ""),
        omni_path=state.get("omni_path", ""),
        megatron_path=state.get("megatron_path", ""),
        gpu_execution_mode=state.get("gpu_execution_mode", "local_gpu"),
        enable_slice_ckpt=state.get("enable_slice_ckpt", "false"),
        k8s_yaml_path=state.get("k8s_yaml_path", ""),
        k8s_launch_cmd=state.get("k8s_launch_cmd", ""),
        wip_code_paths=state.get("wip_code_paths", ""),
    )


def load_or_backfill_run_inputs(run_dir: str) -> dict:
    """Load run_inputs.yml, or backfill it from legacy run_state.json when needed."""
    try:
        return load_run_inputs(run_dir)
    except FileNotFoundError:
        legacy = load_legacy_state(run_dir)
        inputs = _legacy_state_to_inputs(legacy)
        save_run_inputs(run_dir, inputs)
        return inputs


# -- Phase output helpers ----------------------------------------------------

def phase_output_path(run_dir: str, phase_num: int) -> Path:
    """Return the authoritative phase handoff path."""
    return Path(run_dir) / "phases" / f"phase{phase_num}_output.yml"


def legacy_phase_output_path(run_dir: str, phase_num: int) -> Path:
    """Return the legacy phase-local output path."""
    return Path(run_dir) / "phases" / f"phase{phase_num}" / "output.yml"


def get_phase_status(run_dir: str, phase_num: int) -> str | None:
    """Read phase status from the authoritative handoff, falling back to legacy output.yml."""
    path = phase_output_path(run_dir, phase_num)
    if not path.exists():
        path = legacy_phase_output_path(run_dir, phase_num)
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text())
    return data.get("status")


def clear_phase_output(run_dir: str, phase_num: int) -> None:
    """Remove phase handoff files and attempts journal for the given phase."""
    for output_yml in (phase_output_path(run_dir, phase_num), legacy_phase_output_path(run_dir, phase_num)):
        if output_yml.exists():
            output_yml.unlink()
    phase_dir = Path(run_dir) / "phases" / f"phase{phase_num}"
    for transient in ("attempts.jsonl", "loop_state.yml", "escalation.md"):
        path = phase_dir / transient
        if path.exists():
            path.unlink()


# -- Init / Resume -----------------------------------------------------------

def init_run_dir(
    hf_ckpt_path: str,
    model_name: str,
    run_dir: str,
    repos: dict | None = None,
    loop: dict | None = None,
    dry_run: bool = False,
    **cli_kwargs,
) -> dict:
    """Create run_dir, write run_inputs.yml and legacy run_state.json, return inputs dict."""
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    phases_dir = Path(run_dir) / "phases"
    for i in range(7):
        phase_dir = phases_dir / f"phase{i}"
        phase_dir.mkdir(parents=True, exist_ok=True)
        # Create logs subdirectory for Phase 1-5
        if 1 <= i <= 5:
            (phase_dir / "logs").mkdir(parents=True, exist_ok=True)

    inputs = _build_run_inputs(
        hf_ckpt_path=hf_ckpt_path,
        model_name=model_name,
        hf_modeling_path=cli_kwargs.get("hf_modeling_path", ""),
        hf_transformers_path=cli_kwargs.get("hf_transformers_path", ""),
        omni_path=cli_kwargs.get("omni_path", ""),
        megatron_path=cli_kwargs.get("megatron_path", ""),
        gpu_execution_mode=cli_kwargs.get("gpu_execution_mode", "local_gpu"),
        enable_slice_ckpt=cli_kwargs.get("enable_slice_ckpt", "false"),
        k8s_yaml_path=cli_kwargs.get("k8s_yaml_path", ""),
        k8s_launch_cmd=cli_kwargs.get("k8s_launch_cmd", ""),
        wip_code_paths=cli_kwargs.get("wip_code_paths", ""),
        repos=repos,
        loop=loop,
        schema_version="2",
    )
    save_run_inputs(run_dir, inputs)
    # Preflight: only when repos is present (loop-engineering mode).
    # Must run after save_run_inputs so the run_dir exists for diagnostics.
    if repos is not None:
        gh = FakeGhClient() if dry_run else RealGhClient()
        repos_block = ReposBlock.model_validate(repos)
        result = run_preflight(repos_block, dry_run=dry_run, gh=gh)
        if not result.ok:
            import sys
            print(format_failures(result), file=sys.stderr)
            raise SystemExit(2)
    save_legacy_state(run_dir, inputs, current_state="INIT")
    return inputs


def resume_run_dir(run_dir: str, from_phase: int | None = None) -> dict:
    """Load run_inputs.yml, optionally backfill from legacy state, and clear phase outputs from from_phase onward."""
    inputs = load_or_backfill_run_inputs(run_dir)
    sv = inputs.get("schema_version", 1)
    if sv != 2:
        print(f"[WARNING] Run directory has schema_version={sv} (expected 2). "
              f"Phase numbering has changed: Phase 4 is now Performance Tuning, "
              f"Phase 5 is Feature Compat, Phase 6 is KB Update. "
              f"Use --from-phase 4 to reset from the new Phase 4.",
              file=sys.stderr)
    if from_phase is not None:
        for phase_num in range(from_phase, 7):
            clear_phase_output(run_dir, phase_num)
        # Also clear legacy phase keys when legacy state exists. Missing
        # run_state.json is allowed because run_inputs.yml is authoritative.
        try:
            legacy = load_legacy_state(run_dir)
        except FileNotFoundError:
            save_legacy_state(run_dir, inputs, current_state=f"PHASE{from_phase}_RUNNING")
        else:
            for phase_num in range(from_phase, 7):
                legacy.get("phases", {}).pop(f"phase{phase_num}", None)
            legacy["current_state"] = f"PHASE{from_phase}_RUNNING"
            Path(run_dir, "run_state.json").write_text(
                json.dumps(legacy, indent=2, ensure_ascii=False)
            )
    return inputs


# -- Display -----------------------------------------------------------------

_SEP = "-" * 50


def print_context(run_dir: str, inputs: dict) -> None:
    """Print run context and next-step hint."""
    src = inputs.get("source", {})
    paths = inputs.get("paths", {})
    opts = inputs.get("options", {})

    wip_display = "(none)"
    wip_raw = opts.get("wip_code_paths", "")
    if wip_raw:
        try:
            wip_entries = json.loads(wip_raw)
            wip_display = ", ".join(f"{e['path']} ({e['type']})" for e in wip_entries)
        except (json.JSONDecodeError, KeyError):
            wip_display = wip_raw

    print(
        f"\n{_SEP}\n"
        f"Run dir:        {run_dir}\n"
        f"HF ckpt path:   {src.get('hf_ckpt_path', '')}\n"
        f"Model:          {opts.get('model_name', '')}\n"
        f"\nStartup Configuration:\n"
        f"  HF Network Path:      {paths.get('hf_modeling_path', '') or '(not set)'}\n"
        f"  HF Transformers Path: {paths.get('hf_transformers_path', '') or '(not set)'}\n"
        f"  Omni Path:            {paths.get('omni_path', '') or '(not set)'}\n"
        f"  Megatron Path:        {paths.get('megatron_path', '') or '(not set)'}\n"
        f"  GPU Execution Mode:   {opts.get('gpu_execution_mode', 'local_gpu')}\n"
        f"  Slice Ckpt:           {opts.get('enable_slice_ckpt', 'false')}\n"
        f"  K8s YAML:             {opts.get('k8s_yaml_path', '') or '(not set)'}\n"
        f"  K8s Command:          {opts.get('k8s_launch_cmd', '') or '(not set)'}\n"
        f"  WIP Code:             {wip_display}\n"
        f"\nNext step: continue with /loongforge:adapt.\n"
        f"Legacy note: run_state.json is written for backward compatibility; run_inputs.yml and phase outputs are authoritative.\n"
        f"{_SEP}\n"
    )


def run_phase0_bootstrap(run_dir: str) -> None:
    """Generate deterministic Phase 0 artifacts for local, non-agent runs."""
    outputs = bootstrap_phase0(Path(run_dir))
    print("[Phase0 bootstrap] Wrote static analysis artifacts:")
    for name, path in outputs.items():
        print(f"  {name}: {path}")


# -- CLI ---------------------------------------------------------------------

def main(argv=None):
    """main"""
    parser = argparse.ArgumentParser(description="LoongForge Model Adaptation Runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("hf_path", nargs="?", help="HF model local path")
    group.add_argument("--resume", metavar="RUN_DIR", help="Load state from specified run_dir")
    parser.add_argument("--model-name", default=None)
    parser.add_argument("--run-dir", default=None)
    # Pre-startup information collection parameters
    parser.add_argument("--hf-modeling-path", default=None, help="HF network implementation path (modeling_*.py)")
    parser.add_argument("--hf-transformers-path", default=None, help="Local Transformers source tree path")
    parser.add_argument("--omni-path", default=None, help="LoongForge code root directory")
    parser.add_argument("--megatron-path", default=None, help="Megatron-LM code root directory")
    parser.add_argument(
        "--gpu-execution-mode",
        choices=["local_gpu", "k8s"],
        default="local_gpu",
        help="GPU execution mode: local_gpu (local GPU) or k8s (Kubernetes job)",
    )
    parser.add_argument(
        "--enable-slice-ckpt",
        choices=["true", "false"],
        default="false",
        help="Whether to slice Checkpoint to accelerate iteration (default false)",
    )
    parser.add_argument("--k8s-yaml-path", default=None, help="K8s job YAML configuration file path")
    parser.add_argument("--k8s-launch-cmd", default=None, help="K8s job launch command")
    parser.add_argument(
        "--wip-code-paths",
        default=None,
        help="WIP reference implementation paths, format: path1|type1,path2|type2 (type: megatron|hf_transformers|omni|other)",
    )

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

    parser.add_argument(
        "--from-phase",
        type=str,
        choices=["0", "1", "2", "3", "4", "5", "6"],
        default=None,
        metavar="N",
        help="Used with --resume, restart from the specified phase (0/1/2/3/4/5/6)",
    )
    parser.add_argument(
        "--bootstrap-phase0",
        action="store_true",
        help="Generate deterministic Phase 0 analysis artifacts after init/resume. "
             "This is a local fallback when /loongforge:adapt phase agents are unavailable.",
    )
    args = parser.parse_args(argv)

    # All-or-nothing URL validation: if any URL flag is provided, all four must be.
    url_flags = [args.hf_impl_url, args.hf_ckpt_url, args.loongforge_repo, args.megatron_repo]
    loop_engineering = any(url_flag is not None for url_flag in url_flags)
    if loop_engineering and not all(url_flag is not None for url_flag in url_flags):
        parser.error(
            "--hf-impl-url, --hf-ckpt-url, --loongforge-repo, --megatron-repo "
            "must all be provided together"
        )

    if args.resume:
        # Preflight is intentionally skipped on --resume; the original init already passed it.
        from_phase = int(args.from_phase) if args.from_phase is not None else None
        inputs = resume_run_dir(args.resume, from_phase=from_phase)
        print(f"[Resume] State loaded: {args.resume}")

        # Reconciliation: verify remote PR/issue state matches local records (RESUME-02).
        # Skip when --from-phase is specified (user explicitly resetting).
        repos_block = inputs.get("repos")
        if repos_block is not None and from_phase is None:
            from skills.adapt.lib.resume import reconcile_run, ReconciliationMismatch
            from skills.adapt.lib.gh_client import RealGhClient
            gh = RealGhClient()
            loongforge_repo = repos_block.get("loongforge", {}).get("url", "")
            # Extract owner/repo from URL for reconciliation
            if "github.com" in loongforge_repo:
                parts = loongforge_repo.rstrip("/").split("/")
                owner_repo = "/".join(parts[-2:]) if len(parts) >= 2 else ""
            else:
                owner_repo = ""
            repos_info = {"loongforge_repo": owner_repo} if owner_repo else None
            mismatches = reconcile_run(Path(args.resume), from_phase, gh, repos_info=repos_info)
            if mismatches:
                print("[Reconciliation] Remote state mismatches detected:", file=sys.stderr)
                for m in mismatches:
                    print(f"  - {m.artifact_type} #{m.number}: {m.issue} -- {m.detail}", file=sys.stderr)
                print("Use --from-phase N to reset from the affected phase.", file=sys.stderr)
                raise SystemExit(3)

        if from_phase is not None:
            print(f"[Reset] Starting from Phase {from_phase}; cleared stale phase results from Phase {from_phase} onward")
        if args.bootstrap_phase0:
            run_phase0_bootstrap(args.resume)
        print_context(args.resume, inputs)
    else:
        if not args.hf_path:
            parser.error("hf_path or --resume must be provided")
        run_dir = (
            args.run_dir
            or f"adaptation_run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        model_name = args.model_name or Path(args.hf_path).name

        # Parse wip_code_paths
        wip_code_paths = ""
        if args.wip_code_paths:
            entries = []
            for entry in args.wip_code_paths.split(","):
                parts = entry.split("|", 1)
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    parser.error(
                        f"Invalid --wip-code-paths entry: '{entry}', "
                        f"format should be path|type (e.g. /home/user/Megatron|megatron)"
                    )
                entries.append({"path": parts[0], "type": parts[1]})
            wip_code_paths = json.dumps(entries)

        # Build repos/loop dicts when loop_engineering is enabled
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

        inputs = init_run_dir(
            hf_ckpt_path=args.hf_path,
            model_name=model_name,
            run_dir=run_dir,
            hf_modeling_path=args.hf_modeling_path or "",
            hf_transformers_path=args.hf_transformers_path or "",
            omni_path=args.omni_path or "",
            megatron_path=args.megatron_path or "",
            gpu_execution_mode=args.gpu_execution_mode,
            enable_slice_ckpt=args.enable_slice_ckpt,
            k8s_yaml_path=args.k8s_yaml_path or "",
            k8s_launch_cmd=args.k8s_launch_cmd or "",
            wip_code_paths=wip_code_paths,
            repos=repos_dict,
            loop=loop_dict,
            dry_run=args.dry_run,
        )
        if args.bootstrap_phase0:
            run_phase0_bootstrap(run_dir)
        print(f"[Initialized] run_dir created: {run_dir}")
        print_context(run_dir, inputs)


if __name__ == "__main__":
    main()
