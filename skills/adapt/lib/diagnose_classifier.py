"""Diagnose classifier: read-only failure classification for the maker-checker split.

This module is the "checker" side of P16 (maker-checker separation).
It reads validator output + attempts history and produces a classification.
It MUST NOT write code, create files (except escalation via write_escalation),
or call gh methods. It is purely a classifier.

Exports:
  DiagnoseClassification -- enum: CODE_BUG, FLAKY, WRONG_DIRECTION, NEEDS_HUMAN
  DiagnoseResult -- classification + rationale + suggested_fix_summary + failure_signature
  classify_failure -- read-only classification of a validator failure
  write_escalation -- write phases/phaseN/escalation.md on wrong-direction/needs-human
"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from skills.adapt.lib.validator_wrapper import FailureSignature, ValidatorResult


# ---------------------------------------------------------------------------
# DiagnoseClassification enum
# ---------------------------------------------------------------------------

class DiagnoseClassification(str, Enum):
    """Classification of a validator failure (LOOP-04, P16)."""
    CODE_BUG = "code-bug"
    FLAKY = "flaky"
    WRONG_DIRECTION = "wrong-direction"
    NEEDS_HUMAN = "needs-human"


# ---------------------------------------------------------------------------
# DiagnoseResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class DiagnoseResult:
    """Result of classifying a validator failure.

    classification: one of the four DiagnoseClassification values
    rationale: human-readable explanation of the classification
    suggested_fix_summary: advisory suggestion (P11 -- the Edit agent decides what to change)
    failure_signature: the FailureSignature that was classified, or None
    """
    classification: DiagnoseClassification
    rationale: str
    suggested_fix_summary: Optional[str]
    failure_signature: Optional[FailureSignature]


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------

def classify_failure(
    validator_output: ValidatorResult,
    attempts_history: list[dict[str, Any]],
    diff_summary: str = "",
) -> DiagnoseResult:
    """Read-only classification implementing LOOP-04 maker-checker separation.

    Classification logic (ordered by priority):
      (a) If failure_signature is None: return NEEDS_HUMAN (VAL-02, Pitfall 3)
      (b) If 3+ consecutive attempts have same failure_signature.kind AND location:
          return WRONG_DIRECTION (LOOP-05)
      (c) If attempts_history shows same validator alternating pass/fail/pass:
          return FLAKY
      (d) Otherwise: return CODE_BUG

    This function MUST NOT write code, create files (except escalation via
    write_escalation), or call gh methods. It is purely a classifier.
    """
    # (a) VAL-02: Free-text-only failure -> NEEDS_HUMAN
    if validator_output.failure_signature is None:
        return DiagnoseResult(
            classification=DiagnoseClassification.NEEDS_HUMAN,
            rationale="Validator output lacks structured failure signature; cannot classify reliably",
            suggested_fix_summary=None,
            failure_signature=None,
        )

    sig = validator_output.failure_signature

    # (b) LOOP-05: 3+ consecutive attempts with same kind+location -> WRONG_DIRECTION
    consecutive_count = 0
    for entry in reversed(attempts_history):
        fs = entry.get("failure_signature", {})
        if isinstance(fs, dict) and fs.get("kind") == sig.kind and fs.get("location") == sig.location:
            consecutive_count += 1
        else:
            break

    if consecutive_count >= 3:
        return DiagnoseResult(
            classification=DiagnoseClassification.WRONG_DIRECTION,
            rationale=f"No progress after {consecutive_count} attempts on same failure at {sig.location}",
            suggested_fix_summary=None,
            failure_signature=sig,
        )

    # (c) FLAKY: same validator alternating pass/fail/pass
    validator_name = validator_output.name
    verdicts = []
    for entry in attempts_history:
        if entry.get("validator") == validator_name:
            verdicts.append(entry.get("verdict", ""))
    # Check for pass/fail/pass pattern (at least one alternation)
    if len(verdicts) >= 3:
        has_pass = "passed" in verdicts
        has_fail = "failed" in verdicts
        # Detect alternation: pass then fail then pass, or fail then pass then fail
        alternating = False
        for i in range(len(verdicts) - 1):
            if verdicts[i] != verdicts[i + 1] and verdicts[i] in ("passed", "failed") and verdicts[i + 1] in ("passed", "failed"):
                alternating = True
                break
        if has_pass and has_fail and alternating:
            return DiagnoseResult(
                classification=DiagnoseClassification.FLAKY,
                rationale="Validator result inconsistent across reruns; likely non-deterministic",
                suggested_fix_summary=None,
                failure_signature=sig,
            )

    # (d) Default: CODE_BUG
    return DiagnoseResult(
        classification=DiagnoseClassification.CODE_BUG,
        rationale=f"Structured failure: {sig.kind} at {sig.location} (expected {sig.expected}, got {sig.actual})",
        suggested_fix_summary=f"Fix {sig.kind} at {sig.location}",
        failure_signature=sig,
    )


# ---------------------------------------------------------------------------
# write_escalation
# ---------------------------------------------------------------------------

def write_escalation(
    run_dir: Path,
    phase: int,
    classification: DiagnoseClassification,
    rationale: str,
    attempts_summary: list[dict[str, Any]],
) -> Path:
    """Write phases/phaseN/escalation.md (LOOP-05, P4).

    Creates the escalation file with classification, rationale, and
    an escape-hatch instruction for the human.
    Returns the Path to the created file.
    """
    escalation_path = run_dir / "phases" / f"phase{phase}" / "escalation.md"
    escalation_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Phase {phase} Escalation",
        "",
        f"**Classification:** {classification.value}",
        f"**Rationale:** {rationale}",
        "",
        "## Attempts Summary",
    ]
    for entry in attempts_summary:
        attempt = entry.get("attempt", "?")
        verdict = entry.get("verdict", "N/A")
        kind = entry.get("kind", "N/A")
        lines.append(f"- Attempt {attempt}: {verdict} -- {kind}")

    lines.extend([
        "",
        "## Escape Hatch",
        "",
        "This loop has been unable to make progress autonomously. Human intervention is required.",
        f'Review the attempts above and the escalation rationale, then resume with',
        f'`loongforge-adapt --resume <run_dir> --from-phase {phase}`.',
    ])

    escalation_path.write_text("\n".join(lines) + "\n")
    return escalation_path
