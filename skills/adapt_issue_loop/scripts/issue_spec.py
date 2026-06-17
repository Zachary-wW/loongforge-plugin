"""IssueSpec helpers for loongforge-issue-loop."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


_VALID_KINDS = {
    "bug",
    "gap",
    "regression",
    "contract-missing",
    "verification-failure",
    "goal-contract-gap",
}
_VALID_SEVERITIES = {"blocker", "high", "medium", "low"}
_DEDUP_KEY_RE = re.compile(r"^phase\d:[a-z0-9_]+:[a-z0-9_]+$")


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
        validate_dedup_key(self.dedup_key)
        self.reproduction = _validate_reproduction(self.reproduction)
        self.acceptance = _validate_string_list(self.acceptance, "acceptance")
        self.labels = _validate_string_list(self.labels, "labels")
        if not self.acceptance:
            raise ValueError("acceptance checklist is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IssueSpec":
        if not isinstance(data, Mapping):
            raise ValueError("issue spec must be a mapping")
        return cls(
            dedup_key=data["dedup_key"],
            phase=int(data["phase"]),
            title=data["title"],
            kind=data["kind"],
            severity=data["severity"],
            goal_blocked=data["goal_blocked"],
            observed=data["observed"],
            expected=data["expected"],
            reproduction=_validate_reproduction(data.get("reproduction", {})),
            acceptance=_validate_string_list(data.get("acceptance", []), "acceptance"),
            labels=_validate_string_list(data.get("labels", []), "labels"),
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
            lines.extend(_render_code_blocks(commands))
        else:
            lines.append("- No command-level reproducer recorded; use artifact-level evidence below.")
        lines.extend(["", "### Artifacts"])
        if artifacts:
            lines.extend(_render_code_blocks(artifacts))
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


def validate_dedup_key(dedup_key: str) -> None:
    if not isinstance(dedup_key, str) or not _DEDUP_KEY_RE.fullmatch(dedup_key):
        raise ValueError("dedup_key must match phase<digit>:<slug>:<slug>")


def _validate_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return value


def _validate_reproduction(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        raise ValueError("reproduction must be a mapping")
    commands = _validate_string_list(value.get("commands", []), "reproduction.commands")
    artifacts = _validate_string_list(value.get("artifacts", []), "reproduction.artifacts")
    return {"commands": commands, "artifacts": artifacts}


def _render_code_blocks(values: list[str]) -> list[str]:
    lines: list[str] = []
    for value in values:
        fence = _fence_for(value)
        lines.extend(["-", fence, value, fence])
    return lines


def _fence_for(value: str) -> str:
    longest_run = max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)
    return "`" * max(3, longest_run + 1)


def issue_spec_filename(spec: IssueSpec) -> str:
    validate_dedup_key(spec.dedup_key)
    safe = spec.dedup_key.replace(":", "-")
    return f"{safe}.yml"


def write_issue_spec(directory: Path, spec: IssueSpec) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / issue_spec_filename(spec)
    path.write_text(yaml.dump(spec.to_dict(), sort_keys=False, allow_unicode=True))
    return path


def load_issue_spec(path: Path) -> IssueSpec:
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid issue spec YAML: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid issue spec YAML: {path}")
    return IssueSpec.from_dict(data)
