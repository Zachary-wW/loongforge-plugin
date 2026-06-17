"""GitHub issue sync helpers for loongforge-issue-loop."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import sys

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import issue_spec


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = ["gh", *args]
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        raise RuntimeError(f"gh command failed: {' '.join(cmd)}{': ' + stderr if stderr else ''}") from exc


def _find_issue(repo: str, dedup_key: str) -> dict[str, Any] | None:
    result = _run_gh([
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--search",
        f'"{dedup_key}" in:body',
        "--json",
        "number,url,state,title",
        "--limit",
        "10",
    ])
    try:
        issues = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh issue list returned invalid JSON") from exc
    if not isinstance(issues, list):
        raise RuntimeError("gh issue list returned non-list JSON")
    return issues[0] if issues else None


def _create_issue(repo: str, spec: issue_spec.IssueSpec, body: str) -> str:
    args = ["issue", "create", "--repo", repo, "--title", spec.title, "--body", body]
    for label in spec.labels:
        args.extend(["--label", label])
    result = _run_gh(args)
    return result.stdout.strip()


def _comment_issue(repo: str, number: int, body: str) -> None:
    _run_gh(["issue", "comment", str(number), "--repo", repo, "--body", body])


def _reopen_issue(repo: str, number: int) -> None:
    _run_gh(["issue", "reopen", str(number), "--repo", repo])


def sync_issue(repo: str, spec: issue_spec.IssueSpec, dry_run: bool) -> dict[str, Any]:
    body = spec.render_markdown()
    if dry_run:
        return {
            "mode": "dry-run",
            "action": "create",
            "repo": repo,
            "title": spec.title,
            "body": body,
            "labels": spec.labels,
            "dedup_key": spec.dedup_key,
        }

    existing = _find_issue(repo, spec.dedup_key)
    if existing:
        number = int(existing["number"])
        action = "update"
        if str(existing.get("state", "")).lower() == "closed":
            _reopen_issue(repo, number)
            action = "reopen"
        comment = f"New evidence for `{spec.dedup_key}`\n\n{body}"
        _comment_issue(repo, number, comment)
        return {
            "mode": "apply",
            "action": action,
            "issue_url": existing.get("url", ""),
            "issue_number": number,
        }

    issue_url = _create_issue(repo, spec, body)
    return {"mode": "apply", "action": "create", "issue_url": issue_url}
