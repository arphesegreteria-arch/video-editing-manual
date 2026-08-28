from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.credentials import CredentialStore


class InMemoryKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.values[(service_name, username)] = password


def agent_config(tmp_path) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "machine_id": "HOME_DEV",
            "folders": {
                "incoming": str(tmp_path / "incoming"),
                "test_media": str(tmp_path / "test_media"),
                "workspace": str(tmp_path / "workspace"),
                "exports": str(tmp_path / "exports"),
            },
            "resolve": {"executable_path": str(tmp_path / "Resolve.exe")},
            "github": {"owner": "owner", "repository": "repository"},
            "allowed_actions": ["PING"],
        }
    )


def test_credential_store_uses_injected_keyring_without_mutating_config(tmp_path) -> None:
    """Catches credentials being persisted in, or retrieved from, agent config."""
    config = agent_config(tmp_path)
    keyring = InMemoryKeyring()
    store = CredentialStore(config, keyring_backend=keyring)

    store.set_token("unit-test-token-value")

    assert store.get_token() == "unit-test-token-value"
    assert keyring.values == {
        ("ARPHE Remote Agent", "HOME_DEV:github"): "unit-test-token-value"
    }
    assert "unit-test-token-value" not in str(config.model_dump())
    assert "github_token" not in config.model_dump()
