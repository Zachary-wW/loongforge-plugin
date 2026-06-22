"""COMPAT-03 inert-hook tests + future-flag honoured tests for _validate_loop_evidence.

Tests that:
- Legacy phase output (no loop_engineering flag) passes unchanged.
- loop_engineering=true with no loop block passes (inert hook).
- loop_engineering=true with valid loop block passes.
- loop_engineering=true with malformed loop block raises pydantic.ValidationError.
- loop_engineering=true with invalid exit_reason raises pydantic.ValidationError.
- CLI gate exit code preserved for malformed loop blocks.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pydantic
import pytest
import yaml

from skills.adapt.scripts.validate_phase_completion import validate_phase_output

REPO_ROOT = Path(__file__).resolve().parents[4]  # .../loongforge-plugin


def _write(run_dir: Path, phase: int, data: dict) -> None:
    """Write a phaseN_output.yml into a temp run directory."""
    (run_dir / "phases").mkdir(parents=True, exist_ok=True)
    (run_dir / "phases" / f"phase{phase}_output.yml").write_text(
        yaml.dump(data, sort_keys=False)
    )


def _base_phase1_output() -> dict:
    """Return a minimal valid phase1_output.yml dict."""
    return {
        "phase": 1,
        "status": "passed",
        "step_gate": {"mandatory_steps_complete": True},
        "steps": {"s1": {"status": "passed", "evidence": "x"}},
        "validator": {"name": "phase1-verify", "status": "passed"},
    }


class TestLegacyCompat:
    """COMPAT-03: legacy outputs (no loop_engineering flag) pass unchanged."""

    def test_legacy_phase1_output_passes(self, tmp_path: Path) -> None:
        data = _base_phase1_output()
        _write(tmp_path, 1, data)
        # Should return None (no exception)
        assert validate_phase_output(tmp_path, 1) is None


class TestLoopEngineeringFlag:
    """When loop_engineering=true is set, the hook activates."""

    def test_loop_engineering_true_no_loop_block_passes(self, tmp_path: Path) -> None:
        data = _base_phase1_output()
        data["loop_engineering"] = True
        _write(tmp_path, 1, data)
        # No loop block => inert, passes
        assert validate_phase_output(tmp_path, 1) is None

    def test_loop_engineering_true_valid_loop_passes(self, tmp_path: Path) -> None:
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": 1,
            "max_attempts": 5,
            "exit_reason": "validator_passed",
            "attempts_journal": "phases/phase1/attempts.jsonl",
        }
        _write(tmp_path, 1, data)
        assert validate_phase_output(tmp_path, 1) is None

    def test_loop_engineering_true_malformed_attempts_raises(self, tmp_path: Path) -> None:
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": -1,
            "max_attempts": 5,
            "exit_reason": "validator_passed",
            "attempts_journal": "",
        }
        _write(tmp_path, 1, data)
        with pytest.raises(pydantic.ValidationError):
            validate_phase_output(tmp_path, 1)

    def test_loop_engineering_true_invalid_exit_reason_raises(self, tmp_path: Path) -> None:
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": 1,
            "max_attempts": 5,
            "exit_reason": "made_up",
            "attempts_journal": "phases/phase1/attempts.jsonl",
        }
        _write(tmp_path, 1, data)
        with pytest.raises(pydantic.ValidationError):
            validate_phase_output(tmp_path, 1)


class TestPhaseGateCliExitCode:
    """CLI gate preserves BLOCK_EXIT_CODE (2) for malformed loop blocks."""

    def test_phase_gate_cli_blocks_malformed_loop(self, tmp_path: Path) -> None:
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": -1,
            "max_attempts": 5,
            "exit_reason": "validator_passed",
            "attempts_journal": "",
        }
        _write(tmp_path, 1, data)

        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "skills" / "adapt" / "scripts" / "validate_phase_completion.py"),
                "--run-dir", str(tmp_path),
                "--phase", "1",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}; stderr={result.stderr}"
        assert result.stderr.startswith("BLOCKED:"), f"Expected stderr to start with BLOCKED:, got: {result.stderr}"


class TestLegacyNoPydanticImport:
    """Negative invariant: legacy path must NOT import pydantic."""

    def test_legacy_path_no_pydantic_import(self, tmp_path: Path) -> None:
        """Validate that a legacy output (no loop_engineering) does not
        trigger pydantic import in the process."""
        data = _base_phase1_output()
        _write(tmp_path, 1, data)

        # Use subprocess to get a clean Python process with no pydantic pre-loaded
        script = f"""
import sys
# Remove pydantic if already imported
if 'pydantic' in sys.modules:
    del sys.modules['pydantic']

from skills.adapt.scripts.validate_phase_completion import validate_phase_output
from pathlib import Path

validate_phase_output(Path("{tmp_path}"), 1)
assert 'pydantic' not in sys.modules, 'legacy path must not import pydantic'
print("OK")
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "PYTHONPATH": str(REPO_ROOT),
            },
        )
        assert result.returncode == 0, f"Legacy no-pydantic check failed: {result.stderr}"
        assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# VAL-04: validator integrity checks in _validate_loop_evidence
# ---------------------------------------------------------------------------

class TestValidatorIntegrityCheck:
    """VAL-04: When exit_reason is validator_passed, integrity must hold.
    COMPAT-03: legacy outputs still pass without loop_engineering flag."""

    def test_passed_with_valid_integrity(self, tmp_path: Path) -> None:
        """loop_engineering=true, exit_reason=validator_passed, integrity_ok=True -> passes."""
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": 1,
            "max_attempts": 5,
            "exit_reason": "validator_passed",
            "attempts_journal": "",
        }
        data["validator_integrity"] = {
            "binary_hash_ok": True,
            "log_mtime_ok": True,
            "log_present": True,
            "integrity_ok": True,
        }
        _write(tmp_path, 1, data)
        assert validate_phase_output(tmp_path, 1) is None

    def test_passed_with_missing_integrity(self, tmp_path: Path) -> None:
        """loop_engineering=true, exit_reason=validator_passed, no validator_integrity key -> raises ValueError."""
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": 1,
            "max_attempts": 5,
            "exit_reason": "validator_passed",
            "attempts_journal": "",
        }
        # No validator_integrity key at all
        _write(tmp_path, 1, data)
        with pytest.raises(ValueError, match="validator_integrity"):
            validate_phase_output(tmp_path, 1)

    def test_passed_with_failed_integrity(self, tmp_path: Path) -> None:
        """loop_engineering=true, exit_reason=validator_passed, integrity_ok=False -> raises ValueError."""
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": 1,
            "max_attempts": 5,
            "exit_reason": "validator_passed",
            "attempts_journal": "",
        }
        data["validator_integrity"] = {
            "binary_hash_ok": False,
            "log_mtime_ok": True,
            "log_present": True,
            "integrity_ok": False,
        }
        _write(tmp_path, 1, data)
        with pytest.raises(ValueError, match="validator_integrity"):
            validate_phase_output(tmp_path, 1)

    def test_passed_after_fix_with_valid_integrity(self, tmp_path: Path) -> None:
        """exit_reason=validator_passed_after_fix, integrity_ok=True -> passes."""
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": 2,
            "max_attempts": 5,
            "exit_reason": "validator_passed_after_fix",
            "attempts_journal": "",
        }
        data["validator_integrity"] = {
            "binary_hash_ok": True,
            "log_mtime_ok": True,
            "log_present": True,
            "integrity_ok": True,
        }
        _write(tmp_path, 1, data)
        assert validate_phase_output(tmp_path, 1) is None

    def test_non_passed_exit_ignores_integrity(self, tmp_path: Path) -> None:
        """exit_reason=exhausted, no validator_integrity -> passes (integrity irrelevant)."""
        data = _base_phase1_output()
        data["loop_engineering"] = True
        data["loop"] = {
            "attempts": 5,
            "max_attempts": 5,
            "exit_reason": "exhausted",
            "attempts_journal": "",
        }
        # No validator_integrity -- should still pass for non-passed exit reasons
        _write(tmp_path, 1, data)
        assert validate_phase_output(tmp_path, 1) is None

    def test_legacy_still_passes(self, tmp_path: Path) -> None:
        """COMPAT-03 regression: legacy output without loop_engineering flag still passes."""
        data = _base_phase1_output()
        # No loop_engineering, no validator_integrity
        _write(tmp_path, 1, data)
        assert validate_phase_output(tmp_path, 1) is None
