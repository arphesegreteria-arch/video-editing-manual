"""Strict, secret-free local configuration for the ARPHE Remote Agent."""

from __future__ import annotations

import json
from pathlib import Path
from pydantic import Field, model_validator

from scripts.remote_agent.models import StrictModel


V1_ACTIONS = frozenset(
    {
        "PING",
        "GET_STATUS",
        "RUN_CAPABILITY_AUDIT",
        "LIST_MEDIA",
        "FIND_MEDIA",
        "HASH_MEDIA",
        "COPY_TO_WORKSPACE",
        "IMPORT_MEDIA",
        "RUN_TRACKING_PROBE",
        "RUN_RENDER_PROBE",
        "SYNC_APPROVED_CODE",
    }
)


class FolderConfig(StrictModel):
    incoming: Path
    test_media: Path
    workspace: Path
    exports: Path

    def aliases(self) -> tuple[str, ...]:
        return ("incoming", "test_media", "workspace", "exports")

    def path_for(self, alias: str) -> Path:
        if alias not in self.aliases():
            raise KeyError(f"unknown folder alias: {alias}")
        return getattr(self, alias)

    @model_validator(mode="after")
    def folders_must_be_absolute(self) -> "FolderConfig":
        for alias in self.aliases():
            if not self.path_for(alias).is_absolute():
                raise ValueError(f"folder alias {alias} must use an absolute path")
        return self


class ResolveConfig(StrictModel):
    executable_path: Path
    launch_if_needed: bool = True
    test_project: str = Field(default="ARPHE_TEST", min_length=1, max_length=128)
    audit_project_prefix: str = Field(default="ARPHE_AUDIT", min_length=1, max_length=128)

    @model_validator(mode="after")
    def executable_path_must_be_absolute(self) -> "ResolveConfig":
        if not self.executable_path.is_absolute():
            raise ValueError("Resolve executable_path must be absolute")
        return self


class GitHubConfig(StrictModel):
    owner: str = Field(min_length=1, max_length=128)
    repository: str = Field(min_length=1, max_length=128)
    branch: str = Field(default="main", min_length=1, max_length=256)
    api_base_url: str = Field(default="https://api.github.com", pattern=r"^https://")


class AgentConfig(StrictModel):
    machine_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    poll_interval_seconds: int = Field(default=30, ge=10, le=300)
    folders: FolderConfig
    resolve: ResolveConfig
    github: GitHubConfig
    allowed_actions: frozenset[str] = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_local_action_profile(self) -> "AgentConfig":
        unsupported = self.allowed_actions - V1_ACTIONS
        if unsupported:
            raise ValueError(
                "allowed_actions contains unsupported V1 action(s): "
                + ", ".join(sorted(unsupported))
            )
        if self.machine_id == "POLI_01" and "SYNC_APPROVED_CODE" in self.allowed_actions:
            raise ValueError("SYNC_APPROVED_CODE is not enabled for POLI_01")
        return self

    @classmethod
    def load(cls, path: str | Path) -> "AgentConfig":
        config_path = Path(path)
        try:
            raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in configuration file: {config_path}") from exc
        return cls.model_validate(raw_config)
