"""Paths the loop's PR helper (Phase 2) must never include in a fix-PR diff.

A PR touching any of these is auto-rejected and converted to human_needed
escalation (Pitfall 16, REQ-PR-06)."""
from __future__ import annotations

import fnmatch

PROTECTED_PATHS: tuple[str, ...] = (
    # Phase validators (the "checker" side of maker-checker)
    "skills/adapt/references/phases/*/verify.md",
    "skills/adapt/references/phases/*/loss_diff.md",
    "skills/adapt/references/phases/*/performance_tuning_gate.md",
    "skills/adapt/references/phases/*/feature_compat.md",
    "skills/adapt/references/phases/*/kb_consistency.md",
    # Phase gate enforcement
    "skills/adapt/scripts/validate_phase_completion.py",
    "bin/loongforge-phase-gate",
    # Loop engineering safety primitives
    "skills/adapt/lib/redact.py",
    "skills/adapt/lib/protected_paths.py",
    "skills/adapt/lib/preflight.py",
    # Validator scripts inside each phase (Phase 1-4 verify scripts)
    "skills/adapt/scripts/perf_review.py",   # Phase 4 perf gate
    "skills/adapt/scripts/hf_forward.py",    # Phase 1 forward verify
)


def is_protected(repo_relative_path: str) -> bool:
    """Return True if a PR touching `repo_relative_path` should be auto-rejected.

    Path is interpreted relative to the loongforge-plugin repo root, NOT to
    the external LoongForge / Loong-Megatron repos. (Those repos' validators
    are out of scope for this protection -- they aren't validators we wrote.)
    """
    return any(fnmatch.fnmatch(repo_relative_path, pat) for pat in PROTECTED_PATHS)
