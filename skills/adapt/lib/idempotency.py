"""Idempotency key computation, footer format/parse, and dedup key computation.

Exports:
  IdempotencyFooter -- NamedTuple with parsed footer fields
  compute_idempotency_key -- SHA256(run_id:phase:attempt:action_kind) for crash-resume dedup
  format_footer -- HTML comment footer + visible fallback for PR/issue bodies
  parse_footer -- Extract IdempotencyFooter from body text
  compute_dedup_key -- SHA256(phase:validator:kind:location) for cross-attempt issue dedup
"""
from __future__ import annotations

import hashlib
import re
from typing import NamedTuple, Optional


class IdempotencyFooter(NamedTuple):
    """Parsed fields from an idempotency footer in a PR/issue body."""
    run_id: str
    phase: int
    attempt: int
    action: str
    key: str


def compute_idempotency_key(run_id: str, phase: int, attempt: int, action_kind: str) -> str:
    """Compute a deterministic idempotency key for crash-resume dedup (RESUME-03).

    Same inputs always produce the same 64-char lowercase hex string.
    This enables find_by_idempotency_key to locate existing PRs/issues after a crash.
    """
    raw = f"{run_id}:{phase}:{attempt}:{action_kind}"
    return hashlib.sha256(raw.encode()).hexdigest()


def format_footer(run_id: str, phase: int, attempt: int, action_kind: str) -> str:
    """Generate an idempotency footer for embedding in PR/issue bodies.

    Includes both an HTML comment (invisible in rendered Markdown) and a visible
    machine-readable fallback line (searchable even if GitHub does not index HTML
    comments).
    """
    key = compute_idempotency_key(run_id, phase, attempt, action_kind)
    return (
        f"\n[adapt-skill-key: {key}]"
        f"\n<!-- adapt-skill: run={run_id} phase={phase} attempt={attempt} action={action_kind} key={key} -->\n"
    )


_FOOTER_PATTERN = re.compile(
    r"<!-- adapt-skill: run=(\S+) phase=(\d+) attempt=(\d+) action=(\S+) key=([a-f0-9]{64}) -->"
)


def parse_footer(body: str) -> Optional[IdempotencyFooter]:
    """Extract the first idempotency footer from a PR/issue body.

    Returns IdempotencyFooter with parsed fields, or None if no footer found.
    """
    match = _FOOTER_PATTERN.search(body)
    if match is None:
        return None
    return IdempotencyFooter(
        run_id=match.group(1),
        phase=int(match.group(2)),
        attempt=int(match.group(3)),
        action=match.group(4),
        key=match.group(5),
    )


def compute_dedup_key(phase: int, validator_name: str, failure_signature: dict) -> str:
    """Compute a deterministic dedup key for cross-attempt issue dedup (ISSUE-03, D-02).

    Same (phase, validator, kind, location) always produces the same key, enabling
    open_issue to find existing issues for the same failure across different attempts.
    This key is DIFFERENT from the idempotency key: idempotency key is unique per
    (run_id, phase, attempt, action_kind) for crash-resume; dedup key is unique per
    (phase, validator, kind, location) for issue dedup.
    """
    kind = failure_signature.get("kind", "")
    location = failure_signature.get("location", "")
    raw = f"{phase}:{validator_name}:{kind}:{location}"
    return hashlib.sha256(raw.encode()).hexdigest()
