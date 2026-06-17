import importlib.util
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "state.py"
SPEC = importlib.util.spec_from_file_location("issue_loop_state", SCRIPT)
state = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(state)


def test_default_state_records_ds_v4_baseline():
    data = state.default_state(repo="Zachary-wW/loongforge-plugin")
    assert data["target_case"] == "ds_v4"
    assert data["baseline"]["megatron"]["commit"] == "12713af0"
    assert data["baseline"]["omni"]["commit"] == "83e71867"
    assert data["scope"]["phases_enabled"] == [0, 1, 2]
    assert data["scope"]["phases_deferred"][3].startswith("Mac no GPU")
    assert data["merge_policy"] == "auto_after_review_and_verification"


def test_default_goal_contract_has_phase0_1_2_and_deferred_runtime():
    contract = state.default_goal_contract()
    assert sorted(contract.keys()) == ["phase0", "phase1", "phase2", "phase3", "phase4"]
    assert contract["phase0"]["version"] == 1
    assert "MLA" in "\n".join(contract["phase0"]["acceptance"])
    assert "framework-native" in "\n".join(contract["phase1"]["acceptance"])
    assert "tensor" in "\n".join(contract["phase2"]["acceptance"])
    assert contract["phase3"]["status"] == "deferred"
    assert contract["phase4"]["status"] == "deferred"


def test_init_loop_state_writes_state_and_contract(tmp_path):
    state_dir = state.init_loop_state(
        plugin_root=tmp_path,
        repo="Zachary-wW/loongforge-plugin",
    )
    assert state_dir == tmp_path / ".loongforge" / "issue-loop"
    loaded_state = yaml.safe_load((state_dir / "state.yml").read_text())
    loaded_contract = yaml.safe_load((state_dir / "phase_goal_contract.yml").read_text())
    assert loaded_state["active_phase"] == 0
    assert loaded_state["limits"]["max_iterations_per_issue"] == 5
    assert loaded_contract["phase0"]["goal"].startswith("Extract enough DS V4")


def test_init_loop_state_preserves_existing_files_unless_forced(tmp_path):
    state_dir = state.init_loop_state(plugin_root=tmp_path, repo="owner/repo")
    state_path = state_dir / "state.yml"
    contract_path = state_dir / "phase_goal_contract.yml"

    state_path.write_text(yaml.dump({"repo": "custom/repo", "active_phase": 2}))
    contract_path.write_text(yaml.dump({"phase0": {"goal": "custom goal", "comparator_rules": []}}))

    state.init_loop_state(plugin_root=tmp_path, repo="owner/repo")

    assert yaml.safe_load(state_path.read_text())["repo"] == "custom/repo"
    assert yaml.safe_load(contract_path.read_text())["phase0"]["goal"] == "custom goal"

    state.init_loop_state(plugin_root=tmp_path, repo="owner/repo", force=True)

    assert yaml.safe_load(state_path.read_text())["repo"] == "owner/repo"
    assert yaml.safe_load(contract_path.read_text())["phase0"]["goal"].startswith("Extract enough DS V4")


def test_update_state_merges_top_level_keys(tmp_path):
    state_dir = state.init_loop_state(plugin_root=tmp_path, repo="repo/example")
    updated = state.update_state(state_dir, {"active_phase": 1, "active_issue": 17})
    assert updated["active_phase"] == 1
    assert updated["active_issue"] == 17
    loaded = state.load_state(state_dir)
    assert loaded["active_phase"] == 1
    assert loaded["repo"] == "repo/example"
