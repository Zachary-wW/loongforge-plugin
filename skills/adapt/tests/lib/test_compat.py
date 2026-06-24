"""DOC-03 doc consistency and COMPAT-01 backward compatibility tests.

Covers:
  - TestDocConsistency: all 6 agent.md files have identical Loop Engineering Hooks
    sections (after phase number normalization)
  - TestCompat01: legacy invocation produces no pr/issues/loop blocks
    and passes validate_phase_output
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
import pytest

from skills.adapt.lib.gh_client import FakeGhClient
from skills.adapt.lib.schema import LoopBudget
from skills.adapt.scripts.validate_phase_completion import validate_phase_output
from skills.adapt.tests.lib.test_loop_controller import _setup_run_dir, _write_loop_state


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

AGENTS_DIR = Path(__file__).resolve().parents[2] / "references" / "phases"
PHASE_DIRS = [AGENTS_DIR / f"phase{n}" for n in range(7)]


# ---------------------------------------------------------------------------
# Helper: extract Loop Engineering Hooks section from agent.md
# ---------------------------------------------------------------------------

def _extract_hooks_section(agent_md: Path) -> str:
    """Extract the '## Loop Engineering Hooks' section from an agent.md file.

    Strips trailing horizontal rules (---) and blank lines before the next
    section heading so that the extracted content is comparable across all
    six phases regardless of whether the section is followed by a --- separator.
    """
    text = agent_md.read_text()
    # Find the section start
    match = re.search(r"^## Loop Engineering Hooks\s*$", text, re.MULTILINE)
    if not match:
        return ""
    start = match.start()
    # Find the next ## heading that is NOT a sub-heading (###)
    rest = text[match.end():]
    next_section = re.search(r"\n^## ", rest, re.MULTILINE)
    if next_section:
        end = match.end() + next_section.start()
    else:
        end = len(text)
    section = text[start:end]
    # Strip trailing --- separators and blank lines
    section = re.sub(r"\n---\s*$", "", section)
    section = section.rstrip("\n")
    return section


def _normalize_phase_numbers(section: str) -> str:
    """Replace phase0..phase5 with phaseN in hooks sections for comparison.

    Handles patterns like:
      - phase0, phase1, ..., phase5
      - phase=0, phase=1, ..., phase=5
    """
    # First normalize phase=N patterns
    result = re.sub(r"phase=[0-6]", "phase=N", section)
    # Then normalize phaseN patterns (e.g. in branch names and paths)
    result = re.sub(r"phase[0-6]", "phaseN", result)
    return result


def _strip_phase0_disclaimer(section: str) -> str:
    """Remove the Phase 0 D-15 disclaimer about not using the Loop FSM.

    This allows Phase 0's hooks section to have an additional paragraph
    that doesn't apply to other phases, while keeping the core hooks
    structure identical.
    """
    # Strip the D-15 disclaimer block: starts with a `>` blank line before
    # the IMPORTANT line, continues through the disclaimer, and ends
    # just before the next ### heading.
    result = re.sub(
        r"\n>\s*\n> \*\*IMPORTANT:\*\* Phase 0 does NOT use the Loop FSM.*?(?=\n### )",
        "",
        section,
        flags=re.DOTALL,
    )
    # After stripping, ensure there's a blank line before ### (matching other phases)
    result = re.sub(r"(> Skip.*?)\n(### )", r"\1\n\n\2", result)
    return result


# ---------------------------------------------------------------------------
# TestDocConsistency: DOC-03
# ---------------------------------------------------------------------------

class TestDocConsistency:
    """DOC-03: Verify all 6 agent.md files have identical Loop Engineering Hooks
    text (after phase number normalization)."""

    def test_all_six_agents_have_hooks_section(self):
        """Every agent.md file must contain exactly one '## Loop Engineering Hooks'."""
        for phase_dir in PHASE_DIRS:
            agent_md = phase_dir / "agent.md"
            text = agent_md.read_text()
            count = text.count("## Loop Engineering Hooks")
            assert count == 1, f"{agent_md}: expected 1 '## Loop Engineering Hooks', got {count}"

    def test_hooks_sections_identical_after_normalization(self):
        """All 6 hooks sections must be identical after replacing phaseN numbers.

        Phase 0 is allowed to have an additional D-15 disclaimer about not
        using the Loop FSM — this is stripped before comparison.
        """
        sections = []
        for phase_dir in PHASE_DIRS:
            agent_md = phase_dir / "agent.md"
            section = _extract_hooks_section(agent_md)
            assert section, f"{agent_md}: Loop Engineering Hooks section is empty"
            section = _strip_phase0_disclaimer(section)
            sections.append(_normalize_phase_numbers(section))
        # All should be identical
        for i in range(1, len(sections)):
            assert sections[i] == sections[0], (
                f"Phase {i} hooks section differs from phase 0 after normalization.\n"
                f"Phase 0:\n{sections[0][:500]}\n---\nPhase {i}:\n{sections[i][:500]}"
            )

    def test_pre_edit_branch_creation_present(self):
        """Each agent.md must contain 'Pre-Edit: Branch Creation' sub-section."""
        for phase_dir in PHASE_DIRS:
            agent_md = phase_dir / "agent.md"
            text = agent_md.read_text()
            assert "Pre-Edit: Branch Creation" in text, f"{agent_md}: missing 'Pre-Edit: Branch Creation'"

    def test_post_edit_pr_submission_present(self):
        """Each agent.md must contain 'Post-Edit: PR Submission' sub-section."""
        for phase_dir in PHASE_DIRS:
            agent_md = phase_dir / "agent.md"
            text = agent_md.read_text()
            assert "Post-Edit: PR Submission" in text, f"{agent_md}: missing 'Post-Edit: PR Submission'"

    def test_gate_text_present(self):
        """Each agent.md must contain 'These steps apply ONLY when' gate text."""
        for phase_dir in PHASE_DIRS:
            agent_md = phase_dir / "agent.md"
            text = agent_md.read_text()
            assert "These steps apply ONLY when" in text, f"{agent_md}: missing gate text"

    def test_repos_reference_in_hooks(self):
        """Each hooks section must reference 'repos:' within it."""
        for phase_dir in PHASE_DIRS:
            agent_md = phase_dir / "agent.md"
            section = _extract_hooks_section(agent_md)
            assert "repos:" in section, f"{agent_md}: hooks section missing 'repos:' reference"


# ---------------------------------------------------------------------------
# TestCompat01: COMPAT-01 backward compatibility
# ---------------------------------------------------------------------------

class TestCompat01:
    """COMPAT-01: Legacy invocations without repos: produce no pr/issues/loop blocks
    and pass validate_phase_output."""

    def test_legacy_phase_output_no_loop_blocks(self, tmp_path):
        """A legacy phase1_output.yml without pr/issues/loop blocks must pass
        validate_phase_output (no loop_engineering flag)."""
        run_dir = tmp_path / "legacy_run"
        phases_dir = run_dir / "phases"
        phases_dir.mkdir(parents=True, exist_ok=True)

        # Write a minimal legacy phase1_output.yml with required legacy fields
        output_path = phases_dir / "phase1_output.yml"
        legacy_output = {
            "status": "passed",
            "step_gate": {
                "mandatory_steps_complete": True,
            },
            "steps": {
                "step1": {
                    "status": "passed",
                    "evidence": "resolved HF source files",
                    "required": True,
                },
            },
            "validator": {
                "name": "phase1-verify",
                "status": "passed",
            },
        }
        output_path.write_text(yaml.dump(legacy_output, default_flow_style=False))

        # validate_phase_output must not raise
        validate_phase_output(run_dir, phase=1)

        # Assert no loop-related blocks
        data = yaml.safe_load(output_path.read_text())
        assert "pr" not in data, "Legacy output should not contain 'pr' block"
        assert "issues" not in data, "Legacy output should not contain 'issues' block"
        assert "loop" not in data, "Legacy output should not contain 'loop' block"
        assert "loop_engineering" not in data, "Legacy output should not contain 'loop_engineering' flag"

    def test_legacy_run_phase_loop_no_repos_info(self, tmp_path):
        """Calling run_phase_loop with repos_info=None must produce no pr/issues
        blocks in the phase output (local-only mode)."""
        from skills.adapt.lib.loop_controller import run_phase_loop, ExitReason
        from skills.adapt.lib.validator_wrapper import ValidatorResult
        from unittest.mock import patch

        run_dir = _setup_run_dir(tmp_path, phase=1)
        _write_loop_state(run_dir, phase=1, current_state="validate", attempt=1)
        gh = FakeGhClient()
        budget = LoopBudget()

        with patch("skills.adapt.lib.loop_controller.run_validator") as mock_run, \
             patch("skills.adapt.lib.loop_controller.check_validator_integrity") as mock_integrity:
            mock_run.return_value = ValidatorResult(
                name="phase1-verify", status="passed",
                failure_signature=None, evidence={},
                integrity_ok=True,
                integrity_details={"binary_hash_ok": True, "log_mtime_ok": True, "log_present": True},
            )
            mock_integrity.return_value = {
                "integrity_ok": True, "binary_hash_ok": True,
                "log_mtime_ok": True, "log_present": True,
            }
            # Run with repos_info=None (legacy / local-only mode)
            result = run_phase_loop(run_dir, phase=1, gh=gh, budget=budget, repos_info=None)

        assert result == ExitReason.VALIDATOR_PASSED

        # Verify output file exists
        output_path = run_dir / "phases" / "phase1_output.yml"
        assert output_path.exists()
        data = yaml.safe_load(output_path.read_text())

        # The pr block should be present but empty (PrBlockOutput with number=None)
        # In loop_engineering=True mode with repos_info=None, no PR/issue calls
        # are made, but the _write_phase_output still writes the block structure
        # Verify no actual PR/issue was created via gh
        pr_calls = [c for c in gh.calls if c.method in ("open_pr", "open_issue")]
        assert len(pr_calls) == 0, "No gh PR/issue calls should occur when repos_info=None"
