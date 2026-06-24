"""Tests for Phase 0 three-document output validation in validate_phase_completion.py.

Covers:
  - Test 1: phase=0 with hf_analysis_exists + bridge_mapping_exists + bridge_mapping_component_bridge_non_empty passes
  - Test 2: phase=0 missing bridge_mapping_exists raises ValueError
  - Test 3: phase=0 with bridge_mapping_component_bridge_non_empty=false raises ValueError
  - Test 4: phase=0 with old-format checks (model_spec_exists but no hf_analysis_exists) raises ValueError
  - Test 5: Phase 1-5 validation logic is unchanged (regression check)
  - Test 6: _validate_phase0_bridge_mapping validates bridge_mapping.yaml file content
  - Test 7: _validate_phase0_bridge_mapping skips when bridge_mapping_path absent
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import yaml
import pytest

from skills.adapt.scripts.validate_phase_completion import (
    validate_phase_output,
    _validate_phase0_bridge_mapping,
)


def _write_phase0_output(run_dir: Path, checks: dict, artifacts: dict | None = None, status: str = "passed") -> None:
    """Write a minimal phase0_output.yml with given checks and optional artifacts."""
    phases_dir = run_dir / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "status": status,
        "step_gate": {"mandatory_steps_complete": True},
        "steps": {
            "step1": {"status": "passed", "evidence": "ok"},
        },
        "checks": checks,
    }
    if artifacts is not None:
        data["artifacts"] = artifacts
    output_path = phases_dir / "phase0_output.yml"
    output_path.write_text(yaml.dump(data, default_flow_style=False))


def _full_v2_checks() -> dict:
    """Return a complete set of Phase 0 v2 checks that should pass."""
    return {
        "hf_analysis_exists": True,
        "reference_impl_analysis_exists": True,
        "bridge_mapping_exists": True,
        "bridge_mapping_component_bridge_non_empty": True,
        "bridge_mapping_gaps_have_guidance": True,
        "components_non_empty": True,
        "weight_structure_non_empty": True,
        "slice_hf_ckpt_path_resolved": True,
    }


class TestPhase0V2Validation:
    """Test Phase 0 three-document validation (v2)."""

    def test_v2_full_checks_pass(self, tmp_path):
        """Test 1: phase=0 with all v2 checks passes without error."""
        run_dir = tmp_path / "run"
        _write_phase0_output(run_dir, _full_v2_checks())
        # Should not raise
        validate_phase_output(run_dir, phase=0)

    def test_v2_missing_bridge_mapping_exists_raises(self, tmp_path):
        """Test 2: phase=0 missing bridge_mapping_exists raises ValueError."""
        run_dir = tmp_path / "run"
        checks = _full_v2_checks()
        del checks["bridge_mapping_exists"]
        _write_phase0_output(run_dir, checks)
        with pytest.raises(ValueError, match="bridge_mapping_exists"):
            validate_phase_output(run_dir, phase=0)

    def test_v2_bridge_mapping_component_bridge_non_empty_false_raises(self, tmp_path):
        """Test 3: phase=0 with bridge_mapping_component_bridge_non_empty=false raises."""
        run_dir = tmp_path / "run"
        checks = _full_v2_checks()
        checks["bridge_mapping_component_bridge_non_empty"] = False
        _write_phase0_output(run_dir, checks)
        with pytest.raises(ValueError, match="bridge_mapping_component_bridge_non_empty"):
            validate_phase_output(run_dir, phase=0)

    def test_v2_old_model_spec_exists_no_hf_analysis_raises(self, tmp_path):
        """Test 4: phase=0 with old model_spec_exists but no hf_analysis_exists raises.

        Old format (model_spec_exists=true) is no longer accepted.
        """
        run_dir = tmp_path / "run"
        old_checks = {
            "model_spec_exists": True,
            "components_non_empty": True,
            "weight_structure_non_empty": True,
            "slice_hf_ckpt_path_resolved": True,
        }
        _write_phase0_output(run_dir, old_checks)
        with pytest.raises(ValueError, match="hf_analysis_exists"):
            validate_phase_output(run_dir, phase=0)

    def test_v2_missing_reference_impl_analysis_raises(self, tmp_path):
        """Extra: phase=0 missing reference_impl_analysis_exists raises."""
        run_dir = tmp_path / "run"
        checks = _full_v2_checks()
        del checks["reference_impl_analysis_exists"]
        _write_phase0_output(run_dir, checks)
        with pytest.raises(ValueError, match="reference_impl_analysis_exists"):
            validate_phase_output(run_dir, phase=0)

    def test_v2_missing_bridge_mapping_gaps_have_guidance_raises(self, tmp_path):
        """Extra: phase=0 missing bridge_mapping_gaps_have_guidance raises."""
        run_dir = tmp_path / "run"
        checks = _full_v2_checks()
        del checks["bridge_mapping_gaps_have_guidance"]
        _write_phase0_output(run_dir, checks)
        with pytest.raises(ValueError, match="bridge_mapping_gaps_have_guidance"):
            validate_phase_output(run_dir, phase=0)


class TestPhase0BridgeMappingFileValidation:
    """Test _validate_phase0_bridge_mapping helper function."""

    def _write_bridge_mapping(self, run_dir: Path, bridge_mapping: dict) -> None:
        """Write a bridge_mapping.yaml in the phases/phase0/ directory."""
        phase0_dir = run_dir / "phases" / "phase0"
        phase0_dir.mkdir(parents=True, exist_ok=True)
        bm_path = phase0_dir / "bridge_mapping.yaml"
        bm_path.write_text(yaml.dump(bridge_mapping, default_flow_style=False))

    def test_valid_bridge_mapping_passes(self, tmp_path):
        """Test 6: _validate_phase0_bridge_mapping validates bridge_mapping.yaml content."""
        run_dir = tmp_path / "run"
        bridge_mapping = {
            "model": "test-model",
            "hf_source": "transformers/models/test",
            "megatron_family": "test",
            "component_bridge": [
                {"hf": "attention", "megatron": ["MLASelfAttention"], "strategy": "adapt_ref", "confidence": "high"},
            ],
            "gaps": [
                {"id": "G1", "component": "mtp", "hf": "TestMTP", "megatron": "NEW", "decision": "new impl", "impact": "critical", "phase1_guidance": "implement MTP"},
            ],
        }
        self._write_bridge_mapping(run_dir, bridge_mapping)
        data = {"artifacts": {"bridge_mapping_path": "phases/phase0/bridge_mapping.yaml"}}
        # Should not raise
        _validate_phase0_bridge_mapping(run_dir, data)

    def test_empty_component_bridge_raises(self, tmp_path):
        """bridge_mapping.yaml with empty component_bridge list raises ValueError."""
        run_dir = tmp_path / "run"
        bridge_mapping = {
            "model": "test-model",
            "component_bridge": [],
            "gaps": [],
        }
        self._write_bridge_mapping(run_dir, bridge_mapping)
        data = {"artifacts": {"bridge_mapping_path": "phases/phase0/bridge_mapping.yaml"}}
        with pytest.raises(ValueError, match="component_bridge must be a non-empty list"):
            _validate_phase0_bridge_mapping(run_dir, data)

    def test_gap_missing_phase1_guidance_raises(self, tmp_path):
        """bridge_mapping.yaml gap without phase1_guidance raises ValueError."""
        run_dir = tmp_path / "run"
        bridge_mapping = {
            "model": "test-model",
            "component_bridge": [
                {"hf": "attention", "megatron": ["MLASelfAttention"], "strategy": "adapt_ref", "confidence": "high"},
            ],
            "gaps": [
                {"id": "G1", "component": "mtp", "hf": "TestMTP", "megatron": "NEW", "impact": "critical"},
            ],
        }
        self._write_bridge_mapping(run_dir, bridge_mapping)
        data = {"artifacts": {"bridge_mapping_path": "phases/phase0/bridge_mapping.yaml"}}
        with pytest.raises(ValueError, match="phase1_guidance"):
            _validate_phase0_bridge_mapping(run_dir, data)

    def test_no_bridge_mapping_path_skips(self, tmp_path):
        """Test 7: _validate_phase0_bridge_mapping skips when bridge_mapping_path absent."""
        run_dir = tmp_path / "run"
        data = {"artifacts": {}}
        # Should not raise — returns silently
        _validate_phase0_bridge_mapping(run_dir, data)

    def test_bridge_mapping_file_not_found_skips(self, tmp_path):
        """_validate_phase0_bridge_mapping skips when the file does not exist."""
        run_dir = tmp_path / "run"
        data = {"artifacts": {"bridge_mapping_path": "phases/phase0/bridge_mapping.yaml"}}
        # File doesn't exist, but bridge_mapping_exists check in checks block
        # already catches that — this function returns silently
        _validate_phase0_bridge_mapping(run_dir, data)


class TestPhase1to5Unchanged:
    """Test 5: Phase 1-5 validation logic is unchanged (regression check)."""

    def test_phase1_legacy_passes(self, tmp_path):
        """Phase 1 validation with standard fields still works."""
        run_dir = tmp_path / "run"
        phases_dir = run_dir / "phases"
        phases_dir.mkdir(parents=True, exist_ok=True)
        output_path = phases_dir / "phase1_output.yml"
        data = {
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"step1": {"status": "passed", "evidence": "ok"}},
            "validator": {"name": "phase1-verify", "status": "passed"},
        }
        output_path.write_text(yaml.dump(data, default_flow_style=False))
        # Should not raise
        validate_phase_output(run_dir, phase=1)

    def test_phase2_legacy_passes(self, tmp_path):
        """Phase 2 validation with production gate still works."""
        run_dir = tmp_path / "run"
        phases_dir = run_dir / "phases"
        phases_dir.mkdir(parents=True, exist_ok=True)
        output_path = phases_dir / "phase2_output.yml"
        data = {
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"step1": {"status": "passed", "evidence": "ok"}},
            "validator": {"name": "phase2-conversion", "status": "passed"},
            "conversion": {
                "production_gate": {
                    "loaded_by_target_framework": True,
                    "mcore_artifacts_exist": True,
                    "rebuilt_hf_derived_from_mcore": True,
                    "reversible_container_detected": False,
                    "forbidden_shortcuts": [],
                },
            },
        }
        output_path.write_text(yaml.dump(data, default_flow_style=False))
        validate_phase_output(run_dir, phase=2)
