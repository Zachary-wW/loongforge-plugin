"""CLI round-trip tests for skills.adapt.scripts.run.

Covers:
  - Legacy positional-only invocation (no repos/loop)
  - All 4 URL flags + --dry-run (repos + loop blocks present)
  - Partial URL flags rejected (all-or-nothing validation)
  - Resume skips preflight (no network needed)
  - W5: v2-init triggers run_preflight, --resume does NOT (runtime-traced monkeypatch)
  - COMPAT-02: run_state.json legacy fields unchanged (no top-level repos/loop)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Repo root so we can invoke run.py with correct PYTHONPATH
REPO_ROOT = Path(__file__).resolve().parents[4]
RUN_PY = REPO_ROOT / "skills" / "adapt" / "scripts" / "run.py"


def _run_cli(*args: str, tmp_path: Path | None = None) -> subprocess.CompletedProcess:
    """Invoke run.py as a subprocess with PYTHONPATH set to REPO_ROOT."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    cmd = [sys.executable, str(RUN_PY), *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)


# ---------------------------------------------------------------------------
# Test: legacy positional invocation (no URL flags)
# ---------------------------------------------------------------------------

class TestLegacyInvocation:
    def test_legacy_exits_zero(self, tmp_path):
        run_dir = tmp_path / "legacy_run"
        result = _run_cli("/tmp/m", "--run-dir", str(run_dir))
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

    def test_legacy_run_inputs_has_source_paths_options(self, tmp_path):
        run_dir = tmp_path / "legacy_run"
        _run_cli("/tmp/m", "--run-dir", str(run_dir))
        inputs = yaml.safe_load((run_dir / "run_inputs.yml").read_text())
        assert "source" in inputs
        assert "paths" in inputs
        assert "options" in inputs

    def test_legacy_run_inputs_no_repos_or_loop(self, tmp_path):
        run_dir = tmp_path / "legacy_run"
        _run_cli("/tmp/m", "--run-dir", str(run_dir))
        inputs = yaml.safe_load((run_dir / "run_inputs.yml").read_text())
        assert "repos" not in inputs
        assert "loop" not in inputs


# ---------------------------------------------------------------------------
# Test: all 4 URL flags + --dry-run
# ---------------------------------------------------------------------------

class TestV2Invocation:
    def test_v2_exits_zero(self, tmp_path):
        run_dir = tmp_path / "v2_run"
        result = _run_cli(
            "/tmp/m", "--run-dir", str(run_dir),
            "--hf-impl-url", "https://github.com/huggingface/transformers",
            "--hf-ckpt-url", "https://huggingface.co/x/y",
            "--loongforge-repo", "https://github.com/Zachary-wW/LoongForge",
            "--megatron-repo", "https://github.com/Zachary-wW/Loong-Megatron",
            "--dry-run",
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

    def test_v2_run_inputs_has_repos_block(self, tmp_path):
        run_dir = tmp_path / "v2_run"
        _run_cli(
            "/tmp/m", "--run-dir", str(run_dir),
            "--hf-impl-url", "https://github.com/huggingface/transformers",
            "--hf-ckpt-url", "https://huggingface.co/x/y",
            "--loongforge-repo", "https://github.com/Zachary-wW/LoongForge",
            "--megatron-repo", "https://github.com/Zachary-wW/Loong-Megatron",
            "--dry-run",
        )
        inputs = yaml.safe_load((run_dir / "run_inputs.yml").read_text())
        assert "repos" in inputs
        repos = inputs["repos"]
        assert repos["hf_impl"]["url"] == "https://github.com/huggingface/transformers"
        assert repos["hf_ckpt"]["url"] == "https://huggingface.co/x/y"
        assert repos["loongforge"]["url"] == "https://github.com/Zachary-wW/LoongForge"
        assert repos["megatron"]["url"] == "https://github.com/Zachary-wW/Loong-Megatron"

    def test_v2_run_inputs_has_loop_block(self, tmp_path):
        run_dir = tmp_path / "v2_run"
        _run_cli(
            "/tmp/m", "--run-dir", str(run_dir),
            "--hf-impl-url", "https://github.com/huggingface/transformers",
            "--hf-ckpt-url", "https://huggingface.co/x/y",
            "--loongforge-repo", "https://github.com/Zachary-wW/LoongForge",
            "--megatron-repo", "https://github.com/Zachary-wW/Loong-Megatron",
            "--dry-run",
        )
        inputs = yaml.safe_load((run_dir / "run_inputs.yml").read_text())
        assert "loop" in inputs
        loop = inputs["loop"]
        assert loop["max_attempts_per_phase"] == 5
        assert loop["max_attempts_per_run"] == 25
        assert loop["max_wallclock_minutes"] == 240
        assert loop["escalation"] == "human_needed"


# ---------------------------------------------------------------------------
# Test: partial URL flags rejected
# ---------------------------------------------------------------------------

class TestPartialURLFlagsRejected:
    def test_only_hf_impl_url_exits_nonzero(self, tmp_path):
        run_dir = tmp_path / "partial"
        result = _run_cli(
            "/tmp/m", "--run-dir", str(run_dir),
            "--hf-impl-url", "https://github.com/huggingface/transformers",
        )
        assert result.returncode != 0

    def test_only_hf_impl_url_stderr_contains_message(self, tmp_path):
        run_dir = tmp_path / "partial"
        result = _run_cli(
            "/tmp/m", "--run-dir", str(run_dir),
            "--hf-impl-url", "https://github.com/huggingface/transformers",
        )
        assert "must all be provided together" in result.stderr


# ---------------------------------------------------------------------------
# Test: resume skips preflight (no network needed)
# ---------------------------------------------------------------------------

class TestResumeSkipsPreflight:
    def test_resume_exits_zero_without_network(self, tmp_path):
        """Legacy --resume after a simple init should not need network/gh CLI."""
        run_dir = tmp_path / "resume_run"
        # Init first (legacy form, no URL flags, no preflight)
        _run_cli("/tmp/m", "--run-dir", str(run_dir))
        # Resume should work without any network
        result = _run_cli("--resume", str(run_dir))
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"


# ---------------------------------------------------------------------------
# W5: Runtime-traced v2-init calls preflight, --resume does NOT
# ---------------------------------------------------------------------------

class TestW5PreflightTracing:
    def test_v2_init_calls_preflight_resume_does_not(self, tmp_path, monkeypatch):
        """W5: monkey-patching skills.adapt.scripts.run.run_preflight proves:
        - v2-init path invokes run_preflight
        - --resume path does NOT invoke run_preflight
        """
        import skills.adapt.scripts.run as run_mod
        from skills.adapt.lib.preflight import PreflightResult

        called = {"flag": False}

        def _trace(*args, **kwargs):
            called["flag"] = True
            return PreflightResult(ok=True, failures=[], warnings=[], branch_protection={})

        monkeypatch.setattr(run_mod, "run_preflight", _trace)

        # v2 init with all URL flags + --dry-run
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

        # Reset and test --resume does NOT call preflight
        called["flag"] = False
        run_mod.main(["--resume", str(rd)])
        assert called["flag"] is False, "--resume path MUST NOT invoke run_preflight"


# ---------------------------------------------------------------------------
# COMPAT-02: run_state.json legacy fields unchanged
# ---------------------------------------------------------------------------

class TestLegacyStateCompat:
    def test_run_state_json_has_legacy_keys_no_repos_loop(self, tmp_path):
        """After v2 invocation, run_state.json must contain exactly the legacy
        keys and must NOT have top-level repos or loop."""
        run_dir = tmp_path / "compat_run"
        _run_cli(
            "/tmp/m", "--run-dir", str(run_dir),
            "--hf-impl-url", "https://github.com/huggingface/transformers",
            "--hf-ckpt-url", "https://huggingface.co/x/y",
            "--loongforge-repo", "https://github.com/Zachary-wW/LoongForge",
            "--megatron-repo", "https://github.com/Zachary-wW/Loong-Megatron",
            "--dry-run",
        )
        state = json.loads((run_dir / "run_state.json").read_text())
        expected_keys = {
            "hf_path", "model_name", "run_dir", "version", "current_state",
            "model_type", "hf_modeling_path", "omni_path", "megatron_path",
            "gpu_execution_mode", "enable_slice_ckpt", "k8s_yaml_path",
            "k8s_launch_cmd", "wip_code_paths", "phases",
        }
        assert set(state.keys()) == expected_keys, (
            f"run_state.json keys mismatch.\n"
            f"  Expected: {sorted(expected_keys)}\n"
            f"  Got:      {sorted(state.keys())}"
        )
        assert "repos" not in state
        assert "loop" not in state
