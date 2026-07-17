import json
from pathlib import Path

from agentguard_cli.commands import do_init
from agentguard_cli.main import main


def test_cli_do_init(tmp_path: Path) -> None:
    # Trigger do_init directly
    exit_code = do_init(str(tmp_path))
    assert exit_code == 0

    # Verify manifest.json
    manifest_file = tmp_path / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text())
    assert "prompts" in manifest_data
    assert "tools" in manifest_data
    assert "model" in manifest_data

    # Verify policy.json
    policy_file = tmp_path / "policy.json"
    assert policy_file.exists()
    policy_data = json.loads(policy_file.read_text())
    assert policy_data["scope_type"] == "organization"
    assert "max_tool_arg" in policy_data["rules"]

    # Verify Github action workflow
    workflow_file = tmp_path / ".github" / "workflows" / "agentguard.yml"
    assert workflow_file.exists()
    workflow_text = workflow_file.read_text()
    assert "name: AgentGuard Scan" in workflow_text
    assert "agentguard scan" in workflow_text


def test_cli_main_init_subcommand(tmp_path: Path) -> None:
    # Trigger main() parser dispatch logic
    argv = ["init", "--dir", str(tmp_path)]
    exit_code = main(argv)
    assert exit_code == 0

    # Ensure templates are correctly written
    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "policy.json").exists()
    assert (tmp_path / ".github" / "workflows" / "agentguard.yml").exists()
