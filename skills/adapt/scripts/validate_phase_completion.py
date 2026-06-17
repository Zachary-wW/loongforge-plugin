#!/usr/bin/env python3
"""Deterministic LoongForge adaptation phase completion gate.

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


def validate_phase_output(run_dir: Path, phase: int) -> None:
    data = _load_phase_output(run_dir, phase)
    _expect(data.get("status") == "passed", "phase status must be passed")
    _validate_step_gate(data)

    if phase == 0:
        checks = data.get("checks", {})
        _expect(checks.get("model_spec_exists") is True, "checks.model_spec_exists must be true")
        _expect(checks.get("components_non_empty") is True, "checks.components_non_empty must be true")
        _expect(checks.get("weight_structure_non_empty") is True, "checks.weight_structure_non_empty must be true")
        _expect(checks.get("slice_hf_ckpt_path_resolved") is True, "checks.slice_hf_ckpt_path_resolved must be true")
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

    if phase == 2:
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
