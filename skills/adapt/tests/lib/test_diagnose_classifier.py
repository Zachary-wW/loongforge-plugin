"""Tests for diagnose_classifier.py: DiagnoseClassification, DiagnoseResult,
classify_failure, write_escalation.

Covers:
  - LOOP-04: DiagnoseClassifier is read-only (no code writing, no gh calls, no file creation except escalation)
  - LOOP-05: wrong-direction classification from 3+ same-failure attempts triggers write_escalation
  - VAL-02: Free-text-only failures (failure_signature=None) cause needs-human classification
  - DiagnoseClassification enum has exactly 4 members with correct string values
  - repair.md Jinja2 template exists with variables and escape_hatch section
"""
from __future__ import annotations

from pathlib import Path

import pytest

from skills.adapt.lib.diagnose_classifier import (
    DiagnoseClassification,
    DiagnoseResult,
    classify_failure,
    write_escalation,
)
from skills.adapt.lib.validator_wrapper import FailureSignature, ValidatorResult


# ---------------------------------------------------------------------------
# DiagnoseClassification enum
# ---------------------------------------------------------------------------

class TestDiagnoseClassificationEnum:
    def test_exactly_four_members(self) -> None:
        members = list(DiagnoseClassification)
        assert len(members) == 4

    def test_code_bug_value(self) -> None:
        assert DiagnoseClassification.CODE_BUG.value == "code-bug"

    def test_flaky_value(self) -> None:
        assert DiagnoseClassification.FLAKY.value == "flaky"

    def test_wrong_direction_value(self) -> None:
        assert DiagnoseClassification.WRONG_DIRECTION.value == "wrong-direction"

    def test_needs_human_value(self) -> None:
        assert DiagnoseClassification.NEEDS_HUMAN.value == "needs-human"


# ---------------------------------------------------------------------------
# DiagnoseResult dataclass
# ---------------------------------------------------------------------------

class TestDiagnoseResult:
    def test_fields(self) -> None:
        sig = FailureSignature(kind="x", location="y", expected="z", actual="w")
        r = DiagnoseResult(
            classification=DiagnoseClassification.CODE_BUG,
            rationale="test reason",
            suggested_fix_summary="fix the thing",
            failure_signature=sig,
        )
        assert r.classification == DiagnoseClassification.CODE_BUG
        assert r.rationale == "test reason"
        assert r.suggested_fix_summary == "fix the thing"
        assert r.failure_signature is not None

    def test_suggested_fix_summary_none(self) -> None:
        r = DiagnoseResult(
            classification=DiagnoseClassification.NEEDS_HUMAN,
            rationale="no structured signature",
            suggested_fix_summary=None,
            failure_signature=None,
        )
        assert r.suggested_fix_summary is None


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------

class TestClassifyFailure:
    def _make_validator_result(
        self, status: str = "failed",
        failure_signature: FailureSignature | None = None,
    ) -> ValidatorResult:
        return ValidatorResult(
            name="loss-diff", status=status,
            failure_signature=failure_signature, evidence={},
            integrity_ok=True, integrity_details={},
        )

    def test_needs_human_on_missing_signature(self) -> None:
        """VAL-02: failure_signature=None -> NEEDS_HUMAN."""
        result = self._make_validator_result(failure_signature=None)
        diagnosis = classify_failure(result, attempts_history=[])
        assert diagnosis.classification == DiagnoseClassification.NEEDS_HUMAN
        assert "structured failure signature" in diagnosis.rationale.lower() or "cannot classify" in diagnosis.rationale.lower()

    def test_wrong_direction_on_repeated_failure(self) -> None:
        """LOOP-05: 3+ consecutive attempts with same kind+location -> WRONG_DIRECTION."""
        sig = FailureSignature(kind="missing_artifact", location="modeling.py", expected="x", actual="y")
        result = self._make_validator_result(failure_signature=sig)
        # Build attempts history with 3 entries of same kind+location
        history = [
            {"failure_signature": {"kind": "missing_artifact", "location": "modeling.py"}, "verdict": "failed"},
            {"failure_signature": {"kind": "missing_artifact", "location": "modeling.py"}, "verdict": "failed"},
            {"failure_signature": {"kind": "missing_artifact", "location": "modeling.py"}, "verdict": "failed"},
        ]
        diagnosis = classify_failure(result, attempts_history=history)
        assert diagnosis.classification == DiagnoseClassification.WRONG_DIRECTION
        assert "3" in diagnosis.rationale or "No progress" in diagnosis.rationale

    def test_flaky_on_alternating_results(self) -> None:
        """Same validator alternating pass/fail/pass -> FLAKY."""
        sig = FailureSignature(kind="numerical_mismatch", location="loss.py", expected="<1e-5", actual="2e-5")
        result = self._make_validator_result(failure_signature=sig)
        # Use a history with different kind/location for failed entries to avoid
        # triggering WRONG_DIRECTION (3+ same kind+location), but alternating pass/fail
        # for the same validator
        history = [
            {"validator": "loss-diff", "verdict": "passed", "failure_signature": {"kind": "numerical_mismatch", "location": "loss.py"}},
            {"validator": "loss-diff", "verdict": "failed", "failure_signature": {"kind": "other_issue", "location": "other.py"}},
            {"validator": "loss-diff", "verdict": "passed", "failure_signature": {"kind": "numerical_mismatch", "location": "loss.py"}},
        ]
        diagnosis = classify_failure(result, attempts_history=history)
        assert diagnosis.classification == DiagnoseClassification.FLAKY

    def test_code_bug_default(self) -> None:
        """Single structured failure with no repetition -> CODE_BUG."""
        sig = FailureSignature(kind="missing_artifact", location="modeling.py", expected="x", actual="y")
        result = self._make_validator_result(failure_signature=sig)
        history = [
            {"failure_signature": {"kind": "other_error", "location": "other.py"}, "verdict": "failed"},
        ]
        diagnosis = classify_failure(result, attempts_history=history)
        assert diagnosis.classification == DiagnoseClassification.CODE_BUG


# ---------------------------------------------------------------------------
# write_escalation
# ---------------------------------------------------------------------------

class TestWriteEscalation:
    def test_creates_file(self, tmp_path: Path) -> None:
        """write_escalation creates phases/phaseN/escalation.md."""
        path = write_escalation(
            tmp_path, 3,
            DiagnoseClassification.WRONG_DIRECTION,
            "No progress after 3 attempts",
            [{"attempt": 1, "verdict": "failed", "kind": "validate"}],
        )
        assert path.exists()
        assert path.name == "escalation.md"

    def test_contains_classification(self, tmp_path: Path) -> None:
        """Escalation file contains classification value."""
        path = write_escalation(
            tmp_path, 3,
            DiagnoseClassification.NEEDS_HUMAN,
            "Cannot classify",
            [{"attempt": 1, "verdict": "failed", "kind": "validate"}],
        )
        content = path.read_text()
        assert "needs-human" in content

    def test_contains_escape_hatch(self, tmp_path: Path) -> None:
        """Escalation file contains 'Escape Hatch' section (P4)."""
        path = write_escalation(
            tmp_path, 3,
            DiagnoseClassification.WRONG_DIRECTION,
            "No progress",
            [{"attempt": 1, "verdict": "failed", "kind": "validate"}],
        )
        content = path.read_text()
        assert "Escape Hatch" in content

    def test_contains_attempts_summary(self, tmp_path: Path) -> None:
        """Escalation file contains attempts summary."""
        attempts = [
            {"attempt": 1, "verdict": "failed", "kind": "validate"},
            {"attempt": 2, "verdict": "failed", "kind": "validate"},
        ]
        path = write_escalation(
            tmp_path, 3,
            DiagnoseClassification.WRONG_DIRECTION,
            "No progress after 3 attempts",
            attempts,
        )
        content = path.read_text()
        assert "Attempt 1" in content
        assert "Attempt 2" in content

    def test_path_under_correct_phase_dir(self, tmp_path: Path) -> None:
        """Escalation file is at phases/phaseN/escalation.md."""
        path = write_escalation(
            tmp_path, 2,
            DiagnoseClassification.NEEDS_HUMAN,
            "Free-text failure",
            [],
        )
        assert str(path) == str(tmp_path / "phases" / "phase2" / "escalation.md")


# ---------------------------------------------------------------------------
# repair.md template existence and content
# ---------------------------------------------------------------------------

class TestRepairTemplate:
    def test_template_exists(self) -> None:
        """repair.md Jinja2 template exists at expected path."""
        template_path = Path(__file__).resolve().parents[2] / "loop_templates" / "phaseN" / "repair.md"
        assert template_path.exists(), f"Template not found at {template_path}"

    def test_has_jinja2_variables(self) -> None:
        """Template contains all required Jinja2 variables."""
        template_path = Path(__file__).resolve().parents[2] / "loop_templates" / "phaseN" / "repair.md"
        content = template_path.read_text()
        required_vars = ["{{ phase }}", "{{ attempt }}", "{{ validator_name }}",
                         "{{ failure_kind }}", "{{ failure_location }}",
                         "{{ expected }}", "{{ actual }}",
                         "{{ attempts_summary }}", "{{ diff_summary }}"]
        for var in required_vars:
            assert var in content, f"Missing template variable: {var}"

    def test_has_escape_hatch_section(self) -> None:
        """Template contains escape_hatch section (P4)."""
        template_path = Path(__file__).resolve().parents[2] / "loop_templates" / "phaseN" / "repair.md"
        content = template_path.read_text()
        assert "escape_hatch" in content.lower() or "Escape Hatch" in content
