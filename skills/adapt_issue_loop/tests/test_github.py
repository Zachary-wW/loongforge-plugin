import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
ISSUE_SPEC_SCRIPT = SCRIPTS_DIR / "issue_spec.py"
GITHUB_SCRIPT = SCRIPTS_DIR / "github.py"

ISSUE_SPEC_SPEC = importlib.util.spec_from_file_location("issue_loop_issue_spec_for_github", ISSUE_SPEC_SCRIPT)
issue_spec = importlib.util.module_from_spec(ISSUE_SPEC_SPEC)
assert ISSUE_SPEC_SPEC and ISSUE_SPEC_SPEC.loader
sys.modules[ISSUE_SPEC_SPEC.name] = issue_spec
ISSUE_SPEC_SPEC.loader.exec_module(issue_spec)

GITHUB_SPEC = importlib.util.spec_from_file_location("issue_loop_github", GITHUB_SCRIPT)
github = importlib.util.module_from_spec(GITHUB_SPEC)
assert GITHUB_SPEC and GITHUB_SPEC.loader
sys.modules[GITHUB_SPEC.name] = github
GITHUB_SPEC.loader.exec_module(github)


def _spec():
    return issue_spec.IssueSpec(
        dedup_key="phase1:missing_deepseekv4model:baseline_static_compare",
        phase=1,
        title="[Phase 1][DS V4] generated code misses DeepseekV4Model",
        kind="verification-failure",
        severity="high",
        goal_blocked="Phase 1 code is not baseline aligned.",
        observed="Generated roots do not contain DeepseekV4Model.",
        expected="Generated code contains baseline-required DeepseekV4Model symbol.",
        reproduction={"commands": ["loongforge-issue-loop compare-phase --phase 1"], "artifacts": ["run/phases/phase1/report.md"]},
        acceptance=["DeepseekV4Model appears in generated code"],
        labels=["loongforge-adapt", "phase-1", "agent-fixable"],
    )


def test_sync_issue_dry_run_create_payload():
    spec = _spec()

    result = github.sync_issue("owner/repo", spec, dry_run=True)

    assert result["mode"] == "dry-run"
    assert result["action"] == "create"
    assert result["repo"] == "owner/repo"
    assert result["title"] == spec.title
    assert result["labels"] == spec.labels
    assert result["dedup_key"] == spec.dedup_key
    assert "## Dedup key" in result["body"]
    assert f"`{spec.dedup_key}`" in result["body"]


def test_sync_issue_apply_creates_when_no_existing_issue(monkeypatch):
    spec = _spec()
    calls = []

    def fake_run(cmd, *, check, capture_output, text):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        if cmd[:3] == ["gh", "issue", "create"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/owner/repo/issues/42\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(github.subprocess, "run", fake_run)

    result = github.sync_issue("owner/repo", spec, dry_run=False)

    assert result == {"mode": "apply", "action": "create", "issue_url": "https://github.com/owner/repo/issues/42"}
    assert calls[0] == [
        "gh",
        "issue",
        "list",
        "--repo",
        "owner/repo",
        "--state",
        "all",
        "--search",
        f'"{spec.dedup_key}" in:body',
        "--json",
        "number,url,state,title",
        "--limit",
        "10",
    ]
    create_cmd = calls[1]
    assert create_cmd[:8] == ["gh", "issue", "create", "--repo", "owner/repo", "--title", spec.title, "--body"]
    assert f"`{spec.dedup_key}`" in create_cmd[8]
    assert create_cmd[9:] == [
        "--label",
        "loongforge-adapt",
        "--label",
        "phase-1",
        "--label",
        "agent-fixable",
    ]


def test_sync_issue_apply_creates_without_labels_when_repo_lacks_labels(monkeypatch):
    spec = _spec()
    calls = []

    def fake_run(cmd, *, check, capture_output, text):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        if cmd[:3] == ["gh", "issue", "create"] and "--label" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="could not add label: 'loongforge-adapt' not found")
        if cmd[:3] == ["gh", "issue", "create"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/owner/repo/issues/43\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(github.subprocess, "run", fake_run)

    result = github.sync_issue("owner/repo", spec, dry_run=False)

    assert result == {"mode": "apply", "action": "create", "issue_url": "https://github.com/owner/repo/issues/43"}
    assert "--label" in calls[1]
    assert calls[2] == ["gh", "issue", "create", "--repo", "owner/repo", "--title", spec.title, "--body", calls[1][8]]


def test_sync_issue_apply_comments_when_existing_issue_found(monkeypatch):
    spec = _spec()
    calls = []
    existing = [{"number": 7, "url": "https://github.com/owner/repo/issues/7", "state": "OPEN", "title": spec.title}]

    def fake_run(cmd, *, check, capture_output, text):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(existing), stderr="")
        if cmd[:3] == ["gh", "issue", "comment"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(github.subprocess, "run", fake_run)

    result = github.sync_issue("owner/repo", spec, dry_run=False)

    assert result == {
        "mode": "apply",
        "action": "update",
        "issue_url": "https://github.com/owner/repo/issues/7",
        "issue_number": 7,
    }
    assert calls[1][:6] == ["gh", "issue", "comment", "7", "--repo", "owner/repo"]
    assert calls[1][6] == "--body"
    assert calls[1][7].startswith("New evidence for `phase1:missing_deepseekv4model:baseline_static_compare`")
    assert "## Dedup key" in calls[1][7]


def test_sync_issue_apply_reopens_closed_existing_issue_before_commenting(monkeypatch):
    spec = _spec()
    calls = []
    existing = [{"number": 7, "url": "https://github.com/owner/repo/issues/7", "state": "CLOSED", "title": spec.title}]

    def fake_run(cmd, *, check, capture_output, text):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(existing), stderr="")
        if cmd[:3] == ["gh", "issue", "reopen"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["gh", "issue", "comment"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(github.subprocess, "run", fake_run)

    result = github.sync_issue("owner/repo", spec, dry_run=False)

    assert result == {
        "mode": "apply",
        "action": "reopen",
        "issue_url": "https://github.com/owner/repo/issues/7",
        "issue_number": 7,
    }
    assert calls[1] == ["gh", "issue", "reopen", "7", "--repo", "owner/repo"]
    assert calls[2][:6] == ["gh", "issue", "comment", "7", "--repo", "owner/repo"]
    assert "## Dedup key" in calls[2][7]
