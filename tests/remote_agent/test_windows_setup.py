"""Static safety checks for the explicit Windows-only installer scripts."""

from __future__ import annotations

import json
from pathlib import Path


AGENT_ROOT = Path(__file__).parents[2] / "scripts" / "remote_agent"
WINDOWS_ROOT = AGENT_ROOT / "windows"


def _read(relative_path: str) -> str:
    return (AGENT_ROOT / relative_path).read_text(encoding="utf-8")


def test_runtime_requirements_are_pinned_and_dev_dependencies_are_separate():
    requirements = _read("requirements.txt").splitlines()

    assert requirements == [
        "pydantic==2.13.4",
        "requests==2.34.2",
        "keyring==25.7.0",
        "psutil==7.2.2",
    ]
    assert "pytest" not in "\n".join(requirements).lower()
    assert "pytest==" in _read("requirements-dev.txt")


def test_example_config_is_secret_free_and_valid_for_the_existing_schema():
    from scripts.remote_agent.config import AgentConfig

    raw = json.loads(_read("config.example.json"))
    rendered = json.dumps(raw).lower()

    assert "token" not in rendered
    assert "secret" not in rendered
    config = AgentConfig.model_validate(raw)
    assert config.machine_id == "HOME_DEV"
    assert config.github.api_base_url == "https://api.github.com"


def test_setup_is_visible_only_and_uses_credential_manager_token_prompt():
    script = (WINDOWS_ROOT / "setup_windows.ps1").read_text(encoding="utf-8")
    lower = script.lower()

    forbidden = (
        "new-service",
        "sc.exe create",
        "register-scheduledtask",
        "schtasks",
        "new-scheduledtask",
        "currentversion\\run",
        "start-process -windowstyle hidden",
    )
    assert not any(term in lower for term in forbidden)
    assert "-m venv" in script
    assert "--set-github-token" in script
    assert "WScript.Shell" in script
    assert "Copy-Item -LiteralPath" in script


def test_setup_fails_closed_when_external_install_or_token_commands_fail():
    script = (WINDOWS_ROOT / "setup_windows.ps1").read_text(encoding="utf-8")

    assert "function Assert-LastExitCode" in script
    assert "Assert-LastExitCode 'creating the dedicated virtual environment'" in script
    assert "Assert-LastExitCode 'upgrading pip in the dedicated virtual environment'" in script
    assert "Assert-LastExitCode 'installing the ARPHE Remote Agent runtime dependencies'" in script
    assert "Assert-LastExitCode 'validating the local config.json'" in script
    assert "Assert-LastExitCode 'storing the GitHub token in Windows Credential Manager'" in script


def test_launcher_quotes_paths_and_runs_direct_entry_point():
    script = (WINDOWS_ROOT / "start_agent.bat").read_text(encoding="utf-8")

    assert 'set "VENV_PYTHON=' in script
    assert '"%VENV_PYTHON%" "%AGENT_DIRECTORY%\\start_agent.py" --config "%CONFIG_PATH%"' in script
    assert "call \"%VENV_DIRECTORY%\\Scripts\\activate.bat\"" in script
    assert "pause" in script.lower()


def test_entry_point_can_prompt_for_a_token_without_placing_it_in_arguments(tmp_path):
    import subprocess
    import sys

    entry_point = AGENT_ROOT / "start_agent.py"
    result = subprocess.run(
        [sys.executable, str(entry_point), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--set-github-token" in result.stdout


def test_uninstall_only_targets_agent_state_and_preserves_operator_data_by_default():
    script = (WINDOWS_ROOT / "uninstall_agent.ps1").read_text(encoding="utf-8")
    lower = script.lower()

    assert "remove-exactchild" in lower
    assert "expectedleaf" in lower
    assert "remove-item -literalpath $path -recurse -force" in lower
    assert "d:\\arphe\\incoming" not in lower
    assert "d:\\arphe\\exports" not in lower
    assert "logs" in lower and "preserve" in lower
    assert "remove-item -path" not in lower


def test_readme_states_manual_launch_and_no_background_agent():
    readme = _read("README.md")
    lower = readme.lower()

    assert "home_dev" in lower
    assert "windows credential manager" in lower
    assert "no service" in lower
    assert "no scheduled task" in lower
    assert "no startup" in lower
    assert "resolve studio" in lower
