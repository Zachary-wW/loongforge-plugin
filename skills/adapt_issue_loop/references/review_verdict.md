# `review_verdict.yml` Schema

Authoritative schema for the file the **independent reviewer** sub-agent (`adapt-reviewer`) emits at the end of a repair PR review.

The file lives at:

```text
.loongforge/issue-loop/review_verdicts/issue-<n>.yml
```

Where `<n>` is the GitHub Issue number the PR is linked to.

The merge gate at `skills/adapt_issue_loop/scripts/verification.py` consumes the `verdict` field via the gate-input YAML's `review_verdict` key. A missing or non-`approved` value blocks merge.

## Required fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | int | Currently `1`. |
| `issue_id` | int | Linked GitHub Issue number. |
| `pr` | int | Reviewed pull request number. |
| `verdict` | enum | `approved`, `request_changes`, `block`, or `needs_human`. |
| `summary` | string | One paragraph: what changed, why mergeable (or not). |
| `findings` | list | Possibly empty. Each finding has `severity`, `where`, `note`. |
| `evidence` | list | Read-only commands or file paths the reviewer consulted. |

## `verdict` semantics

- `approved` — all gates green; findings at most `nit`. Maps to merge-gate `review_verdict: approved`.
- `request_changes` — fixable in place; reviewer flagged at least one `[request]`. Maps to merge-gate `review_verdict: changes_requested` (gate blocks).
- `block` — non-fixable-in-place defect (scope violation, broken acceptance, regressing comparator, contract-field deletion). Gate blocks; PR should not be merged even if other findings are addressed.
- `needs_human` — prerequisites missing or judgment exceeds the autonomous loop. Gate blocks; main session escalates.

## Finding severity

| Tag | Meaning | Effect on verdict |
|---|---|---|
| `block` | Must fix before merge | Forces `verdict: block` (or `request_changes` if reviewer judges in-place fixable) |
| `request` | Should fix | Forces at least `request_changes` |
| `nit` | Optional cleanup | No effect on verdict |

Each finding MUST include a concrete `where` (file path + line range, or a command + expected output excerpt). Findings without a verifiable locator are not allowed.

## Example

```yaml
schema_version: 1
issue_id: 29
pr: 31
verdict: approved
summary: "Adds adapt-reviewer agent and review_verdict.yml schema; SKILL.md now mandates dispatching the reviewer before constructing the gate input. No code paths in the merge gate changed."
findings:
  - severity: nit
    where: "skills/adapt_issue_loop/SKILL.md#review-and-merge-gate"
    note: "Could link to the schema doc inline; not blocking."
evidence:
  - "gh pr diff 31"
  - "agents/adapt-reviewer.md"
  - "skills/adapt_issue_loop/scripts/verification.py:33"
```

## Where this file is consumed

1. Repair flow writes `review_verdict.yml` after the reviewer's structured response.
2. The merge-gate input YAML's `review_verdict` field is set to one of:
   - `approved` — when verdict is `approved`
   - `changes_requested` — when verdict is `request_changes`, `block`, or `needs_human`
3. `loongforge-issue-loop verify-merge-gate --inputs <gate.yml>` rejects merge unless `review_verdict == "approved"`.

## Versioning

Bump `schema_version` on any breaking change to required fields. Older verdict files remain readable; the gate only checks the mapped `review_verdict` value.
