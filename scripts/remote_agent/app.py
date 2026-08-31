"""Production composition root for the visible ARPHE Remote Agent."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import threading

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.credentials import CredentialStore
from scripts.remote_agent.file_broker import FileBroker
from scripts.remote_agent.github_queue import GitHubQueue
from scripts.remote_agent.handler_registry import HandlerRegistry
from scripts.remote_agent.handlers import register_handlers
from scripts.remote_agent.job_runner import JobRunner
from scripts.remote_agent.lifecycle import LifecycleController, SingleInstanceLock
from scripts.remote_agent.logging_setup import configure_logging
from scripts.remote_agent.resolve_manager import ResolveManager


APP_VERSION = "1.0.0"


@dataclass
class RemoteAgentApplication:
    config: AgentConfig
    controller: LifecycleController
    logger: logging.Logger
    instance_lock: SingleInstanceLock | None

    def run(self) -> None:
        from scripts.remote_agent.ui.main_window import MainWindow

        MainWindow(self.controller).run()


def build_application(
    config_path: str | Path,
    *,
    agent_version: str = APP_VERSION,
    source_commit: str = "unknown",
    acquire_lock: bool = True,
) -> RemoteAgentApplication:
    """Validate local setup and wire every production dependency explicitly."""
    config = AgentConfig.load(config_path)
    for alias in config.folders.aliases():
        folder = config.folders.path_for(alias)
        if not folder.is_dir():
            raise RuntimeError(f"configured folder alias is unavailable: {alias}")

    instance_lock = SingleInstanceLock(config.machine_id) if acquire_lock else None
    if instance_lock is not None:
        instance_lock.acquire()
    try:
        # This is the only production logger construction path. JobRunner rejects
        # anything that is not the verified machine-specific redacting logger.
        logger = configure_logging(config.machine_id)
        token = CredentialStore(config).get_token()
        if not token:
            raise RuntimeError("GitHub token is missing from Windows Credential Manager")

        queue = GitHubQueue(config.github, token)
        file_broker = FileBroker(config.folders)
        resolve_manager = ResolveManager(config.resolve)
        resolve_manager.connect(5.0)
        registry = HandlerRegistry(config.allowed_actions)
        register_handlers(
            registry,
            config,
            file_broker,
            resolve_manager,
            agent_version=agent_version,
            source_commit=source_commit,
        )
        cancellation = threading.Event()
        runner = JobRunner(
            config,
            queue,
            registry,
            agent_version=agent_version,
            source_commit=source_commit,
            logger=logger,
            cancellation_requested=cancellation.is_set,
        )
        controller = LifecycleController(
            config,
            queue,
            runner,
            resolve_manager,
            agent_version=agent_version,
            source_commit=source_commit,
            logger=logger,
            cancellation_event=cancellation,
            instance_lock=instance_lock,
        )
        return RemoteAgentApplication(config, controller, logger, instance_lock)
    except BaseException:
        if instance_lock is not None:
            instance_lock.release()
        raise
