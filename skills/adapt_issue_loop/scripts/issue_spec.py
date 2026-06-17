"""IssueSpec helpers for loongforge-issue-loop."""
from __future__ import annotations

import re
import sys
import types
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


# Tests load this file with importlib.util.module_from_spec without inserting the
# module into sys.modules first. Python 3.12 dataclasses with postponed
# annotations consult sys.modules during class processing, so register a module
# shell when needed.
if __name__ not in sys.modules:
    sys.modules[__name__] = types.ModuleType(__name__)
sys.modules[__name__].__dict__.update(globals())

_VALID_KINDS = {
    "bug",
    "gap",
    "regression",
    "contract-missing",
    "verification-failure",
    "goal-contract-gap",
}
_VALID_SEVERITIES = {"blocker", "high", "medium", "low"}


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
    return replaced.strip("_") or "unknown"


def make_dedup_key(phase: int, root_cause: str, gate: str) -> str:
    return f"phase{phase}:{slugify(root_cause)}:{slugify(gate)}"


@dataclass
class IssueSpec:
    dedup_key: str
    phase: int
    title: str
    kind: str
    severity: str
    goal_blocked: str
    observed: str
    expected: str
    reproduction: dict[str, Any]
    acceptance: list[str]
    labels: list[str]

    def __post_init__(self) -> None:
        if self.phase not in (0, 1, 2, 3, 4, 5):
            raise ValueError(f"phase must be 0-5, got {self.phase}")
        if self.kind not in _VALID_KINDS:
            raise ValueError(f"invalid issue kind: {self.kind}")
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(f"invalid issue severity: {self.severity}")
        if not self.dedup_key:
            raise ValueError("dedup_key is required")
        if not self.acceptance:
            raise ValueError("acceptance checklist is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IssueSpec":
        return cls(
            dedup_key=data["dedup_key"],
            phase=int(data["phase"]),
            title=data["title"],
            kind=data["kind"],
            severity=data["severity"],
            goal_blocked=data["goal_blocked"],
            observed=data["observed"],
            expected=data["expected"],
            reproduction=data.get("reproduction") or {"commands": [], "artifacts": []},
            acceptance=list(data.get("acceptance") or []),
            labels=list(data.get("labels") or []),
        )

    def render_markdown(self) -> str:
        commands = self.reproduction.get("commands") or []
        artifacts = self.reproduction.get("artifacts") or []
        labels = ", ".join(self.labels) if self.labels else "none"
        lines = [
            "## Phase",
            f"Phase {self.phase}",
            "",
            "## Kind / Severity",
            f"{self.kind} / {self.severity}",
            "",
            "## Goal blocked",
            self.goal_blocked,
            "",
            "## Observed failure",
            self.observed,
            "",
            "## Expected behavior",
            self.expected,
            "",
            "## Evidence",
            "### Commands",
        ]
        if commands:
            lines.extend(f"- `{cmd}`" for cmd in commands)
        else:
            lines.append("- No command-level reproducer recorded; use artifact-level evidence below.")
        lines.extend(["", "### Artifacts"])
        if artifacts:
            lines.extend(f"- `{artifact}`" for artifact in artifacts)
        else:
            lines.append("- No artifacts recorded.")
        lines.extend(["", "## Acceptance checklist"])
        lines.extend(f"- [ ] {item}" for item in self.acceptance)
        lines.extend([
            "",
            "## Dedup key",
            f"`{self.dedup_key}`",
            "",
            "## Labels",
            labels,
            "",
            "## Agent instructions",
            "Repair agent must reproduce or prove the issue before modifying code.",
            "Repair agent must keep the PR scoped to this issue.",
        ])
        return "\n".join(lines) + "\n"


def issue_spec_filename(spec: IssueSpec) -> str:
    safe = spec.dedup_key.replace(":", "-")
    return f"{safe}.yml"


def write_issue_spec(directory: Path, spec: IssueSpec) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / issue_spec_filename(spec)
    path.write_text(yaml.dump(spec.to_dict(), sort_keys=False, allow_unicode=True))
    return path


def load_issue_spec(path: Path) -> IssueSpec:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Invalid issue spec YAML: {path}")
    return IssueSpec.from_dict(data)


sys.modules[__name__].__dict__.update(globals())
