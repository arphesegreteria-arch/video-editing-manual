from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import logging
from pathlib import Path
import threading
import time

import pytest

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.github_queue import ClaimConflict, QueuedJob
from scripts.remote_agent.handler_registry import HandlerRegistry
from scripts.remote_agent.handlers.agent_status import PingParameters
from scripts.remote_agent.job_runner import JobRunner
from scripts.remote_agent.lifecycle import CloseMode, LifecycleController, ThreadScheduler
from scripts.remote_agent.logging_setup import configure_redacting_logger
from scripts.remote_agent.models import AgentState, Job, JobStatus


def _config(tmp_path: Path) -> AgentConfig:
    folders = {}
    for alias in ("incoming", "test_media", "workspace", "exports"):
        path = (tmp_path / alias).resolve()
        path.mkdir(exist_ok=True)
        folders[alias] = str(path)
    return AgentConfig.model_validate(
        {
            "machine_id": "HOME_DEV",
            "poll_interval_seconds": 30,
            "folders": folders,
            "resolve": {
                "executable_path": "C:/Program Files/Blackmagic Design/DaVinci Resolve/Resolve.exe"
            },
            "github": {"owner": "arphe", "repository": "jobs"},
            "allowed_actions": ["PING"],
        }
    )


def _job(*, job_id: str = "job-001", target_machine: str = "HOME_DEV", timeout_seconds: int = 5) -> Job:
    return Job.model_validate(
        {
            "job_id": job_id,
            "target_machine": target_machine,
            "action": "PING",
            "created_at": "2026-08-28T00:00:00Z",
            "requested_by": "arphe",
            "retryable": False,
            "timeout_seconds": timeout_seconds,
            "parameters": {},
        }
    )


def _registry(*, handler=None) -> HandlerRegistry:
    registry = HandlerRegistry(["PING"])
    registry.register(
        "PING",
        PingParameters,
        handler or (lambda _parameters, _token: {"pong": True}),
        idempotent=True,
    )
    return registry


def _safe_logger() -> logging.Logger:
    return configure_redacting_logger(
        logging.Logger("arphe.remote_agent.HOME_DEV"),
        [logging.StreamHandler(StringIO())],
    )


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class ManualScheduler:
    def __init__(self) -> None:
        self._permits = threading.Semaphore(0)

    def wait(self, _delay: float, stopped: threading.Event) -> bool:
        while not stopped.is_set():
            if self._permits.acquire(timeout=0.01):
                return stopped.is_set()
        return True

    def wake(self) -> None:
        self._permits.release()

    def advance(self) -> None:
        self._permits.release()


class FakeResolve:
    def connect(self, _timeout_seconds: float):
        return None

    def get_status(self):
        return {"status": "connected", "connected": True, "version": "19.1"}


class RecordingQueue:
    def __init__(self, queued_job: QueuedJob | None) -> None:
        self.queued_job = queued_job
        self.transitions: list[str] = []
        self.results = []
        self.terminal: list[QueuedJob] = []
        self.heartbeats = []
        self.claims = 0
        self.running = 0

    def list_pending(self, machine_id: str) -> list[QueuedJob]:
        self.transitions.append(f"LIST:{machine_id}")
        return [] if self.queued_job is None else [self.queued_job]

    def claim(self, candidate: Job, sha: str, *, idempotent: bool) -> QueuedJob:
        self.transitions.append(f"CLAIM:{candidate.job_id}:{sha}:{idempotent}")
        self.claims += 1
        claimed = candidate.model_copy(
            update={
                "status": JobStatus.CLAIMED,
                "claimed_by": candidate.target_machine,
                "claimed_at": datetime(2026, 8, 28, tzinfo=timezone.utc),
                "lease_expires_at": datetime(2026, 8, 29, tzinfo=timezone.utc),
                "attempt": 1,
            }
        )
        return QueuedJob(claimed, "claimed-sha")

    def mark_running(self, claimed: QueuedJob) -> QueuedJob:
        self.transitions.append(f"RUNNING:{claimed.job.job_id}:{claimed.sha}")
        self.running += 1
        return QueuedJob(claimed.job.model_copy(update={"status": JobStatus.RUNNING}), "running-sha")

    def write_result(self, result) -> None:
        self.transitions.append(f"RESULT:{result.job_id}:{result.status.value}")
        self.results.append(result)

    def mark_terminal(self, running: QueuedJob, status: JobStatus) -> QueuedJob:
        self.transitions.append(f"TERMINAL:{running.job.job_id}:{status.value}")
        terminal = QueuedJob(running.job.model_copy(update={"status": status}), "terminal-sha")
        self.terminal.append(terminal)
        return terminal

    def write_heartbeat(self, heartbeat) -> None:
        self.heartbeats.append(heartbeat)


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached")


def test_full_pending_to_succeeded_flow_uses_real_runner_transitions(tmp_path: Path) -> None:
    queue = RecordingQueue(QueuedJob(_job(), "source-sha"))
    runner = JobRunner(
        _config(tmp_path),
        queue,
        _registry(),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
    )

    result = runner.run_once()

    assert result is not None
    assert result.status is JobStatus.SUCCEEDED
    assert result.output == {"pong": True}
    assert queue.transitions == [
        "LIST:HOME_DEV",
        "CLAIM:job-001:source-sha:True",
        "RUNNING:job-001:claimed-sha",
        "RESULT:job-001:SUCCEEDED",
        "TERMINAL:job-001:SUCCEEDED",
    ]


def test_target_mismatch_never_crosses_the_claim_boundary(tmp_path: Path) -> None:
    queue = RecordingQueue(QueuedJob(_job(target_machine="POLI_01"), "source-sha"))
    runner = JobRunner(
        _config(tmp_path),
        queue,
        _registry(),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
    )

    assert runner.run_once() is None
    assert queue.transitions == ["LIST:HOME_DEV"]
    assert queue.claims == 0
    assert queue.results == []


def test_claim_conflict_enters_visible_backoff_without_persisting_results(tmp_path: Path) -> None:
    class ConflictQueue(RecordingQueue):
        def claim(self, candidate: Job, sha: str, *, idempotent: bool) -> QueuedJob:
            self.transitions.append(f"CLAIM_CONFLICT:{candidate.job_id}:{sha}:{idempotent}")
            raise ClaimConflict("job document changed before update")

    queue = ConflictQueue(QueuedJob(_job(), "source-sha"))
    scheduler = ManualScheduler()
    clock = FakeClock()
    runner = JobRunner(
        _config(tmp_path),
        queue,
        _registry(),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
    )
    controller = LifecycleController(
        _config(tmp_path),
        queue,
        runner,
        FakeResolve(),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
        scheduler=scheduler,
        monotonic=clock,
    )

    controller.start(ui_visible=True)
    _wait_for(lambda: controller.state is AgentState.ERROR)
    controller.shutdown()

    assert controller.retry_delay_seconds == 60.0
    assert queue.results == []
    assert queue.terminal == []
    assert "CLAIM_CONFLICT:job-001:source-sha:True" in queue.transitions


def test_github_outage_backoff_grows_across_real_controller_polls(tmp_path: Path) -> None:
    class OutageQueue(RecordingQueue):
        def list_pending(self, machine_id: str) -> list[QueuedJob]:
            self.transitions.append(f"LIST_FAIL:{machine_id}")
            raise RuntimeError("GitHub unavailable")

    queue = OutageQueue(None)
    scheduler = ManualScheduler()
    clock = FakeClock()
    runner = JobRunner(
        _config(tmp_path),
        queue,
        _registry(),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
    )
    controller = LifecycleController(
        _config(tmp_path),
        queue,
        runner,
        FakeResolve(),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
        scheduler=scheduler,
        monotonic=clock,
    )

    controller.start(ui_visible=True)
    _wait_for(lambda: controller.state is AgentState.ERROR and controller.retry_delay_seconds == 60.0)
    assert "GitHub" in controller.status_message

    clock.advance(60.0)
    scheduler.advance()
    _wait_for(lambda: controller.retry_delay_seconds == 120.0)
    controller.shutdown()

    assert queue.transitions.count("LIST_FAIL:HOME_DEV") >= 2


def test_timeout_persists_failed_timeout_terminal_state(tmp_path: Path) -> None:
    started = threading.Event()

    def slow_handler(_parameters, token):
        started.set()
        while not token.cancelled:
            time.sleep(0.005)
        return {"stopped": True}

    queue = RecordingQueue(QueuedJob(_job(timeout_seconds=5), "source-sha"))
    runner = JobRunner(
        _config(tmp_path),
        queue,
        _registry(handler=slow_handler),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
        monotonic=iter((0.0, 6.0)).__next__,
    )

    result = runner.run_once()

    assert started.is_set()
    assert result is not None
    assert result.status is JobStatus.FAILED_TIMEOUT
    assert [item.job.status for item in queue.terminal] == [JobStatus.FAILED_TIMEOUT]


def test_abort_close_flow_leaves_no_running_job_or_heartbeat(tmp_path: Path) -> None:
    cleanup_seen = threading.Event()

    def blocking_handler(_parameters, token):
        while not token.cancelled:
            time.sleep(0.005)
        cleanup_seen.set()
        return {"cleaned": True}

    queue = RecordingQueue(QueuedJob(_job(job_id="job-abort"), "source-sha"))
    cancellation = threading.Event()
    runner = JobRunner(
        _config(tmp_path),
        queue,
        _registry(handler=blocking_handler),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
        cancellation_requested=cancellation.is_set,
    )
    controller = LifecycleController(
        _config(tmp_path),
        queue,
        runner,
        FakeResolve(),
        agent_version="1.0.0",
        source_commit="abc123",
        logger=_safe_logger(),
        cancellation_event=cancellation,
        scheduler=ThreadScheduler(),
        monotonic=time.monotonic,
    )

    controller.start(ui_visible=True)
    _wait_for(lambda: controller.snapshot().current_job == "job-abort")

    assert controller.request_close(CloseMode.ABORT_CURRENT) is False
    controller.wait_until_stopped(timeout=1)

    assert cleanup_seen.is_set()
    assert controller.state is AgentState.OFFLINE
    assert controller.last_job_status is JobStatus.ABORTED
    assert controller.snapshot().current_job == "-"
    assert any(result.status is JobStatus.ABORTED for result in queue.results)
    assert all(heartbeat.current_job_id is None for heartbeat in queue.heartbeats)


def test_build_application_fails_closed_when_resolve_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    from scripts.remote_agent import app

    config = _config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")

    class FailingResolve(FakeResolve):
        def connect(self, timeout_seconds):
            raise RuntimeError(f"Resolve unavailable within {timeout_seconds} seconds")

    monkeypatch.setattr(app, "configure_logging", lambda _machine_id: _safe_logger())
    monkeypatch.setattr(
        app,
        "CredentialStore",
        lambda _config: type("Store", (), {"get_token": lambda self: "token"})(),
    )
    monkeypatch.setattr(app, "GitHubQueue", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(app, "FileBroker", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(app, "ResolveManager", lambda *_args, **_kwargs: FailingResolve())
    monkeypatch.setattr(app, "register_handlers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "JobRunner", lambda *_args, **_kwargs: object())

    with pytest.raises(RuntimeError, match="Resolve unavailable"):
        app.build_application(config_path, acquire_lock=False)
