"""Windows Credential Manager access for ARPHE Remote Agent tokens."""

from __future__ import annotations

from typing import Protocol

import keyring

from scripts.remote_agent.config import AgentConfig


SERVICE_NAME = "ARPHE Remote Agent"


class KeyringBackend(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...


class CredentialStore:
    """Stores each machine's GitHub token outside the local config file."""

    def __init__(
        self, config: AgentConfig, keyring_backend: KeyringBackend | None = None
    ) -> None:
        self._account = f"{config.machine_id}:github"
        self._keyring = keyring if keyring_backend is None else keyring_backend

    def get_token(self) -> str | None:
        return self._keyring.get_password(SERVICE_NAME, self._account)

    def set_token(self, token: str) -> None:
        self._keyring.set_password(SERVICE_NAME, self._account, token)
