from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.handler_registry import HandlerRegistry
from scripts.remote_agent.handlers import register_handlers
from scripts.remote_agent.handlers.sync_code import ApprovedCodeSync, SubprocessGitSyncAdapter, default_code_sync
from scripts.remote_agent.job_runner import CancellationToken


class FakeBroker:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def list_media(self, alias: str, relative_dir: str) -> list[str]:
        self.calls.append(("list", alias, relative_dir))
        return ["incoming/clip.mp4"]

    def find_media(self, alias: str, query: str) -> list[str]:
        self.calls.append(("find", alias, query))
        return ["test_media/clip.mp4"]

    def hash_media(self, alias: str, relative_path: str) -> dict[str, object]:
        self.calls.append(("hash", alias, relative_path))
        return {"path": "incoming/clip.mp4", "size_bytes": 3, "sha256": "a" * 64}

    def copy_to_workspace(
        self, source_alias: str, relative_path: str, destination_relative_path: str | None, token: CancellationToken
    ) -> str:
        self.calls.append(("copy", source_alias, relative_path, destination_relative_path, token))
        return "workspace/jobs/clip.mp4"


class FakeResolve:
    def __init__(self) -> None:
        self.test_project_checks = 0
        self.imports: list[tuple[str, str | None]] = []

    def get_status(self) -> dict[str, object]:
        return {"status": "connected", "connected": True, "project": "ARPHE_TEST", "timeline": "Test", "version": "20"}

    def require_test_project(self) -> str:
        self.test_project_checks += 1
        return "ARPHE_TEST"

    def import_media(self, alias_relative_path: str, target_bin: str | None, token: CancellationToken) -> dict[str, object]:
        self.imports.append((alias_relative_path, target_bin, token))
        return {"imported": [alias_relative_path], "target_bin": target_bin}


def config(tmp_path: Path, *, allowed_actions: list[str] | None = None) -> AgentConfig:
    folders = {name: str(tmp_path / name) for name in ("incoming", "test_media", "workspace", "exports")}
    return AgentConfig.model_validate(
        {
            "machine_id": "HOME_DEV",
            "folders": folders,
            "resolve": {"executable_path": str(tmp_path / "Resolve.exe")},
            "github": {"owner": "arphesegreteria-arch", "repository": "video-editing-manual", "branch": "main"},
            "local_checkout_path": str(tmp_path / "video-editing-manual"),
            "allowed_actions": allowed_actions or ["PING", "GET_STATUS", "LIST_MEDIA", "FIND_MEDIA", "HASH_MEDIA", "COPY_TO_WORKSPACE", "IMPORT_MEDIA"],
        }
    )


def registry_for(tmp_path: Path, *, allowed_actions: list[str] | None = None) -> tuple[HandlerRegistry, FakeBroker, FakeResolve]:
    agent_config = config(tmp_path, allowed_actions=allowed_actions)
    broker = FakeBroker()
    resolve = FakeResolve()
    registry = HandlerRegistry(agent_config.allowed_actions)
    register_handlers(registry, agent_config, broker, resolve, agent_version="1.2.3", source_commit="abc123")
    return registry, broker, resolve


def test_ping_and_status_expose_only_sanitized_local_metadata(tmp_path: Path) -> None:
    """Catches status handlers leaking unrelated local paths or secret configuration."""
    registry, _, _ = registry_for(tmp_path)

    ping = registry.get("PING").handler(registry.validate_parameters("PING", {}))
    status = registry.get("GET_STATUS").handler(registry.validate_parameters("GET_STATUS", {}))

    assert ping["agent_version"] == "1.2.3"
    assert ping["source_commit"] == "abc123"
    assert ping["machine_id"] == "HOME_DEV"
    assert set(ping) == {"agent_version", "source_commit", "machine_id", "os", "python", "allowed_actions"}
    assert "github" not in ping and "folders" not in ping
    assert status == {
        "machine_id": "HOME_DEV",
        "allowed_folder_aliases": ["exports", "incoming", "test_media", "workspace"],
        "resolve": {"status": "connected", "connected": True, "project": "ARPHE_TEST", "timeline": "Test", "version": "20"},
    }


def test_media_handlers_delegate_only_alias_relative_requests_to_broker_and_manager(tmp_path: Path) -> None:
    """Catches handlers bypassing the guarded broker or importing outside a disposable project."""
    registry, broker, resolve = registry_for(tmp_path)

    assert registry.get("LIST_MEDIA").handler(registry.validate_parameters("LIST_MEDIA", {"alias": "incoming", "relative_dir": "footage"})) == {"media": ["incoming/clip.mp4"]}
    assert registry.get("FIND_MEDIA").handler(registry.validate_parameters("FIND_MEDIA", {"alias": "test_media", "query": "clip"})) == {"media": ["test_media/clip.mp4"]}
    assert registry.get("HASH_MEDIA").handler(registry.validate_parameters("HASH_MEDIA", {"alias": "incoming", "relative_path": "clip.mp4"})) == {"path": "incoming/clip.mp4", "size_bytes": 3, "sha256": "a" * 64}
    token = CancellationToken()
    assert registry.get("COPY_TO_WORKSPACE").handler(registry.validate_parameters("COPY_TO_WORKSPACE", {"source_alias": "incoming", "relative_path": "clip.mp4", "destination_relative_path": "jobs/clip.mp4"}), token) == {"path": "workspace/jobs/clip.mp4"}
    assert registry.get("IMPORT_MEDIA").handler(registry.validate_parameters("IMPORT_MEDIA", {"source_alias": "incoming", "relative_path": "clip.mp4", "target_bin": "Remote Agent"}), token) == {"imported": ["incoming/clip.mp4"], "target_bin": "Remote Agent"}

    assert broker.calls == [
        ("list", "incoming", "footage"),
        ("find", "test_media", "clip"),
        ("hash", "incoming", "clip.mp4"),
        ("copy", "incoming", "clip.mp4", "jobs/clip.mp4", token),
        ("hash", "incoming", "clip.mp4"),
    ]
    assert resolve.test_project_checks == 1
    assert resolve.imports == [("incoming/clip.mp4", "Remote Agent", token)]


def test_mutating_media_handlers_refuse_an_already_cancelled_token_before_the_adapter_runs(tmp_path: Path) -> None:
    """Catches a cancelled copy/import job mutating media or Resolve after cancellation was requested."""
    registry, broker, resolve = registry_for(tmp_path)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(RuntimeError, match="cancelled"):
        registry.get("COPY_TO_WORKSPACE").handler(
            registry.validate_parameters("COPY_TO_WORKSPACE", {"source_alias": "incoming", "relative_path": "clip.mp4"}), token
        )
    with pytest.raises(RuntimeError, match="cancelled"):
        registry.get("IMPORT_MEDIA").handler(
            registry.validate_parameters("IMPORT_MEDIA", {"source_alias": "incoming", "relative_path": "clip.mp4"}), token
        )

    assert broker.calls == []
    assert resolve.imports == []


@pytest.mark.parametrize(
    ("action", "parameters"),
    [
        ("LIST_MEDIA", {"alias": "incoming", "unexpected": True}),
        ("HASH_MEDIA", {"alias": "incoming", "relative_path": "clip.mp4", "command": "whoami"}),
        ("COPY_TO_WORKSPACE", {"source_alias": "incoming", "relative_path": "clip.mp4", "destination_relative_path": "C:/outside/clip.mp4"}),
        ("IMPORT_MEDIA", {"source_alias": "incoming", "relative_path": "clip.mp4", "target_bin": "x", "extra": "no"}),
    ],
)
def test_media_parameter_schemas_reject_unknown_fields_and_absolute_paths(tmp_path: Path, action: str, parameters: dict[str, object]) -> None:
    """Catches remote jobs smuggling extra fields or an absolute broker path into a media handler."""
    registry, _, _ = registry_for(tmp_path)

    with pytest.raises(ValidationError):
        registry.validate_parameters(action, parameters)


def test_local_profile_cannot_be_widened_by_registered_handler(tmp_path: Path) -> None:
    """Catches a remotely requested but locally disabled action being retrievable for execution."""
    registry, _, _ = registry_for(tmp_path, allowed_actions=["PING"])

    with pytest.raises(PermissionError, match="not enabled"):
        registry.get("GET_STATUS")


def test_copy_schema_allows_an_explicit_null_destination_for_the_broker_default(tmp_path: Path) -> None:
    """Catches optional workspace destinations being treated as malformed remote paths."""
    registry, _, _ = registry_for(tmp_path)

    parameters = registry.validate_parameters(
        "COPY_TO_WORKSPACE",
        {"source_alias": "incoming", "relative_path": "clip.mp4", "destination_relative_path": None},
    )

    assert parameters.destination_relative_path is None


class FakeGit:
    def __init__(self, *, clean: bool = True, remote_sha: str = "a" * 40, ancestor: bool = True) -> None:
        self.clean = clean
        self.remote_sha = remote_sha
        self.ancestor = ancestor
        self.fast_forwards: list[tuple[str, str, str]] = []

    def remote_url(self, remote_name: str) -> str:
        assert remote_name == "origin"
        return "https://github.com/arphesegreteria-arch/video-editing-manual.git"

    def current_branch(self) -> str:
        return "main"

    def is_clean(self) -> bool:
        return self.clean

    def current_revision(self) -> str:
        return "b" * 40

    def remote_revision(self, remote_name: str, branch: str, token: CancellationToken) -> str:
        assert (remote_name, branch) == ("origin", "main")
        return self.remote_sha

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        assert ancestor == "b" * 40
        return self.ancestor and descendant == self.remote_sha

    def fast_forward(self, remote_name: str, branch: str, commit_sha: str, token: CancellationToken) -> None:
        self.fast_forwards.append((remote_name, branch, commit_sha))


@pytest.mark.parametrize(
    ("git", "expected_error"),
    [
        (FakeGit(clean=False), "clean"),
        (FakeGit(remote_sha="b" * 40), "exact"),
        (FakeGit(ancestor=False), "fast-forward"),
    ],
)
def test_approved_code_sync_refuses_any_non_fast_forward_or_dirty_update(tmp_path: Path, git: FakeGit, expected_error: str) -> None:
    """Catches code sync updating a dirty tree, a different remote commit, or divergent history."""
    service = ApprovedCodeSync(config(tmp_path, allowed_actions=["SYNC_APPROVED_CODE"]), git)

    with pytest.raises(PermissionError, match=expected_error):
        service.sync("a" * 40, CancellationToken())

    assert git.fast_forwards == []


def test_approved_code_sync_uses_only_configured_remote_branch_and_exact_sha(tmp_path: Path) -> None:
    """Catches a code deployment taking job-supplied commands or an unconfigured Git target."""
    git = FakeGit()
    service = ApprovedCodeSync(config(tmp_path, allowed_actions=["SYNC_APPROVED_CODE"]), git)

    token = CancellationToken()
    result = service.sync("a" * 40, token)

    assert result == {"updated_to": "a" * 40, "restart_required": True}
    assert git.fast_forwards == [("origin", "main", "a" * 40)]
    registry, _, _ = registry_for(tmp_path, allowed_actions=["SYNC_APPROVED_CODE"])
    with pytest.raises(ValidationError):
        registry.validate_parameters("SYNC_APPROVED_CODE", {"commit_sha": "a" * 40, "command": "git reset --hard"})


def test_approved_code_sync_refuses_a_cancelled_token_before_it_mutates_git(tmp_path: Path) -> None:
    """Catches a cancellation request being ignored at the Git fast-forward boundary."""
    git = FakeGit()
    service = ApprovedCodeSync(config(tmp_path, allowed_actions=["SYNC_APPROVED_CODE"]), git)
    token = CancellationToken()
    token.cancel()

    with pytest.raises(RuntimeError, match="cancelled"):
        service.sync("a" * 40, token)

    assert git.fast_forwards == []


def test_default_code_sync_binds_the_real_adapter_to_the_configured_checkout(tmp_path: Path) -> None:
    """Catches production registration deriving its Git checkout from the process CWD."""
    agent_config = config(tmp_path, allowed_actions=["SYNC_APPROVED_CODE"])

    service = default_code_sync(agent_config)

    assert isinstance(service.git_adapter, SubprocessGitSyncAdapter)
    assert service.git_adapter.repository_path == tmp_path / "video-editing-manual"


def test_subprocess_git_adapter_uses_the_configured_checkout_with_fixed_shell_free_argv(tmp_path: Path) -> None:
    """Catches controlled Git sync running in CWD, using a shell, or skipping its post-update HEAD check."""
    checkout = tmp_path / "fixed-checkout"
    sha = "a" * 40
    responses = iter(
        [
            "https://github.com/arphesegreteria-arch/video-editing-manual.git",
            "main",
            "",
            "b" * 40,
            "",
            sha,
            "",
            "",
            sha,
        ]
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    class Completed:
        returncode = 0

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def run(argv: list[str], **kwargs: object) -> Completed:
        calls.append((argv, kwargs))
        return Completed(next(responses))

    service = ApprovedCodeSync(
        config(tmp_path, allowed_actions=["SYNC_APPROVED_CODE"]),
        SubprocessGitSyncAdapter(checkout, run=run),
    )

    result = service.sync(sha, CancellationToken())

    assert result == {"updated_to": sha, "restart_required": True}
    assert [argv for argv, _ in calls] == [
        ["git", "-C", str(checkout), "remote", "get-url", "origin"],
        ["git", "-C", str(checkout), "branch", "--show-current"],
        ["git", "-C", str(checkout), "status", "--porcelain"],
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        ["git", "-C", str(checkout), "fetch", "--no-tags", "origin", "main"],
        ["git", "-C", str(checkout), "rev-parse", "origin/main"],
        ["git", "-C", str(checkout), "merge-base", "--is-ancestor", "b" * 40, sha],
        ["git", "-C", str(checkout), "merge", "--ff-only", sha],
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
    ]
    assert all(kwargs["shell"] is False for _, kwargs in calls)
