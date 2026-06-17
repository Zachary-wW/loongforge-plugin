import importlib.util
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "issue_spec.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_issue_spec", SCRIPT)
issue_spec = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(issue_spec)


def test_make_dedup_key_is_stable_and_slugged():
    key = issue_spec.make_dedup_key(phase=0, root_cause="model_spec missing MTP", gate="Phase 1 Contract")
    assert key == "phase0:model_spec_missing_mtp:phase_1_contract"


def test_issue_spec_renders_markdown_with_checklist():
    spec = issue_spec.IssueSpec(
        dedup_key="phase0:model_spec_missing_mtp:phase1_contract_blocked",
        phase=0,
        title="[Phase 0][DS V4] model_spec misses MTP fields",
        kind="contract-missing",
        severity="blocker",
        goal_blocked="Phase 1 cannot choose DS V4 native strategy without MTP metadata.",
        observed="model_spec.yaml does not contain mtp_num_layers.",
        expected="Phase 0 output records MTP facts or proves MTP is absent.",
        reproduction={"commands": ["loongforge-issue-loop compare-phase --phase 0"], "artifacts": ["run/phases/phase0/model_spec.yaml"]},
        acceptance=["model_spec contains mtp_num_layers", "Phase 1 preflight has no fallback_phase=0"],
        labels=["loongforge-adapt", "phase-0", "ds-v4", "agent-fixable"],
    )
    body = spec.render_markdown()
    assert "## Phase" in body
    assert "Phase 0" in body
    assert "## Dedup key" in body
    assert "`phase0:model_spec_missing_mtp:phase1_contract_blocked`" in body
    assert "- [ ] model_spec contains mtp_num_layers" in body
    assert "Repair agent must reproduce or prove the issue" in body


def test_issue_spec_roundtrip_file(tmp_path):
    spec = issue_spec.IssueSpec(
        dedup_key="phase1:missing_deepseekv4model:baseline_static_compare",
        phase=1,
        title="[Phase 1][DS V4] generated code misses DeepseekV4Model",
        kind="verification-failure",
        severity="high",
        goal_blocked="Phase 1 code is not baseline aligned.",
        observed="Generated roots do not contain DeepseekV4Model.",
        expected="Generated code contains baseline-required DeepseekV4Model symbol.",
        reproduction={"commands": [], "artifacts": []},
        acceptance=["DeepseekV4Model appears in generated code"],
        labels=["phase-1"],
    )
    path = issue_spec.write_issue_spec(tmp_path, spec)
    assert path.name == "phase1-missing_deepseekv4model-baseline_static_compare.yml"
    loaded = issue_spec.load_issue_spec(path)
    assert loaded.dedup_key == spec.dedup_key
    assert loaded.labels == ["phase-1"]
