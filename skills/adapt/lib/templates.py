"""PR/issue/comment template rendering with dedup key embedding.

Exports:
  REQUIRED_LABELS       -- base label constant for all bot PRs/issues
  pr_title              -- PR title template (PR-03)
  pr_body               -- PR body template with idempotency footer (PR-03, ISSUE-02)
  issue_title           -- Issue title template (ISSUE-01)
  issue_body            -- Issue body template with dedup key embedding (ISSUE-01, ISSUE-03, D-02)
  dedup_comment         -- Comment appended to existing issue on duplicate failure (ISSUE-03)
  agent_resume_comment  -- Comment posted when human commits detected (PR-05, D-01)
  closing_summary       -- Comment for run-completion issue closure (ISSUE-04)
"""
from __future__ import annotations

from typing import Optional

from skills.adapt.lib.idempotency import compute_dedup_key, format_footer


REQUIRED_LABELS: list[str] = ["loongforge-adapt"]
"""Base label constant. Callers add f\"run-{run_id}\" and f\"phase-{phase}\" at runtime."""


def pr_title(
    run_id: str,
    phase: int,
    attempt: int,
    validator: str = "",
    kind: str = "base",
) -> str:
    """Generate a PR title following the adapt-skill template (PR-03).

    Format: [adapt][{kind}][run-{run_id}] phase-{phase} attempt-{attempt}{validator_suffix}
    """
    validator_suffix = f" ({validator})" if validator else ""
    return f"[adapt][{kind}][run-{run_id}] phase-{phase} attempt-{attempt}{validator_suffix}"


def pr_body(
    run_id: str,
    phase: int,
    attempt: int,
    kind: str = "base",
    validator: str = "",
    diff_summary: str = "",
    fixes_issue: Optional[int] = None,
) -> str:
    """Generate a PR body following the adapt-skill template (PR-03, ISSUE-02).

    Sections: Summary, Validator, Diff Summary, Linked Issue.
    Appends idempotency footer via format_footer.
    """
    sections = []

    # Summary
    sections.append(f"## Summary\n\nAdapt skill {kind} PR for phase {phase}, attempt {attempt}.")

    # Validator
    validator_text = validator if validator else "N/A (base PR)"
    sections.append(f"## Validator\n\n{validator_text}")

    # Diff Summary
    diff_text = diff_summary if diff_summary else "(see PR diff)"
    sections.append(f"## Diff Summary\n\n{diff_text}")

    # Linked Issue
    if fixes_issue is not None:
        sections.append(f"## Linked Issue\n\nFixes #{fixes_issue}")
    else:
        sections.append("## Linked Issue\n\nN/A")

    body = "\n\n".join(sections)
    body += format_footer(run_id, phase, attempt, f"{kind}-pr")
    return body


def issue_title(phase: int, validator_name: str, failure_kind: str) -> str:
    """Generate an issue title following the adapt-skill template (ISSUE-01).

    Format: [adapt] phase-{phase} {validator_name}: {failure_kind}
    """
    return f"[adapt] phase-{phase} {validator_name}: {failure_kind}"


def issue_body(
    phase: int,
    validator_name: str,
    failure_signature: dict,
    log_excerpt: str,
    attempts_jsonl_link: str,
    reproduction_cmd: str,
    run_id: str = "",
    attempt: int = 0,
) -> str:
    """Generate an issue body following the adapt-skill template (ISSUE-01, ISSUE-03, D-02).

    Sections: Failure Signature (table), Log Excerpt, Full Log (details), Attempts Log, Reproduction.
    Embeds [dedup-key: ...] for cross-attempt dedup when failure_signature is non-empty.
    Appends idempotency footer via format_footer.
    """
    sections = []

    # Failure Signature table
    kind = failure_signature.get("kind", "")
    location = failure_signature.get("location", "")
    expected = failure_signature.get("expected", "")
    actual = failure_signature.get("actual", "")
    sections.append(
        "## Failure Signature\n\n"
        "| Field     | Value |\n"
        "|-----------|-------|\n"
        f"| kind      | {kind} |\n"
        f"| location  | {location} |\n"
        f"| expected  | {expected} |\n"
        f"| actual    | {actual} |"
    )

    # Log Excerpt
    sections.append(f"## Log Excerpt\n\n{log_excerpt}")

    # Full Log (collapsible)
    sections.append(
        "<details><summary>Full Log</summary>\n\n"
        "(caller fills from file)\n\n"
        "</details>"
    )

    # Attempts Log
    sections.append(f"## Attempts Log\n\n[attempts.jsonl]({attempts_jsonl_link})")

    # Reproduction
    sections.append(
        "## Reproduction\n\n"
        f"```bash\n{reproduction_cmd}\n```"
    )

    body = "\n\n".join(sections)

    # Dedup key embedding (D-02, ISSUE-03): only if failure_signature is non-empty
    # and contains at least one of "kind" or "location"
    if failure_signature and (kind or location):
        dedup_key = compute_dedup_key(phase, validator_name, failure_signature)
        body += f"\n\n[dedup-key: {dedup_key}]"

    # Idempotency footer
    if run_id:
        body += format_footer(run_id, phase, attempt, "issue")

    return body


def dedup_comment(attempt: int, log_excerpt: str, timestamp: str) -> str:
    """Generate a comment to append to an existing issue on duplicate failure (ISSUE-03, D-02).

    Contains attempt number, log excerpt (collapsible), and timestamp.
    """
    return (
        f"**Attempt {attempt}** ({timestamp})\n\n"
        "<details><summary>Log excerpt</summary>\n\n"
        f"{log_excerpt}\n\n"
        "</details>"
    )


def agent_resume_comment(run_id: str, phase: int) -> str:
    """Generate a comment posted when human commits are detected (PR-05, D-01).

    Informs the user that the loop is paused and how to resume.
    """
    return (
        ":warning: Human commits detected on this branch.\n\n"
        "The adapt skill loop is paused. To resume, please:\n"
        "1. Review the commits above\n"
        f"2. Run `/agent-resume` or invoke `loongforge-adapt --resume <run_dir> --from-phase {phase}`\n\n"
        f"Run ID: `{run_id}` | Phase: {phase}"
    )


def closing_summary(run_id: str, phase: int, outcome: str) -> str:
    """Generate a closing comment for run-completion issue closure (ISSUE-04).

    Contains run_id, phase, and outcome.
    """
    return (
        f"Run `{run_id}` phase-{phase} completed: **{outcome}**\n\n"
        "Closing as part of run finalization."
    )
