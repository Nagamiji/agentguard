import json
from pathlib import Path

from agentguard_cli.commands import do_init
from agentguard_cli.main import main


def test_cli_do_init(tmp_path: Path) -> None:
    exit_code = do_init(str(tmp_path))
    assert exit_code == 0

    # Primary format: agentguard.yaml must exist and be valid YAML
    yaml_file = tmp_path / "agentguard.yaml"
    assert yaml_file.exists(), "agentguard.yaml should be the primary output of init"
    yaml_text = yaml_file.read_text()
    assert "system_prompt" in yaml_text
    assert "tools" in yaml_text
    assert "agentguard scan --local" in yaml_text

    # Legacy format: manifest.json still written for backwards compatibility
    manifest_file = tmp_path / "manifest.json"
    assert manifest_file.exists(), "manifest.json should still be written for existing pipelines"
    manifest_data = json.loads(manifest_file.read_text())
    assert "prompts" in manifest_data
    assert "tools" in manifest_data
    assert "model" in manifest_data

    # policy.json is no longer generated (policies now live inside agentguard.yaml)
    assert not (tmp_path / "policy.json").exists(), (
        "policy.json should not be generated — policies belong in agentguard.yaml"
    )

    # GitHub Actions workflow
    workflow_file = tmp_path / ".github" / "workflows" / "agentguard.yml"
    assert workflow_file.exists()
    workflow_text = workflow_file.read_text()
    assert "AgentGuard" in workflow_text
    assert "agentguard scan --local" in workflow_text


def test_cli_main_init_subcommand(tmp_path: Path) -> None:
    argv = ["init", "--dir", str(tmp_path)]
    exit_code = main(argv)
    assert exit_code == 0

    assert (tmp_path / "agentguard.yaml").exists()
    assert (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "policy.json").exists()
    assert (tmp_path / ".github" / "workflows" / "agentguard.yml").exists()
