#!/usr/bin/env python3
"""Deterministic LoongForge adaptation phase completion gate.

Phase 0 validation checks the three-document output (hf_analysis,
reference_impl_analysis, bridge_mapping) as of v2.

This script checks phase output artifacts that were already produced by phase
agents. It does not run model validation, GPU jobs, or agentic reviews.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


BLOCK_EXIT_CODE = 2


def _load_phase_output(run_dir: Path, phase: int) -> dict[str, Any]:
    output_path = run_dir / "phases" / f"phase{phase}_output.yml"
    if not output_path.exists():
        raise ValueError(f"Missing phase output: {output_path}")
    data = yaml.safe_load(output_path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Invalid phase output YAML: {output_path}")
    return data


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _nested(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _validate_step_gate(data: dict[str, Any]) -> None:
    """Validate phase-internal step completion evidence."""
    step_gate = data.get("step_gate")
    _expect(isinstance(step_gate, dict), "step_gate evidence must be present")
    _expect(
        step_gate.get("mandatory_steps_complete") is True,
        "step_gate.mandatory_steps_complete must be true",
    )

    steps = data.get("steps")
    _expect(isinstance(steps, dict) and bool(steps), "steps evidence must be present")
    for step_name, step in steps.items():
        _expect(isinstance(step, dict), f"steps.{step_name} must be an object")
        required = step.get("required", True)
        status = step.get("status")
        if required is False and status == "skipped":
            _expect(bool(step.get("reason")), f"steps.{step_name}.reason must explain skipped optional step")
            continue
        _expect(status == "passed", f"steps.{step_name}.status must be passed")
        _expect(bool(step.get("evidence")), f"steps.{step_name}.evidence must be present")


def _validate_loop_evidence(data: dict[str, Any]) -> None:
    """When loop_engineering: true, validate loop block + integrity checks.

    When loop_engineering: true is set, this is where future checks for
    PR-merged status, validator-binary hash, log-mtime, attempts.jsonl
    presence, etc. will live (per VAL-04, REQ-LOG-01)."""
    if data.get("loop_engineering") is not True:
        return  # legacy output: skip silently
    # Phase 3 will populate the body. Phase 1 just asserts the optional
    # `loop:` block, if present, parses cleanly through Pydantic.
    loop_block = data.get("loop")
    if loop_block is not None:
        from skills.adapt.lib.schema import LoopBlockOutput
        LoopBlockOutput.model_validate(loop_block)  # raises ValidationError on bad shape

    # VAL-04: If exit_reason is validator_passed, integrity must hold
    if loop_block is not None and loop_block.get("exit_reason") in ("validator_passed", "validator_passed_after_fix"):
        integrity = data.get("validator_integrity", {})
        if not isinstance(integrity, dict) or not integrity.get("integrity_ok", False):
            raise ValueError(
                "validator_integrity checks failed for passed exit: "
                f"binary_hash_ok={integrity.get('binary_hash_ok')}, "
                f"log_mtime_ok={integrity.get('log_mtime_ok')}, "
                f"log_present={integrity.get('log_present')}"
            )


def _validate_phase0_bridge_mapping(run_dir: Path, data: dict[str, Any]) -> None:
    """Optional: validate bridge_mapping.yaml content beyond existence checks."""
    artifacts = data.get("artifacts", {})
    bm_path = artifacts.get("bridge_mapping_path")
    if bm_path is None:
        return  # no path provided, skip content validation
    full_path = run_dir / bm_path
    if not full_path.exists():
        return  # file not found is already caught by bridge_mapping_exists check
    bm_data = yaml.safe_load(full_path.read_text())
    if not isinstance(bm_data, dict):
        raise ValueError(f"bridge_mapping.yaml is not a valid YAML dict: {full_path}")
    _expect(isinstance(bm_data.get("component_bridge"), list) and len(bm_data["component_bridge"]) > 0,
            "bridge_mapping.yaml component_bridge must be a non-empty list")
    _expect(isinstance(bm_data.get("gaps"), list),
            "bridge_mapping.yaml gaps must be a list")
    # Verify all gap entries have phase1_guidance
    for gap in bm_data.get("gaps", []):
        _expect(bool(gap.get("phase1_guidance")),
                f"bridge_mapping.yaml gap {gap.get('id', '?')} must have phase1_guidance")


def _validate_phase1_bridge_mapping_consumption(run_dir: Path, data: dict[str, Any]) -> None:
    """When bridge_mapping_consumed is true, verify the bridge_mapping.yaml file
    referenced in artifacts was actually read and has a non-empty component_bridge list."""
    checks = data.get("checks", {})
    bridge_mapping_consumed = checks.get("bridge_mapping_consumed")
    if bridge_mapping_consumed is not True:
        return  # not consumed or field absent — skip
    artifacts = data.get("artifacts", {})
    bm_path = artifacts.get("bridge_mapping_path")
    if bm_path is None:
        raise ValueError("checks.bridge_mapping_consumed is true but artifacts.bridge_mapping_path is absent")
    full_path = run_dir / bm_path
    if not full_path.exists():
        raise ValueError(f"checks.bridge_mapping_consumed is true but bridge_mapping file not found: {full_path}")
    bm_data = yaml.safe_load(full_path.read_text())
    if not isinstance(bm_data, dict):
        raise ValueError(f"bridge_mapping.yaml is not a valid YAML dict: {full_path}")
    component_bridge = bm_data.get("component_bridge")
    _expect(isinstance(component_bridge, list) and len(component_bridge) > 0,
            "bridge_mapping.yaml component_bridge must be a non-empty list when bridge_mapping_consumed is true")


def validate_phase_output(run_dir: Path, phase: int) -> None:
    data = _load_phase_output(run_dir, phase)
    _expect(data.get("status") == "passed", "phase status must be passed")
    _validate_step_gate(data)

    if phase == 0:
        checks = data.get("checks", {})
        # Three-document Phase 0 output (v2 — replaces model_spec.yaml)
        _expect(checks.get("hf_analysis_exists") is True, "checks.hf_analysis_exists must be true")
        _expect(checks.get("reference_impl_analysis_exists") is True, "checks.reference_impl_analysis_exists must be true")
        _expect(checks.get("bridge_mapping_exists") is True, "checks.bridge_mapping_exists must be true")
        _expect(checks.get("bridge_mapping_component_bridge_non_empty") is True, "checks.bridge_mapping_component_bridge_non_empty must be true")
        _expect(checks.get("bridge_mapping_gaps_have_guidance") is True, "checks.bridge_mapping_gaps_have_guidance must be true")
        # Retained checks from v1
        _expect(checks.get("components_non_empty") is True, "checks.components_non_empty must be true")
        _expect(checks.get("weight_structure_non_empty") is True, "checks.weight_structure_non_empty must be true")
        _expect(checks.get("slice_hf_ckpt_path_resolved") is True, "checks.slice_hf_ckpt_path_resolved must be true")
        _validate_phase0_bridge_mapping(run_dir, data)
        return

    expected_validators = {
        1: "phase1-verify",
        2: "phase2-conversion",
        3: "loss-diff",
        4: "feature-compat",
        5: "kb-consistency",
    }
    expected_name = expected_validators[phase]
    validator = data.get("validator") or _nested(data, "details", "validator")
    _expect(isinstance(validator, dict), "validator evidence must be present")
    _expect(validator.get("name") == expected_name, f"validator.name must be {expected_name}")
    _expect(validator.get("status") == "passed", "validator.status must be passed")

    if phase == 1:
        # --- Phase 1 specific checks (conditional for backward compat) ---
        checks = data.get("checks", {})

        # 1. Bridge mapping consumption check
        bridge_mapping_consumed = checks.get("bridge_mapping_consumed")
        if bridge_mapping_consumed is not None:
            _expect(bridge_mapping_consumed is True,
                    "checks.bridge_mapping_consumed must be true when bridge_mapping was used as primary input")

        # 2. Generated Megatron files consistency check
        generated_megatron_files = data.get("artifacts", {}).get("generated_megatron_files")
        if generated_megatron_files is not None:
            _expect(isinstance(generated_megatron_files, list),
                    "artifacts.generated_megatron_files must be a list when present")
            valid_prefixes = ("megatron/", "loongforge/models/common/experimental_attention_variant/")
            for fpath in generated_megatron_files:
                _expect(any(fpath.startswith(p) for p in valid_prefixes),
                        f"artifacts.generated_megatron_files entry '{fpath}' must start with a valid Megatron prefix")

        # 3. Perf lint execution check
        perf_lint_executed = checks.get("perf_lint_executed")
        if perf_lint_executed is not None:
            _expect(perf_lint_executed is True,
                    "checks.perf_lint_executed must be true when perf rules are enforced")

        # 4. HF sanity run check
        hf_sanity = checks.get("hf_sanity_run_passed")
        if hf_sanity is not None:
            _expect(hf_sanity is True,
                    "checks.hf_sanity_run_passed must be true when HF sanity run is executed")

        # 5. Example script dry run check
        example_dry = checks.get("example_script_dry_run_passed")
        if example_dry is not None:
            _expect(example_dry is True,
                    "checks.example_script_dry_run_passed must be true when example script dry run is executed")

        # 6. Strategy overrides reason check
        strategy_overrides = data.get("strategy", {}).get("overrides")
        if strategy_overrides is not None and isinstance(strategy_overrides, dict):
            for component, override in strategy_overrides.items():
                if isinstance(override, dict):
                    _expect(bool(override.get("reason")),
                            f"strategy.overrides.{component}.reason must be present when strategy was overridden")

        # 7. Bridge mapping consumption verification helper
        _validate_phase1_bridge_mapping_consumption(run_dir, data)

    if phase == 2:
        # --- Phase 2 bridge_mapping consumption checks (conditional) ---
        checks = data.get("checks", {})

        bridge_mapping_consumed = checks.get("bridge_mapping_consumed")
        if bridge_mapping_consumed is not None:
            _expect(bridge_mapping_consumed is True,
                    "checks.bridge_mapping_consumed must be true when bridge_mapping was used as primary input")

        generated_megatron_files = data.get("artifacts", {}).get("generated_megatron_files")
        if generated_megatron_files is not None:
            _expect(isinstance(generated_megatron_files, list),
                    "artifacts.generated_megatron_files must be a list when present")
            for fpath in generated_megatron_files:
                _expect(isinstance(fpath, str) and len(fpath) > 0,
                        f"artifacts.generated_megatron_files entries must be non-empty strings, got: {fpath}")

        source_bm_path = data.get("source", {}).get("bridge_mapping_path")
        if source_bm_path is not None:
            _expect(isinstance(source_bm_path, str) and len(source_bm_path) > 0,
                    "source.bridge_mapping_path must be a non-empty string when present")

        if bridge_mapping_consumed is True and source_bm_path is not None:
            full_path = run_dir / source_bm_path
            if full_path.exists():
                bm_data = yaml.safe_load(full_path.read_text())
                if isinstance(bm_data, dict):
                    component_bridge = bm_data.get("component_bridge")
                    _expect(isinstance(component_bridge, list) and len(component_bridge) > 0,
                            "bridge_mapping.yaml component_bridge must be a non-empty list when bridge_mapping_consumed is true")

        # Existing production_gate checks
        production_gate = _nested(data, "conversion", "production_gate") or _nested(data, "details", "step5c_production_gate")
        _expect(isinstance(production_gate, dict), "conversion.production_gate evidence must be present")
        _expect(
            production_gate.get("loaded_by_target_framework") is True,
            "conversion.production_gate.loaded_by_target_framework must be true",
        )
        _expect(
            production_gate.get("mcore_artifacts_exist") is True,
            "conversion.production_gate.mcore_artifacts_exist must be true",
        )
        _expect(
            production_gate.get("rebuilt_hf_derived_from_mcore") is True,
            "conversion.production_gate.rebuilt_hf_derived_from_mcore must be true",
        )
        _expect(
            production_gate.get("reversible_container_detected") is False,
            "conversion.production_gate.reversible_container_detected must be false",
        )
        _expect(
            production_gate.get("forbidden_shortcuts") == [],
            "conversion.production_gate.forbidden_shortcuts must be empty",
        )

    if phase == 3:
        # --- Phase 3 bridge_mapping consumption checks (conditional) ---
        checks = data.get("checks", {})

        # 1. Bridge mapping consumption check
        bridge_mapping_consumed = checks.get("bridge_mapping_consumed")
        if bridge_mapping_consumed is not None:
            _expect(bridge_mapping_consumed is True,
                    "checks.bridge_mapping_consumed must be true when bridge_mapping was used as primary input")

        # 2. Bridge mapping source path consistency check
        source_bm_path = data.get("source", {}).get("bridge_mapping_path")
        if source_bm_path is not None:
            _expect(isinstance(source_bm_path, str) and len(source_bm_path) > 0,
                    "source.bridge_mapping_path must be a non-empty string when present")

        # 3. Bridge mapping consumption verification (when consumed, verify file exists)
        if bridge_mapping_consumed is True and source_bm_path is not None:
            full_path = run_dir / source_bm_path
            if full_path.exists():
                bm_data = yaml.safe_load(full_path.read_text())
                if isinstance(bm_data, dict):
                    component_bridge = bm_data.get("component_bridge")
                    _expect(isinstance(component_bridge, list) and len(component_bridge) > 0,
                            "bridge_mapping.yaml component_bridge must be a non-empty list when bridge_mapping_consumed is true")
                    # Phase 3 specific: verify phase3_reference_requirements exists when bridge_mapping consumed
                    phase3_reqs = bm_data.get("phase3_reference_requirements")
                    if phase3_reqs is not None:
                        _expect(isinstance(phase3_reqs, dict),
                                "bridge_mapping.yaml phase3_reference_requirements must be a dict when present")

    if phase == 4:
        checks = data.get("checks", {})

        # Bridge mapping consumption check (conditional for backward compat)
        bridge_mapping_consumed = checks.get("bridge_mapping_consumed")
        if bridge_mapping_consumed is not None:
            _expect(bridge_mapping_consumed is True,
                    "checks.bridge_mapping_consumed must be true when bridge_mapping was used as input")
            # Verify bridge_mapping file exists and has content
            artifacts = data.get("artifacts", {})
            bm_path = artifacts.get("bridge_mapping_path")
            if bm_path is None:
                # Also check source section (Phase 4 schema places it there)
                bm_path = data.get("source", {}).get("bridge_mapping_path")
            if bm_path is not None:
                full_path = run_dir / bm_path
                if not full_path.exists():
                    raise ValueError(f"checks.bridge_mapping_consumed is true but bridge_mapping file not found: {full_path}")
                bm_data = yaml.safe_load(full_path.read_text())
                if not isinstance(bm_data, dict):
                    raise ValueError(f"bridge_mapping.yaml is not a valid YAML dict: {full_path}")
                component_bridge = bm_data.get("component_bridge")
                _expect(isinstance(component_bridge, list) and len(component_bridge) > 0,
                        "bridge_mapping.yaml component_bridge must be a non-empty list when bridge_mapping_consumed is true")

        # hf_analysis consumption check (conditional for backward compat)
        source = data.get("source", {})
        hf_analysis_path = source.get("hf_analysis_path")
        if hf_analysis_path is not None:
            full_path = run_dir / hf_analysis_path
            if not full_path.exists():
                raise ValueError(f"source.hf_analysis_path references a file that does not exist: {full_path}")
            hfa_data = yaml.safe_load(full_path.read_text())
            if not isinstance(hfa_data, dict):
                raise ValueError(f"hf_analysis.yaml is not a valid YAML dict: {full_path}")
            _expect(isinstance(hfa_data.get("model_category"), str),
                    "hf_analysis.yaml model_category must be a string")
            _expect(isinstance(hfa_data.get("components"), dict) and len(hfa_data["components"]) > 0,
                    "hf_analysis.yaml components must be a non-empty dict")

    if phase == 5:
        checks = data.get("checks", {})

        # Bridge mapping consumption check (conditional for backward compat)
        bridge_mapping_consumed = checks.get("bridge_mapping_consumed")
        if bridge_mapping_consumed is not None:
            _expect(bridge_mapping_consumed is True,
                    "checks.bridge_mapping_consumed must be true when bridge_mapping was used as input")
            artifacts = data.get("artifacts", {})
            bm_path = artifacts.get("bridge_mapping_path")
            if bm_path is None:
                # Also check source section
                bm_path = data.get("source", {}).get("bridge_mapping_path")
            if bm_path is not None:
                full_path = run_dir / bm_path
                if not full_path.exists():
                    raise ValueError(f"checks.bridge_mapping_consumed is true but bridge_mapping file not found: {full_path}")
                bm_data = yaml.safe_load(full_path.read_text())
                if not isinstance(bm_data, dict):
                    raise ValueError(f"bridge_mapping.yaml is not a valid YAML dict: {full_path}")
                component_bridge = bm_data.get("component_bridge")
                _expect(isinstance(component_bridge, list) and len(component_bridge) > 0,
                        "bridge_mapping.yaml component_bridge must be a non-empty list when bridge_mapping_consumed is true")

        # HF analysis consumption check (conditional for backward compat)
        hf_analysis_consumed = checks.get("hf_analysis_consumed")
        if hf_analysis_consumed is not None:
            _expect(hf_analysis_consumed is True,
                    "checks.hf_analysis_consumed must be true when hf_analysis was used as input")
            source = data.get("source", {})
            hfa_path = source.get("hf_analysis_path")
            if hfa_path is not None:
                full_path = run_dir / hfa_path
                if not full_path.exists():
                    raise ValueError(f"source.hf_analysis_path references a file that does not exist: {full_path}")
                hfa_data = yaml.safe_load(full_path.read_text())
                if not isinstance(hfa_data, dict):
                    raise ValueError(f"hf_analysis.yaml is not a valid YAML dict: {full_path}")
                _expect(isinstance(hfa_data.get("model_category"), str),
                        "hf_analysis.yaml model_category must be a string")
                _expect(isinstance(hfa_data.get("components"), dict) and len(hfa_data["components"]) > 0,
                        "hf_analysis.yaml components must be a non-empty dict")

    _validate_loop_evidence(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check LoongForge phase completion artifacts")
    parser.add_argument("--run-dir", required=True, help="Adaptation run directory")
    parser.add_argument("--phase", required=True, type=int, choices=range(6), help="Phase number 0-5")
    args = parser.parse_args(argv)

    try:
        validate_phase_output(Path(args.run_dir), args.phase)
    except Exception as exc:  # noqa: BLE001 - CLI gate should report any blocking reason.
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return BLOCK_EXIT_CODE

    print(f"PASSED: phase {args.phase} completion gate satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
