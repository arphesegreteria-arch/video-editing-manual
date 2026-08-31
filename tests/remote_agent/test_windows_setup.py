"""Static safety checks for the explicit Windows-only installer scripts."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


AGENT_ROOT = Path(__file__).parents[2] / "scripts" / "remote_agent"
WINDOWS_ROOT = AGENT_ROOT / "windows"


def _read(relative_path: str) -> str:
    return (AGENT_ROOT / relative_path).read_text(encoding="utf-8")


def _run_setup_config_flow(
    tmp_path: Path, *, fail_prompt: bool = False, fail_validation: bool = False
) -> dict[str, object]:
    """Run the installer config transaction with controlled prompt/validation boundaries."""
    config_path = tmp_path / "config.json"
    prompt_behavior = "throw 'prompt failed'" if fail_prompt else "return $default"
    validator_behavior = "throw 'validation failed'" if fail_validation else "if (-not (Test-Path -LiteralPath $candidate)) { throw 'candidate missing' }"
    command = f"""
$ErrorActionPreference = 'Stop'
. '{(WINDOWS_ROOT / 'setup_windows.ps1').as_posix()}'
$configPath = '{config_path.as_posix()}'
$examplePath = '{(AGENT_ROOT / 'config.example.json').as_posix()}'
$failed = $false
$prompts = [System.Collections.Generic.List[string]]::new()
try {{
    Initialize-NewConfig -AgentDirectory '{tmp_path.as_posix()}' -ConfigPath $configPath -ExampleConfigPath $examplePath `
        -PromptReader {{ param($prompt, $default) $prompts.Add($prompt); {prompt_behavior} }} `
        -ConfigValidator {{ param($candidate) {validator_behavior} }}
}} catch {{
    $failed = $true
}}
[pscustomobject]@{{
    failed = $failed
    config_exists = Test-Path -LiteralPath $configPath
    temporary_count = @(Get-ChildItem -LiteralPath '{tmp_path.as_posix()}' -Filter '.config.json.*.tmp' -File -ErrorAction SilentlyContinue).Count
    prompts = @($prompts)
}} | ConvertTo-Json -Compress
"""
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


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
    assert "[IO.File]::Move" in script


def test_setup_fails_closed_when_external_install_or_token_commands_fail():
    script = (WINDOWS_ROOT / "setup_windows.ps1").read_text(encoding="utf-8")

    assert "function Assert-LastExitCode" in script
    assert "Assert-LastExitCode 'creating the dedicated virtual environment'" in script
    assert "Assert-LastExitCode 'upgrading pip in the dedicated virtual environment'" in script
    assert "Assert-LastExitCode 'installing the ARPHE Remote Agent runtime dependencies'" in script
    assert "Assert-LastExitCode 'validating the local config.json'" in script
    assert "Assert-LastExitCode 'storing the GitHub token in Windows Credential Manager'" in script


def test_first_run_config_is_not_created_when_a_prompt_fails(tmp_path):
    """Catches an incomplete first run being mistaken for an existing configuration."""
    result = _run_setup_config_flow(tmp_path, fail_prompt=True)

    assert result == {"failed": True, "config_exists": False, "temporary_count": 0, "prompts": ["Machine ID (uppercase letters, digits, underscores)"]}


def test_first_run_config_is_not_created_when_strict_validation_fails(tmp_path):
    """Catches a candidate surviving after strict config validation rejects it."""
    result = _run_setup_config_flow(tmp_path, fail_validation=True)

    assert result["failed"] is True
    assert result["config_exists"] is False
    assert result["temporary_count"] == 0


def test_first_run_config_commits_only_after_validation_and_skips_source_prompts_without_sync(tmp_path):
    """Catches a partial config commit or unnecessary source-repository questions for queue-only setup."""
    result = _run_setup_config_flow(tmp_path)

    assert result["failed"] is False
    assert result["config_exists"] is True
    assert result["temporary_count"] == 0
    assert any("runtime/job" in prompt.lower() for prompt in result["prompts"])
    assert not any("source repository" in prompt.lower() for prompt in result["prompts"])


def test_first_run_config_refuses_to_overwrite_existing_operator_configuration(tmp_path):
    """Catches a repeat run replacing a completed operator configuration with example defaults."""
    config_path = tmp_path / "config.json"
    config_path.write_text('{"operator_value":"preserve"}', encoding="utf-8")
    command = f"""
$ErrorActionPreference = 'Stop'
. '{(WINDOWS_ROOT / 'setup_windows.ps1').as_posix()}'
$configPath = '{config_path.as_posix()}'
$failed = $false
try {{
    Initialize-NewConfig -AgentDirectory '{tmp_path.as_posix()}' -ConfigPath $configPath -ExampleConfigPath '{(AGENT_ROOT / 'config.example.json').as_posix()}' `
        -PromptReader {{ param($prompt, $default) return $default }} `
        -ConfigValidator {{ param($candidate) throw 'validator must not run' }}
}} catch {{
    $failed = $true
}}
[pscustomobject]@{{ failed = $failed; content = Get-Content -LiteralPath $configPath -Raw }} | ConvertTo-Json -Compress
"""
    result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, check=False)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"failed": True, "content": '{"operator_value":"preserve"}'}


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


def test_readme_documents_manual_release_gate_and_expanded_secret_scan():
    readme = _read("README.md")

    assert "HOME_DEV manual release checklist" in readme
    assert "PING" in readme
    assert "LIST_MEDIA" in readme
    assert "RUN_CAPABILITY_AUDIT" in readme
    assert "RUN_RENDER_PROBE" in readme
    assert "REMOTE_AGENT_V1_HOME_DEV_TESTED" in readme
    assert "POLI_01" in readme
    assert "api[_-]?key" in readme


def test_current_state_records_tested_versions_and_pending_live_gate():
    current_state = (Path(__file__).parents[2] / "CURRENT_STATE.md").read_text(encoding="utf-8")
    lower = current_state.lower()

    assert "python " in lower
    assert "pytest " in lower
    assert "pydantic " in lower
    assert "requests " in lower
    assert "keyring " in lower
    assert "psutil " in lower
    assert "remote_agent_v1_home_dev_tested" in lower
    assert "not yet" in lower or "non ancora" in lower
    assert "poli_01" in lower
    assert "not production-ready" in lower or "non production-ready" in lower
