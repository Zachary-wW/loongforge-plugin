#!/usr/bin/env python3
"""LoongForge issue-driven adapt loop CLI."""
from __future__ import annotations

import argparse


DESCRIPTION = "LoongForge issue-driven adapt loop"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--version", action="version", version="loongforge-issue-loop 0.1.0")
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init", help="Initialize local issue-loop state")
    init.add_argument("--target", help="Target path or identifier for initialization")
    init.add_argument("--repo", help="Repository path or slug")

    compare_phase = sub.add_parser("compare-phase", help="Compare a phase against static baseline rules")
    compare_phase.add_argument("--phase", help="Phase identifier to compare")
    compare_phase.add_argument("--run-dir", help="Run directory containing comparator inputs")

    sub.add_parser("issue-from-report", help="Create IssueSpec files from a comparator report")

    sync_issue = sub.add_parser("sync-issue", help="Create or update a GitHub Issue from an IssueSpec")
    sync_issue.add_argument("--issue-spec", help="Path to an IssueSpec file")
    sync_issue.add_argument("--dry-run", action="store_true", help="Parse and validate without changing GitHub")

    sub.add_parser("verify-merge-gate", help="Evaluate deterministic merge-gate inputs")
    sub.add_parser("run-dry", help="Run local dry-run pipeline without touching GitHub")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    parser.error(f"subcommand not implemented yet: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
