"""Controlled, configuration-bound code synchronization with no job command text."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import Field, field_validator

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.models import StrictModel


_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


class SyncParameters(StrictModel):
    commit_sha: str = Field(min_length=40, max_length=40)

    @field_validator("commit_sha")
    @classmethod
    def full_commit_sha_required(cls, value: str) -> str:
        if not _FULL_GIT_SHA.fullmatch(value):
            raise ValueError("commit_sha must be an exact 40-character Git SHA")
        return value.lower()


class GitSyncAdapter(Protocol):
    """Small injected boundary; the handler never starts a subprocess itself."""

    def remote_url(self, remote_name: str) -> str: ...
    def current_branch(self) -> str: ...
    def is_clean(self) -> bool: ...
    def current_revision(self) -> str: ...
    def remote_revision(self, remote_name: str, branch: str) -> str: ...
    def is_ancestor(self, ancestor: str, descendant: str) -> bool: ...
    def fast_forward(self, remote_name: str, branch: str, commit_sha: str) -> None: ...


class ApprovedCodeSync:
    """Verify all local invariants before a fake/injected Git update boundary is used."""

    def __init__(self, config: AgentConfig, git: GitSyncAdapter, *, remote_name: str = "origin") -> None:
        self._config = config
        self._git = git
        self._remote_name = remote_name
        self._expected_remote = (
            f"https://github.com/{config.github.owner}/{config.github.repository}.git"
        )

    def sync(self, commit_sha: str) -> dict[str, object]:
        if self._config.machine_id != "HOME_DEV" or "SYNC_APPROVED_CODE" not in self._config.allowed_actions:
            raise PermissionError("code synchronization is enabled only for the HOME_DEV local profile")
        if not _FULL_GIT_SHA.fullmatch(commit_sha):
            raise PermissionError("code synchronization requires an exact commit SHA")
        if self._git.remote_url(self._remote_name) != self._expected_remote:
            raise PermissionError("configured repository remote identity does not match")
        if self._git.current_branch() != self._config.github.branch:
            raise PermissionError("configured repository branch does not match")
        if not self._git.is_clean():
            raise PermissionError("local repository worktree must be clean")
        current_sha = self._git.current_revision()
        remote_sha = self._git.remote_revision(self._remote_name, self._config.github.branch)
        if remote_sha.casefold() != commit_sha.casefold():
            raise PermissionError("requested SHA must exactly match the configured remote branch")
        if not self._git.is_ancestor(current_sha, commit_sha):
            raise PermissionError("code synchronization must be a fast-forward update")
        # All arguments originate in the local config plus the validated full SHA.
        self._git.fast_forward(self._remote_name, self._config.github.branch, commit_sha)
        return {"updated_to": commit_sha, "restart_required": True}


def sync_approved_code(parameters: SyncParameters, service: ApprovedCodeSync | None) -> dict[str, object]:
    if service is None:
        raise RuntimeError("controlled code sync adapter is not installed")
    return service.sync(parameters.commit_sha)
