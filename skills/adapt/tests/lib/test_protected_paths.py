"""Tests for skills.adapt.lib.protected_paths — validator-protected-paths data module."""
from __future__ import annotations

from skills.adapt.lib.protected_paths import PROTECTED_PATHS, is_protected


def test_protected_paths_non_empty():
    assert len(PROTECTED_PATHS) >= 1


def test_validate_phase_completion_is_protected():
    assert is_protected("skills/adapt/scripts/validate_phase_completion.py") is True


def test_loongforge_phase_gate_is_protected():
    assert is_protected("bin/loongforge-phase-gate") is True


def test_phase1_verify_md_is_protected():
    assert is_protected("skills/adapt/references/phases/phase1/verify.md") is True


def test_readme_is_not_protected():
    assert is_protected("README.md") is False


def test_arbitrary_source_is_not_protected():
    assert is_protected("skills/adapt/some_new_file.py") is False


def test_redact_is_protected():
    assert is_protected("skills/adapt/lib/redact.py") is True


def test_protected_paths_itself_is_protected():
    assert is_protected("skills/adapt/lib/protected_paths.py") is True
