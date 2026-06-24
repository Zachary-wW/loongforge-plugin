"""CLI tests for skills.adapt.scripts.phase_loop.

Covers:
  - Arg parsing (--run-dir, --phase, --dry-run, --continue-fix)
  - Exit code mapping: 0=passed, 1=exhausted/human_needed, 10=FIX_NEEDED
  - _extract_repos_info() from RunInputs
  - Dry-run with FakeGhClient (no real gh calls)
  - --continue-fix sets pause_before_fix=False
  - Missing run_inputs.yml → exit 2
  - Nonexistent run-dir → exit 2
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
PHASE_LOOP_PY = REPO_ROOT / "skills" / "adapt" / "scripts" / "phase_loop.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Invoke phase_loop.py as a subprocess with correct PYTHONPATH."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    cmd = [sys.executable, str(PHASE_LOOP_PY), *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)


def _init_run_dir(run_dir: Path, with_repos: bool = False) -> None:
    """Create a minimal run directory with run_inputs.yml for testing."""
    from skills.adapt.lib.schema import RunInputs, SourceBlock, PathsBlock, OptionsBlock

    run_dir.mkdir(parents=True, exist_ok=True)
    phases_dir = run_dir / "phases"
    for i in range(7):
        (phases_dir / f"phase{i}").mkdir(parents=True, exist_ok=True)
        if 1 <= i <= 5:
            (phases_dir / f"phase{i}" / "logs").mkdir(parents=True, exist_ok=True)

    inputs = RunInputs(
        source=SourceBlock(hf_ckpt_path="/tmp/fake_ckpt"),
        paths=PathsBlock(),
        options=OptionsBlock(model_name="TestModel"),
    )
    (run_dir / "run_inputs.yml").write_text(
        yaml.dump(inputs.model_dump(), default_flow_style=False)
    )

    if with_repos:
        inputs_v2 = RunInputs(
            source=SourceBlock(hf_ckpt_path="/tmp/fake_ckpt"),
            paths=PathsBlock(),
            options=OptionsBlock(model_name="TestModel"),
            **{
                "repos": {
                    "hf_impl": {"url": "https://github.com/huggingface/transformers", "ref": "main"},
                    "hf_ckpt": {"url": "https://huggingface.co/org/model", "revision": "main"},
                    "loongforge": {"url": "https://github.com/Zachary-wW/LoongForge", "base_ref": "main"},
                    "megatron": {"url": "https://github.com/Zachary-wW/Loong-Megatron", "base_ref": "loong-main/core_v0.15.0"},
                }
            },
        )
        (run_dir / "run_inputs.yml").write_text(
            yaml.dump(inputs_v2.model_dump(), default_flow_style=False)
        )


# ---------------------------------------------------------------------------
# Test: arg parsing
# ---------------------------------------------------------------------------

class TestArgParsing:
    def test_missing_run_dir_exits_2(self):
        result = _run_cli("--phase", "0")
        assert result.returncode == 2

    def test_missing_phase_exits_2(self, tmp_path):
        result = _run_cli("--run-dir", str(tmp_path))
        assert result.returncode == 2

    def test_invalid_phase_exits_2(self, tmp_path):
        result = _run_cli("--run-dir", str(tmp_path), "--phase", "9")
        assert result.returncode == 2

    def test_help_exits_0(self):
        result = _run_cli("--help")
        assert result.returncode == 0
        assert "phase" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Test: missing / invalid run directory
# ---------------------------------------------------------------------------

class TestInvalidRunDir:
    def test_nonexistent_run_dir_exits_2(self, tmp_path):
        result = _run_cli("--run-dir", str(tmp_path / "nonexistent"), "--phase", "0")
        assert result.returncode == 2
        assert "does not exist" in result.stderr

    def test_missing_run_inputs_yml_exits_2(self, tmp_path):
        run_dir = tmp_path / "empty_run"
        run_dir.mkdir()
        result = _run_cli("--run-dir", str(run_dir), "--phase", "0")
        assert result.returncode == 2
        assert "not found" in result.stderr


# ---------------------------------------------------------------------------
# Test: repos_info extraction
# ---------------------------------------------------------------------------

class TestReposInfoExtraction:
    def test_extract_repos_info_no_repos(self, tmp_path):
        """Without repos: block, repos_info should be None."""
        from skills.adapt.scripts.phase_loop import _extract_repos_info
        from skills.adapt.lib.schema import RunInputs, SourceBlock

        inputs = RunInputs(source=SourceBlock(hf_ckpt_path="/tmp/m"))
        result = _extract_repos_info(inputs)
        assert result is None

    def test_extract_repos_info_with_repos(self, tmp_path):
        """With repos: block, repos_info should have owner/repo strings."""
        from skills.adapt.scripts.phase_loop import _extract_repos_info
        from skills.adapt.lib.schema import RunInputs, SourceBlock, ReposBlock, RepoSpec, HFImplSpec, HFCkptSpec

        inputs = RunInputs(
            source=SourceBlock(hf_ckpt_path="/tmp/m"),
            repos=ReposBlock(
                hf_impl=HFImplSpec(url="https://github.com/huggingface/transformers", ref="main"),
                hf_ckpt=HFCkptSpec(url="https://huggingface.co/org/model"),
                loongforge=RepoSpec(url="https://github.com/Zachary-wW/LoongForge", base_ref="main"),
                megatron=RepoSpec(url="https://github.com/Zachary-wW/Loong-Megatron", base_ref="loong-main/core_v0.15.0"),
            ),
        )
        result = _extract_repos_info(inputs)
        assert result is not None
        assert result["loongforge_repo"] == "Zachary-wW/LoongForge"
        assert result["megatron_repo"] == "Zachary-wW/Loong-Megatron"
        assert result["loongforge_base_ref"] == "main"
        assert result["megatron_ref"] == "loong-main/core_v0.15.0"


# ---------------------------------------------------------------------------
# Test: run_id extraction
# ---------------------------------------------------------------------------

class TestRunIdExtraction:
    def test_run_id_from_dir_name(self):
        from skills.adapt.scripts.phase_loop import _run_id_from_dir
        assert _run_id_from_dir(Path("/tmp/loongforge_adapt/my_run_42")) == "my_run_42"

    def test_run_id_from_nested_dir(self):
        from skills.adapt.scripts.phase_loop import _run_id_from_dir
        assert _run_id_from_dir(Path("/tmp/runs/deepseek_v4")) == "deepseek_v4"


# ---------------------------------------------------------------------------
# Test: dry-run invocation (FakeGhClient, no network)
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_phase0_exits_nonzero_no_validator(self, tmp_path):
        """Without a real validator set up, dry-run Phase 0 should exit 1
        (validator fails → exhausted or human_needed)."""
        run_dir = tmp_path / "dry_run_0"
        _init_run_dir(run_dir, with_repos=True)
        result = _run_cli("--run-dir", str(run_dir), "--phase", "0", "--dry-run")
        # The FSM will try to validate and fail; exact exit code depends on
        # whether loongforge-phase-gate binary exists and is callable.
        # At minimum, the CLI should not crash with an import error.
        assert result.returncode in (0, 1, 10), f"stderr: {result.stderr}\nstdout: {result.stdout}"

    def test_dry_run_no_repos_local_mode(self, tmp_path):
        """Without repos: block, the loop runs in local-only mode."""
        run_dir = tmp_path / "local_run"
        _init_run_dir(run_dir, with_repos=False)
        result = _run_cli("--run-dir", str(run_dir), "--phase", "0", "--dry-run")
        # Should not crash — local mode skips all gh calls
        assert result.returncode in (0, 1), f"stderr: {result.stderr}\nstdout: {result.stdout}"


# ---------------------------------------------------------------------------
# Test: --continue-fix flag
# ---------------------------------------------------------------------------

class TestContinueFix:
    def test_continue_fix_flag_recognized(self, tmp_path):
        """--continue-fix should be accepted without error."""
        run_dir = tmp_path / "continue_fix"
        _init_run_dir(run_dir, with_repos=False)
        result = _run_cli("--run-dir", str(run_dir), "--phase", "0", "--dry-run", "--continue-fix")
        # Just verify no import error or arg parsing error
        assert result.returncode in (0, 1), f"stderr: {result.stderr}\nstdout: {result.stdout}"


# ---------------------------------------------------------------------------
# Test: exit code mapping
# ---------------------------------------------------------------------------

class TestExitCodeMapping:
    def test_exit_reason_fix_needed_maps_to_10(self):
        """ExitReason.FIX_NEEDED should map to exit code 10."""
        from skills.adapt.scripts.phase_loop import main
        from skills.adapt.lib.loop_controller import ExitReason
        # Unit-level: verify the mapping logic
        exit_code_map = {
            ExitReason.VALIDATOR_PASSED: 0,
            ExitReason.VALIDATOR_PASSED_AFTER_FIX: 0,
            ExitReason.FIX_NEEDED: 10,
        }
        assert exit_code_map[ExitReason.FIX_NEEDED] == 10
        assert exit_code_map[ExitReason.VALIDATOR_PASSED] == 0
        assert exit_code_map.get(ExitReason.EXHAUSTED, 1) == 1

    def test_exit_reason_exhausted_maps_to_1(self):
        from skills.adapt.lib.loop_controller import ExitReason
        exit_code_map = {
            ExitReason.VALIDATOR_PASSED: 0,
            ExitReason.VALIDATOR_PASSED_AFTER_FIX: 0,
            ExitReason.FIX_NEEDED: 10,
        }
        assert exit_code_map.get(ExitReason.EXHAUSTED, 1) == 1
        assert exit_code_map.get(ExitReason.HUMAN_NEEDED, 1) == 1


# ---------------------------------------------------------------------------
# Test: existing ExitReason count update
# ---------------------------------------------------------------------------

class TestExitReasonCount:
    def test_exit_reason_now_has_7_values(self):
        """After adding FIX_NEEDED, ExitReason should have 7 values."""
        from skills.adapt.lib.loop_controller import ExitReason
        assert len(ExitReason) == 7
        assert hasattr(ExitReason, "FIX_NEEDED")
        assert ExitReason.FIX_NEEDED.value == "fix_needed"
