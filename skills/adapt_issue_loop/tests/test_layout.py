from pathlib import Path
import subprocess


SKILL_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = SKILL_ROOT.parents[1]


def test_issue_loop_layout_exists():
    assert (PLUGIN_ROOT / "bin" / "loongforge-issue-loop").exists()
    assert (SKILL_ROOT / "SKILL.md").exists()
    for name in (
        "run.py",
        "state.py",
        "issue_spec.py",
        "comparator.py",
        "github.py",
        "verification.py",
    ):
        assert (SKILL_ROOT / "scripts" / name).exists(), name


def test_issue_loop_skill_documents_entrypoint():
    text = (SKILL_ROOT / "SKILL.md").read_text()
    assert "name: adapt_issue_loop" in text
    assert "/loongforge:adapt_issue_loop" in text
    assert "loongforge-issue-loop" in text
    assert "Gate 1" in text
    assert "Phase 0-2" in text
    assert "GitHub Issue" in text


def test_issue_loop_cli_help_runs():
    result = subprocess.run(
        [str(PLUGIN_ROOT / "bin" / "loongforge-issue-loop"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "LoongForge issue-driven adapt loop" in result.stdout


def test_issue_loop_cli_rejects_unsupported_target_without_parse_error(tmp_path):
    result = subprocess.run(
        [
            str(PLUGIN_ROOT / "bin" / "loongforge-issue-loop"),
            "init",
            "--target",
            "phase-1",
            "--repo",
            "owner/repo",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "unsupported target" in result.stderr
    assert "unrecognized arguments" not in result.stderr


def test_readme_mentions_issue_loop():
    text = (PLUGIN_ROOT / "README.md").read_text()
    assert "/loongforge:adapt_issue_loop" in text
    assert "loongforge-issue-loop" in text
