"""Read-only allowlisted agent and Resolve status handlers."""

from __future__ import annotations

import platform

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.models import StrictModel


class PingParameters(StrictModel):
    """PING accepts no remotely supplied settings."""


class GetStatusParameters(StrictModel):
    """GET_STATUS accepts no remotely supplied settings."""


def ping(config: AgentConfig, *, agent_version: str, source_commit: str) -> dict[str, object]:
    return {
        "agent_version": agent_version,
        "source_commit": source_commit,
        "machine_id": config.machine_id,
        "os": platform.system(),
        "python": platform.python_version(),
        "allowed_actions": sorted(config.allowed_actions),
    }


def get_status(config: AgentConfig, resolve_manager: object) -> dict[str, object]:
    status = getattr(resolve_manager, "get_status")()
    return {
        "machine_id": config.machine_id,
        "allowed_folder_aliases": sorted(config.folders.aliases()),
        "resolve": status,
    }
