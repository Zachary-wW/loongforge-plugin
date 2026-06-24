import json
import subprocess
import sys
from pathlib import Path

import yaml


PLUGIN_SKILL_ROOT = Path(__file__).parent.parent
PLUGIN_ROOT = PLUGIN_SKILL_ROOT.parents[1]
REPO_ROOT = PLUGIN_ROOT.parent


def test_plugin_manifest_exists_and_is_namespaced():
    manifest_path = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["name"] == "loongforge"
    assert manifest["version"]
    assert "LoongForge" in manifest["description"]


def test_plugin_skill_exists_and_documents_plugin_entrypoint():
    skill_path = PLUGIN_SKILL_ROOT / "SKILL.md"
    text = skill_path.read_text()
    assert "name: adapt" in text
    assert "/loongforge:adapt" in text
    assert "loongforge-adapt <hf_path>" in text
    assert "python loongforge_adapt/scripts/run.py" not in text
    assert "/loongforge-adapt" not in text
    assert "adapt-phase0" in text
    assert "general-purpose" in text


def test_plugin_contains_copied_adapt_assets():
    assert (PLUGIN_SKILL_ROOT / "scripts" / "run.py").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase0" / "agent.md").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase0" / "reference_contract_schema.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase0" / "slice_report_schema.json").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "phase1_output_schema.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "strategy_rules.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "megatron_preread_checklist.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "phase2_output_schema.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "conversion_gates.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "conversion_strategy_rules.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase3" / "phase3_output_schema.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase4" / "phase4_output_schema.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase4" / "performance_tuning_gate.md").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase5" / "feature_matrix.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase5" / "phase5_output_schema.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "source_templates" / "llm.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "source_templates" / "vlm.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "source_templates" / "diffusion.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "phase6_output_schema.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "extraction_rules.yaml").exists()
    assert (PLUGIN_SKILL_ROOT / "knowledge_base" / "schema" / "EXIT_CONTRACT.md").exists()
    assert (PLUGIN_SKILL_ROOT / "knowledge_base" / "schema" / "STEP_GATE.md").exists()
    assert (PLUGIN_SKILL_ROOT / "tests" / "test_runner.py").exists()


def test_phase5_feature_matrix_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase5" / "agent.md"
    matrix = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase5" / "feature_matrix.yaml"
    manual_text = manual.read_text()
    matrix_data = yaml.safe_load(matrix.read_text())

    assert "references/phases/phase5/feature_matrix.yaml" in manual_text
    assert "Fixed Phase 5 switch matrix:" not in manual_text
    assert matrix_data["version"] == 1
    switches = {row["switch"] for row in matrix_data["rows"]}
    assert {"TP", "PP", "FP8 blockwise training", "Optimizer CPU offload"}.issubset(switches)


def test_phase0_schemas_are_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase0" / "agent.md"
    reference_schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase0" / "reference_contract_schema.yaml"
    slice_schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase0" / "slice_report_schema.json"
    manual_text = manual.read_text()
    reference_data = yaml.safe_load(reference_schema.read_text())
    slice_data = json.loads(slice_schema.read_text())

    # After Phase 0 redesign (Plan 06-01), agent.md references bridge_mapping_schema
    # instead of the literal reference_contract_schema.yaml path.
    # Either the schema path or bridge_mapping_schema reference must appear.
    assert (
        "references/phases/phase0/reference_contract_schema.yaml" in manual_text
        or "bridge_mapping_schema" in manual_text
    ), "agent.md must reference either reference_contract_schema.yaml or bridge_mapping_schema"
    assert "references/phases/phase0/slice_report_schema.json" in manual_text
    assert "`reference_contract.yml` must use model-agnostic fields only:" not in manual_text
    assert "`slice_report.json` schema:" not in manual_text
    assert "implementation_contract" in reference_data
    assert "conversion_requirements" in reference_data
    assert "validation" in slice_data


def test_phase1_output_schema_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "agent.md"
    schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "phase1_output_schema.yaml"
    manual_text = manual.read_text()
    schema_data = yaml.safe_load(schema.read_text())

    assert "references/phases/phase1/phase1_output_schema.yaml" in manual_text
    assert "`phase1_output.yml` schema:" not in manual_text
    assert schema_data["phase"] == 1
    assert schema_data["step_gate"]["mandatory_steps_complete"] is True
    assert "generated_files" in schema_data["artifacts"]
    assert schema_data["validator"]["name"] == "phase1-verify"


def test_phase1_strategy_rules_are_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "agent.md"
    rules = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "strategy_rules.yaml"
    manual_text = manual.read_text()
    rules_data = yaml.safe_load(rules.read_text())

    assert "references/phases/phase1/strategy_rules.yaml" in manual_text
    assert "| `reuse_megatron` |" not in manual_text
    strategy_names = {strategy["final_strategy"] for strategy in rules_data["strategies"]}
    assert {"reuse_megatron", "wrap_megatron", "adapt_ref", "new_impl"}.issubset(strategy_names)
    assert "native_integration_gate" in rules_data
    assert "shared_megatron_change_policy" in rules_data


def test_phase1_megatron_preread_checklist_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "agent.md"
    checklist = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase1" / "megatron_preread_checklist.yaml"
    manual_text = manual.read_text()
    checklist_data = yaml.safe_load(checklist.read_text())

    assert "references/phases/phase1/megatron_preread_checklist.yaml" in manual_text
    assert "<megatron_path>/megatron/core/transformer/spec_utils.py" not in manual_text
    assert checklist_data["required_reference"]["path"] == "knowledge_base/schema/MEGATRON_COMPONENT_MAP.md"
    source_paths = {source["path"] for source in checklist_data["required_megatron_sources"]}
    assert "<megatron_path>/megatron/core/transformer/spec_utils.py" in source_paths
    assert len(checklist_data["completion_questions"]) >= 5


def test_phase2_output_schema_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "agent.md"
    schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "phase2_output_schema.yaml"
    manual_text = manual.read_text()
    schema_data = yaml.safe_load(schema.read_text())

    assert "references/phases/phase2/phase2_output_schema.yaml" in manual_text
    assert "`phase2_output.yml` schema:" not in manual_text
    assert schema_data["phase"] == 2
    assert schema_data["step_gate"]["mandatory_steps_complete"] is True
    assert "production_gate" in schema_data["conversion"]
    assert schema_data["validator"]["name"] == "phase2-conversion"


def test_phase2_conversion_gates_are_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "agent.md"
    gates = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "conversion_gates.yaml"
    manual_text = manual.read_text()
    gates_data = yaml.safe_load(gates.read_text())

    assert "references/phases/phase2/conversion_gates.yaml" in manual_text
    assert "#### Step 5a — HF Roundtrip Test" not in manual_text
    assert "#### Step 5d — Offline Roundtrip verification" not in manual_text
    assert gates_data["validator"] == "phase2-conversion"
    gate_ids = {gate["id"] for gate in gates_data["gates"]}
    assert {"step5a", "step5b", "step5c", "step5d"}.issubset(gate_ids)
    step5c = next(gate for gate in gates_data["gates"] if gate["id"] == "step5c")
    assert "production_gate_schema" in step5c


def test_phase2_conversion_strategy_rules_are_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "agent.md"
    rules = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase2" / "conversion_strategy_rules.yaml"
    manual_text = manual.read_text()
    rules_data = yaml.safe_load(rules.read_text())

    assert "references/phases/phase2/conversion_strategy_rules.yaml" in manual_text
    assert "| `append_mapping` |" not in manual_text
    strategy_names = {strategy["name"] for strategy in rules_data["conversion_strategies"]}
    assert {"append_mapping", "insert_load_preprocess", "insert_save_postprocess", "override_parallel_dim"}.issubset(strategy_names)
    assert "tier1" in rules_data["tiers"]
    assert "tier2" in rules_data["tiers"]
    assert rules_data["protected_file_constraint"]["if_existing_logic_must_change"]["failure_gate"] == "protected_file_change_required"


def test_phase3_output_schema_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase3" / "agent.md"
    schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase3" / "phase3_output_schema.yaml"
    manual_text = manual.read_text()
    schema_data = yaml.safe_load(schema.read_text())

    assert "references/phases/phase3/phase3_output_schema.yaml" in manual_text
    assert "**When reference_type=hf / megatron**:" not in manual_text
    assert "**When reference_type=standalone**:" not in manual_text
    assert "Do not write `reference_modes` as a wrapper" in manual_text
    assert "reference_modes" not in schema_data
    assert schema_data["phase"] == 3
    assert schema_data["step_gate"]["mandatory_steps_complete"] is True
    assert schema_data["validator"]["name"] == "loss-diff"
    assert "mode_rules" in schema_data
    assert "standalone" in schema_data["mode_rules"]


def test_phase4_performance_tuning_schema_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase4" / "agent.md"
    schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase4" / "phase4_output_schema.yaml"
    manual_text = manual.read_text()
    schema_data = yaml.safe_load(schema.read_text())

    assert "references/phases/phase4/phase4_output_schema.yaml" in manual_text
    assert schema_data["phase"] == 4
    assert schema_data["validator"]["name"] == "performance-tuning"


def test_phase5_output_schema_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase5" / "agent.md"
    schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase5" / "phase5_output_schema.yaml"
    manual_text = manual.read_text()
    schema_data = yaml.safe_load(schema.read_text())

    assert "references/phases/phase5/phase5_output_schema.yaml" in manual_text
    assert "Write `phase5_output.yml` to `run_dir/phases/phase5_output.yml`:" not in manual_text
    assert schema_data["phase"] == 5
    assert schema_data["step_gate"]["mandatory_steps_complete"] is True
    assert "single_switches" in schema_data
    assert "combinations" in schema_data
    assert schema_data["validator"]["name"] == "feature-compat"


def test_phase6_output_schema_is_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "agent.md"
    schema = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "phase6_output_schema.yaml"
    manual_text = manual.read_text()
    schema_data = yaml.safe_load(schema.read_text())

    assert "references/phases/phase6/phase6_output_schema.yaml" in manual_text
    assert schema_data["phase"] == 6
    assert schema_data["validator"]["name"] == "kb-consistency"


def test_phase5_extraction_rules_are_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "agent.md"
    rules = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "extraction_rules.yaml"
    manual_text = manual.read_text()
    rules_data = yaml.safe_load(rules.read_text())

    assert "references/phases/phase6/extraction_rules.yaml" in manual_text
    assert "### 1b. Infer structural_tags from model_spec.yaml" not in manual_text
    assert "### 1d. Build code_paths" not in manual_text
    assert "### 1e. Build omni_reference" not in manual_text
    assert "structural_tags" in rules_data
    assert "code_paths" in rules_data
    assert "omni_reference" in rules_data
    assert rules_data["source_templates"]["llm"] == "references/phases/phase6/source_templates/llm.yaml"


def test_phase5_source_templates_are_externalized():
    manual = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "agent.md"
    templates_dir = PLUGIN_SKILL_ROOT / "references" / "phases" / "phase6" / "source_templates"
    manual_text = manual.read_text()

    assert "references/phases/phase6/source_templates/llm.yaml" in manual_text
    assert "references/phases/phase6/source_templates/vlm.yaml" in manual_text
    assert "references/phases/phase6/source_templates/diffusion.yaml" in manual_text
    assert "#### LLM Template" not in manual_text
    for filename in ["llm.yaml", "vlm.yaml", "diffusion.yaml"]:
        data = yaml.safe_load((templates_dir / filename).read_text())
        assert "family" in data
        assert "hf_reference" in data
        assert "structural_tags" in data
        assert "code_paths" in data
        assert "omni_reference" in data


def test_phase_agents_exist_and_reference_canonical_manuals():
    expected = {
        "adapt-phase0.md": "references/phases/phase0/agent.md",
        "adapt-phase1.md": "references/phases/phase1/agent.md",
        "adapt-phase2.md": "references/phases/phase2/agent.md",
        "adapt-phase3.md": "references/phases/phase3/agent.md",
        "adapt-phase4.md": "references/phases/phase4/agent.md",
        "adapt-phase5.md": "references/phases/phase5/agent.md",
        "adapt-phase6.md": "references/phases/phase6/agent.md",
    }
    for filename, manual in expected.items():
        path = PLUGIN_ROOT / "agents" / filename
        text = path.read_text()
        assert manual in text
        assert "knowledge_base/schema/EXIT_CONTRACT.md" in text
        assert "knowledge_base/schema/STEP_GATE.md" in text
        assert "phase.status" in text
        assert "attempts.jsonl" in text


def test_plugin_bin_wrappers_and_hook_example_exist():
    assert (PLUGIN_ROOT / "bin" / "loongforge-adapt").exists()
    assert (PLUGIN_ROOT / "bin" / "loongforge-phase-gate").exists()
    assert (PLUGIN_ROOT / "hooks" / "README.md").exists()
    hook_example = PLUGIN_ROOT / "hooks" / "task_completed_phase_gate.example.json"
    text = hook_example.read_text()
    assert "TaskCompleted" in text
    assert "loongforge-phase-gate" in text
    assert not (PLUGIN_ROOT / "hooks" / "hooks.json").exists()


def _write_phase_output(run_dir: Path, phase: int, output: dict):
    phases_dir = run_dir / "phases"
    phases_dir.mkdir(parents=True, exist_ok=True)
    (phases_dir / f"phase{phase}").mkdir(parents=True, exist_ok=True)
    (phases_dir / f"phase{phase}_output.yml").write_text(
        yaml.dump(output, sort_keys=False, allow_unicode=True)
    )


def test_phase_gate_passes_for_valid_phase1_output(tmp_path):
    _write_phase_output(
        tmp_path,
        1,
        {
            "phase": 1,
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"step1": {"status": "passed", "evidence": "synthetic"}},
            "validator": {"name": "phase1-verify", "status": "passed"},
        },
    )
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-phase-gate"),
            "--run-dir",
            str(tmp_path),
            "--phase",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_phase_gate_blocks_missing_step_gate(tmp_path):
    _write_phase_output(
        tmp_path,
        1,
        {
            "phase": 1,
            "status": "passed",
            "validator": {"name": "phase1-verify", "status": "passed"},
        },
    )
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-phase-gate"),
            "--run-dir",
            str(tmp_path),
            "--phase",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "step_gate" in result.stderr


def test_phase_gate_blocks_missing_validator(tmp_path):
    _write_phase_output(
        tmp_path,
        1,
        {
            "phase": 1,
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"step1": {"status": "passed", "evidence": "synthetic"}},
            "validator": {"name": "phase1-verify", "status": "failed"},
        },
    )
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-phase-gate"),
            "--run-dir",
            str(tmp_path),
            "--phase",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "validator.status" in result.stderr


def test_phase_gate_blocks_phase2_without_production_gate(tmp_path):
    _write_phase_output(
        tmp_path,
        2,
        {
            "phase": 2,
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"step1": {"status": "passed", "evidence": "synthetic"}},
            "validator": {"name": "phase2-conversion", "status": "passed"},
        },
    )
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-phase-gate"),
            "--run-dir",
            str(tmp_path),
            "--phase",
            "2",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "conversion.production_gate" in result.stderr


def test_phase_gate_passes_phase2_with_production_gate(tmp_path):
    _write_phase_output(
        tmp_path,
        2,
        {
            "phase": 2,
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"step1": {"status": "passed", "evidence": "synthetic"}},
            "validator": {"name": "phase2-conversion", "status": "passed"},
            "conversion": {
                "production_gate": {
                    "loaded_by_target_framework": True,
                    "mcore_artifacts_exist": True,
                    "rebuilt_hf_derived_from_mcore": True,
                    "reversible_container_detected": False,
                    "forbidden_shortcuts": [],
                }
            },
        },
    )
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-phase-gate"),
            "--run-dir",
            str(tmp_path),
            "--phase",
            "2",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_phase_gate_passes_phase3_with_top_level_schema_shape(tmp_path):
    _write_phase_output(
        tmp_path,
        3,
        {
            "phase": 3,
            "status": "passed",
            "step_gate": {"mandatory_steps_complete": True},
            "steps": {"step1": {"status": "passed", "evidence": "synthetic"}},
            "model": {"reference_type": "hf", "reference_framework": "transformers"},
            "validator": {"name": "loss-diff", "status": "passed"},
        },
    )
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-phase-gate"),
            "--run-dir",
            str(tmp_path),
            "--phase",
            "3",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_phase_gate_blocks_phase3_reference_modes_wrapper_shape(tmp_path):
    _write_phase_output(
        tmp_path,
        3,
        {
            "reference_modes": {
                "hf_or_megatron": {
                    "phase": 3,
                    "status": "passed",
                    "step_gate": {"mandatory_steps_complete": True},
                    "steps": {"step1": {"status": "passed", "evidence": "synthetic"}},
                    "validator": {"name": "loss-diff", "status": "passed"},
                }
            }
        },
    )
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-phase-gate"),
            "--run-dir",
            str(tmp_path),
            "--phase",
            "3",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "phase status" in result.stderr


def test_plugin_runner_cli_smoke(tmp_path):
    run_dir = tmp_path / "plugin_cli"
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-adapt"),
            "/tmp/model",
            "--run-dir",
            str(run_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (run_dir / "run_inputs.yml").exists()
    assert (run_dir / "run_state.json").exists()
    assert "/loongforge:adapt" in result.stdout


def test_resume_from_phase_does_not_require_existing_legacy_state(tmp_path):
    run_dir = tmp_path / "no_legacy_state"
    result = subprocess.run(
        [
            sys.executable,
            str(PLUGIN_SKILL_ROOT / "scripts" / "run.py"),
            "/tmp/model",
            "--run-dir",
            str(run_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    (run_dir / "run_state.json").unlink()

    result = subprocess.run(
        [
            sys.executable,
            str(PLUGIN_SKILL_ROOT / "scripts" / "run.py"),
            "--resume",
            str(run_dir),
            "--from-phase",
            "2",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (run_dir / "run_state.json").exists()


def test_legacy_only_state_resume_backfills_run_inputs(tmp_path):
    run_dir = tmp_path / "legacy_only"
    run_dir.mkdir()
    (run_dir / "run_state.json").write_text(
        json.dumps(
            {
                "hf_path": "/tmp/model",
                "model_name": "legacy-model",
                "run_dir": str(run_dir),
                "current_state": "INIT",
                "hf_modeling_path": "/tmp/modeling.py",
                "omni_path": "/opt/loongforge",
                "megatron_path": "/opt/megatron",
                "gpu_execution_mode": "k8s",
                "enable_slice_ckpt": "true",
                "k8s_yaml_path": "/tmp/job.yaml",
                "k8s_launch_cmd": "kubectl apply -f /tmp/job.yaml",
                "wip_code_paths": "",
                "phases": {},
            }
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(PLUGIN_SKILL_ROOT / "scripts" / "run.py"),
            "--resume",
            str(run_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    inputs = yaml.safe_load((run_dir / "run_inputs.yml").read_text())
    assert inputs["source"]["hf_ckpt_path"] == "/tmp/model"
    assert inputs["options"]["model_name"] == "legacy-model"
    assert inputs["options"]["gpu_execution_mode"] == "k8s"


def test_plugin_contains_adapt_eval_assets():
    eval_skill = PLUGIN_ROOT / "skills" / "adapt_eval"
    assert (eval_skill / "SKILL.md").exists()
    assert (eval_skill / "scripts" / "run.py").exists()
    assert (eval_skill / "scripts" / "eval_helpers.py").exists()
    assert (eval_skill / "scripts" / "log_parser.py").exists()
    assert (eval_skill / "tests" / "test_eval_helpers.py").exists()
    assert (eval_skill / "tests" / "test_log_parser.py").exists()
    assert (eval_skill / "tests" / "test_run_cli.py").exists()
    assert (PLUGIN_ROOT / "bin" / "loongforge-adapt-eval").exists()
    assert (PLUGIN_ROOT / "eval" / "SCOREBOARD.md").exists()
    assert (PLUGIN_ROOT / "eval" / "SCOREBOARD.json").exists()
    assert (PLUGIN_ROOT / "eval" / ".gitignore").exists()


def test_adapt_eval_skill_documents_subcommands():
    skill = (PLUGIN_ROOT / "skills" / "adapt_eval" / "SKILL.md").read_text()
    for sub in ("init", "record-loss", "set-backup-info", "set-adapt-run",
                "set-omni-review", "compute-verdict", "restore"):
        assert sub in skill, f"SKILL.md should mention sub-command {sub}"
    assert "/loongforge:adapt_eval" in skill
    assert "loongforge-adapt-eval" in skill
