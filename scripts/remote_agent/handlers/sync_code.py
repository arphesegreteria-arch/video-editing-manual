"""Controlled, configuration-bound code synchronization with no job command text."""

from __future__ import annotations

import re
from pathlib import Path
import subprocess
from typing import Protocol

from pydantic import Field, field_validator

from scripts.remote_agent.cancellation import CancellationToken, require_not_cancelled
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
    def remote_revision(self, remote_name: str, branch: str, token: CancellationToken) -> str: ...
    def is_ancestor(self, ancestor: str, descendant: str) -> bool: ...
    def fast_forward(self, remote_name: str, branch: str, commit_sha: str, token: CancellationToken) -> None: ...


class SubprocessGitSyncAdapter:
    """Local Git boundary with fixed argv construction and no shell."""
    def __init__(self, repository_path: Path, *, run=subprocess.run) -> None:
        self._repository_path, self._run = repository_path, run

    @property
    def repository_path(self) -> Path:
        """The fixed local checkout selected by strict agent configuration."""
        return self._repository_path
    def _git(self, *args: str) -> str:
        result = self._run(["git", "-C", str(self._repository_path), *args], shell=False, check=False, capture_output=True, text=True)
        if result.returncode != 0: raise RuntimeError("controlled Git operation failed")
        return result.stdout.strip()
    def remote_url(self, remote_name: str) -> str: return self._git("remote", "get-url", remote_name)
    def current_branch(self) -> str: return self._git("branch", "--show-current")
    def is_clean(self) -> bool: return not self._git("status", "--porcelain")
    def current_revision(self) -> str: return self._git("rev-parse", "HEAD")
    def remote_revision(self, remote_name: str, branch: str, token: CancellationToken) -> str:
        require_not_cancelled(token)
        self._git("fetch", "--no-tags", remote_name, branch)
        require_not_cancelled(token)
        return self._git("rev-parse", f"{remote_name}/{branch}")
    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        result = self._run(["git", "-C", str(self._repository_path), "merge-base", "--is-ancestor", ancestor, descendant], shell=False, check=False, capture_output=True, text=True)
        return result.returncode == 0
    def fast_forward(self, remote_name: str, branch: str, commit_sha: str, token: CancellationToken) -> None:
        require_not_cancelled(token)
        self._git("merge", "--ff-only", commit_sha)
        require_not_cancelled(token)
        if self.current_revision().casefold() != commit_sha.casefold(): raise RuntimeError("controlled Git update did not reach requested SHA")


class ApprovedCodeSync:
    """Verify all local invariants before a fake/injected Git update boundary is used."""

    def __init__(self, config: AgentConfig, git: GitSyncAdapter, *, remote_name: str = "origin") -> None:
        self._config = config
        self._git = git
        self._remote_name = remote_name
        self._expected_remote = (
            f"https://github.com/{config.github.owner}/{config.github.repository}.git"
        )

    @property
    def git_adapter(self) -> GitSyncAdapter:
        """Expose the fixed boundary for local wiring verification."""
        return self._git

    def sync(self, commit_sha: str, token: CancellationToken) -> dict[str, object]:
        require_not_cancelled(token)
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
        remote_sha = self._git.remote_revision(self._remote_name, self._config.github.branch, token)
        if remote_sha.casefold() != commit_sha.casefold():
            raise PermissionError("requested SHA must exactly match the configured remote branch")
        if not self._git.is_ancestor(current_sha, commit_sha):
            raise PermissionError("code synchronization must be a fast-forward update")
        # All arguments originate in the local config plus the validated full SHA.
        require_not_cancelled(token)
        self._git.fast_forward(self._remote_name, self._config.github.branch, commit_sha, token)
        require_not_cancelled(token)
        return {"updated_to": commit_sha, "restart_required": True}


def sync_approved_code(
    parameters: SyncParameters, service: ApprovedCodeSync | None, token: CancellationToken
) -> dict[str, object]:
    if service is None:
        raise RuntimeError("controlled code sync adapter is not installed")
    return service.sync(parameters.commit_sha, token)


def default_code_sync(config: AgentConfig) -> ApprovedCodeSync:
    """Create production Git sync only from the immutable configured checkout."""
    if config.local_checkout_path is None:
        raise ValueError("SYNC_APPROVED_CODE requires local_checkout_path")
    return ApprovedCodeSync(config, SubprocessGitSyncAdapter(config.local_checkout_path))
