import json

import pytest
from pydantic import BaseModel, ValidationError

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.handler_registry import HandlerRegistry


def valid_config_data(tmp_path, machine_id: str = "HOME_DEV") -> dict:
    return {
        "machine_id": machine_id,
        "poll_interval_seconds": 30,
        "folders": {
            "incoming": str(tmp_path / "incoming"),
            "test_media": str(tmp_path / "test_media"),
            "workspace": str(tmp_path / "workspace"),
            "exports": str(tmp_path / "exports"),
        },
        "resolve": {
            "executable_path": str(tmp_path / "Resolve.exe"),
            "launch_if_needed": False,
            "test_project": "ARPHE_TEST",
            "audit_project_prefix": "ARPHE_AUDIT_",
        },
        "github": {
            "owner": "arphesegreteria-arch",
            "repository": "arphe-remote-jobs",
            "branch": "main",
        },
        "local_checkout_path": str(tmp_path / "video-editing-manual"),
        "code_sync": {
            "source_repository": {
                "owner": "arphesegreteria-arch",
                "repository": "video-editing-manual",
                "branch": "main",
            }
        },
        "allowed_actions": ["PING", "SYNC_APPROVED_CODE"],
    }


def test_agent_config_loads_local_machine_and_folder_aliases(tmp_path) -> None:
    """Catches config loading that loses the machine-local folder policy."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(valid_config_data(tmp_path)), encoding="utf-8")

    config = AgentConfig.load(config_path)

    assert config.machine_id == "HOME_DEV"
    assert config.poll_interval_seconds == 30
    assert set(config.folders.aliases()) == {
        "incoming",
        "test_media",
        "workspace",
        "exports",
    }
    assert config.folders.path_for("workspace") == tmp_path / "workspace"


@pytest.mark.parametrize("machine_id", ["home_dev", "HOME DEV", "HOME-DEV"])
def test_agent_config_rejects_invalid_machine_id(tmp_path, machine_id: str) -> None:
    """Catches ambiguous machine identifiers in the remote-job target check."""
    with pytest.raises(ValidationError, match="machine_id"):
        AgentConfig.model_validate(valid_config_data(tmp_path, machine_id))


@pytest.mark.parametrize("poll_interval_seconds", [9, 301])
def test_agent_config_rejects_polling_outside_safe_bounds(
    tmp_path, poll_interval_seconds: int
) -> None:
    """Catches polling intervals outside the V1 10-to-300-second limit."""
    data = valid_config_data(tmp_path) | {"poll_interval_seconds": poll_interval_seconds}

    with pytest.raises(ValidationError, match="poll_interval_seconds"):
        AgentConfig.model_validate(data)


def test_agent_config_rejects_unknown_folder_alias_and_secret_fields(tmp_path) -> None:
    """Catches local config that widens folders or stores credentials on disk."""
    data = valid_config_data(tmp_path)
    data["folders"]["patient_records"] = str(tmp_path / "patient_records")
    data["github_token"] = "should-not-be-configured"

    with pytest.raises(ValidationError) as exc_info:
        AgentConfig.model_validate(data)

    assert "patient_records" in str(exc_info.value)
    assert "github_token" in str(exc_info.value)


def test_folder_config_only_resolves_declared_aliases(tmp_path) -> None:
    """Catches alias lookups that expose config-model attributes as filesystem roots."""
    config = AgentConfig.model_validate(valid_config_data(tmp_path))

    with pytest.raises(KeyError, match="unknown folder alias"):
        config.folders.path_for("model_dump")


@pytest.mark.parametrize("machine_id", ["POLI_01", "LAB_01"])
def test_only_home_dev_can_enable_code_synchronization(tmp_path, machine_id: str) -> None:
    """Catches any non-HOME_DEV machine enabling controlled code deployment."""
    with pytest.raises(ValidationError, match="SYNC_APPROVED_CODE"):
        AgentConfig.model_validate(valid_config_data(tmp_path, machine_id))


def test_home_dev_profile_can_enable_code_synchronization(tmp_path) -> None:
    """Catches the experimental HOME_DEV profile being needlessly restricted."""
    config = AgentConfig.model_validate(valid_config_data(tmp_path, "HOME_DEV"))

    assert "SYNC_APPROVED_CODE" in config.allowed_actions
    assert config.local_checkout_path == tmp_path / "video-editing-manual"
    assert config.github.repository == "arphe-remote-jobs"
    assert config.code_sync.source_repository.repository == "video-editing-manual"

    with pytest.raises(ValidationError, match="frozen"):
        config.local_checkout_path = tmp_path / "another-checkout"


@pytest.mark.parametrize(
    "checkout_path",
    [None, "relative/checkout", "C:/credentials/checkout"],
)
def test_code_synchronization_requires_an_absolute_secret_free_local_checkout_path(tmp_path, checkout_path) -> None:
    """Catches sync falling back to CWD or accepting a relative/secret-bearing checkout path."""
    data = valid_config_data(tmp_path)
    if checkout_path is None:
        data.pop("local_checkout_path")
    else:
        data["local_checkout_path"] = checkout_path

    with pytest.raises(ValidationError, match="checkout"):
        AgentConfig.model_validate(data)


@pytest.mark.parametrize("sync_config", [None, {}, {"source_repository": {}}])
def test_code_synchronization_fails_closed_without_a_separate_source_repository(tmp_path, sync_config) -> None:
    """Catches sync silently reusing the private runtime/job repository as source code."""
    data = valid_config_data(tmp_path)
    if sync_config is None:
        data.pop("code_sync")
    else:
        data["code_sync"] = sync_config

    with pytest.raises(ValidationError, match="code_sync"):
        AgentConfig.model_validate(data)


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("test_project", "CLIENT_PRODUCTION"),
        ("audit_project_prefix", "CLIENT_AUDIT_"),
    ],
)
def test_agent_config_rejects_unsafe_resolve_project_configuration(
    tmp_path, field: str, unsafe_value: str
) -> None:
    """Catches local Resolve configuration targeting a non-disposable project convention."""
    data = valid_config_data(tmp_path)
    data["resolve"][field] = unsafe_value

    with pytest.raises(ValidationError, match=unsafe_value):
        AgentConfig.model_validate(data)


class PingParameters(BaseModel):
    pass


def test_handler_registry_enforces_local_profile_when_resolving_action(tmp_path) -> None:
    """Catches invocation of a registered handler disabled by the local profile."""
    config_data = valid_config_data(tmp_path)
    config_data["allowed_actions"] = ["PING"]
    config = AgentConfig.model_validate(config_data)
    registry = HandlerRegistry(config.allowed_actions)

    registry.register("PING", PingParameters, lambda parameters: {"ok": True})
    registry.register("SYNC_APPROVED_CODE", PingParameters, lambda parameters: {"ok": True})

    assert registry.get("PING").idempotent is False
    with pytest.raises(PermissionError, match="not enabled"):
        registry.get("SYNC_APPROVED_CODE")
