from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading

import pytest

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.github_queue import QueuedJob
from scripts.remote_agent.handler_registry import HandlerRegistry
from scripts.remote_agent.job_runner import JobRunner, RunnerState
from scripts.remote_agent.models import Job, JobStatus


def config(tmp_path: Path) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "machine_id": "HOME_DEV",
            "folders": {name: str(tmp_path / name) for name in ("incoming", "test_media", "workspace", "exports")},
            "resolve": {"executable_path": str(tmp_path / "Resolve.exe")},
            "github": {"owner": "arphesegreteria-arch", "repository": "video-editing-manual"},
            "allowed_actions": ["PING"],
        }
    )


def job(*, target_machine: str = "HOME_DEV", action: str = "PING", timeout_seconds: int = 5) -> Job:
    return Job.model_validate(
        {
            "job_id": "job-001",
            "target_machine": target_machine,
            "action": action,
            "created_at": "2026-08-28T00:00:00Z",
            "requested_by": "arphe",
            "retryable": False,
            "timeout_seconds": timeout_seconds,
            "parameters": {},
        }
    )


class FakeQueue:
    def __init__(self, queued: QueuedJob) -> None:
        self.queued = queued
        self.claims = 0
        self.running = 0
        self.results = []
        self.terminal: list[QueuedJob] = []

    def list_pending(self, machine_id: str) -> list[QueuedJob]:
        return [self.queued]

    def claim(self, candidate: Job, sha: str, *, idempotent: bool) -> QueuedJob:
        self.claims += 1
        claimed = candidate.model_copy(update={"status": JobStatus.CLAIMED, "claimed_by": candidate.target_machine, "lease_expires_at": datetime(2026, 8, 29, tzinfo=timezone.utc)})
        return QueuedJob(claimed, "claimed-sha")

    def mark_running(self, claimed: QueuedJob) -> QueuedJob:
        self.running += 1
        return QueuedJob(claimed.job.model_copy(update={"status": JobStatus.RUNNING}), "running-sha")

    def write_result(self, result) -> None:
        self.results.append(result)

    def mark_terminal(self, running: QueuedJob, status: JobStatus) -> QueuedJob:
        terminal = QueuedJob(running.job.model_copy(update={"status": status}), "terminal-sha")
        self.terminal.append(terminal)
        return terminal


def registry(*, enabled: bool = True) -> HandlerRegistry:
    handler_registry = HandlerRegistry(["PING"] if enabled else [])
    from scripts.remote_agent.handlers.agent_status import PingParameters

    handler_registry.register("PING", PingParameters, lambda _parameters: {"pong": True}, idempotent=True)
    return handler_registry


def test_runner_validates_target_and_profile_before_claim(tmp_path: Path) -> None:
    """Catches claiming a job addressed to another machine or disabled by the local profile."""
    target_queue = FakeQueue(QueuedJob(job(target_machine="POLI_01"), "source-sha"))
    target_runner = JobRunner(config(tmp_path), target_queue, registry(), agent_version="1", source_commit="abc")
    profile_queue = FakeQueue(QueuedJob(job(), "source-sha"))
    profile_runner = JobRunner(config(tmp_path), profile_queue, registry(enabled=False), agent_version="1", source_commit="abc")

    assert target_runner.run_once() is None
    assert profile_runner.run_once() is None
    assert target_queue.claims == profile_queue.claims == 0
    assert target_queue.results == profile_queue.results == []


def test_runner_claims_runs_and_writes_structured_success_result(tmp_path: Path) -> None:
    """Catches the runner skipping a queue transition or losing a handler's structured output."""
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(config(tmp_path), queue, registry(), agent_version="1", source_commit="abc")

    result = runner.run_once()

    assert result is not None
    assert result.status is JobStatus.SUCCEEDED
    assert result.output == {"pong": True}
    assert queue.claims == queue.running == 1
    assert queue.results == [result]
    assert [item.job.status for item in queue.terminal] == [JobStatus.SUCCEEDED]


def test_runner_aborts_before_handler_when_cancellation_is_requested(tmp_path: Path) -> None:
    """Catches a cancellation request being ignored after a job has been safely claimed."""
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(config(tmp_path), queue, registry(), agent_version="1", source_commit="abc", cancellation_requested=lambda: True)

    result = runner.run_once()

    assert result is not None
    assert result.status is JobStatus.ABORTED
    assert result.error_type == "Cancelled"
    assert queue.claims == queue.running == 1


def test_runner_serializes_concurrent_calls_and_sanitizes_secret_handler_failure(tmp_path: Path) -> None:
    """Catches a second caller claiming while a job runs or a secret exception escaping result validation."""
    started, release, stopped = threading.Event(), threading.Event(), threading.Event()
    from scripts.remote_agent.handlers.agent_status import PingParameters
    handler_registry = HandlerRegistry(["PING"])
    def handler(_p, token):
        started.set(); release.wait(1)
        if token.cancelled:
            return {"cancelled": True}
        raise RuntimeError("token=abc")
    handler_registry.register("PING", PingParameters, handler, idempotent=True)
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(config(tmp_path), queue, handler_registry, agent_version="1", source_commit="abc")
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(runner.run_once()))
    thread.start(); assert started.wait(1)
    assert runner.run_once() is None and queue.claims == 1
    release.set(); thread.join(1)
    result = outcome[0]
    assert result.status is JobStatus.FAILED
    assert "abc" not in result.error_message
    assert queue.results == [result]


def test_runner_cancels_and_joins_handler_before_persisting_aborted_result(tmp_path: Path) -> None:
    """Catches persisting ABORTED while a destructive handler is still running."""
    started, cleaned = threading.Event(), threading.Event()
    cancelling = [False]
    from scripts.remote_agent.handlers.agent_status import PingParameters
    r = HandlerRegistry(["PING"])

    def handler(_p, token):
        started.set()
        while not token.cancelled:
            threading.Event().wait(0.01)
        cleaned.set()
        return {"cleaned": True}

    r.register("PING", PingParameters, handler)
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(config(tmp_path), queue, r, agent_version="1", source_commit="abc", cancellation_requested=lambda: cancelling[0])
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(runner.run_once()))
    thread.start()
    assert started.wait(1)

    cancelling[0] = True
    thread.join(1)

    assert cleaned.is_set()
    assert outcome[0].status is JobStatus.ABORTED
    assert queue.results == [outcome[0]]
    assert queue.terminal[0].job.status is JobStatus.ABORTED


def test_runner_holds_the_gate_without_persisting_when_cleanup_bound_is_exhausted(tmp_path: Path) -> None:
    """Catches an uncooperative mutator being marked terminal while it can still run."""
    started, release, stopped = threading.Event(), threading.Event(), threading.Event()
    cancelling = [False]
    from scripts.remote_agent.handlers.agent_status import PingParameters

    registry = HandlerRegistry(["PING"])

    def handler(_parameters, _token):
        started.set()
        assert release.wait(1)
        stopped.set()
        return {"finished": True}

    registry.register("PING", PingParameters, handler)
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(
        config(tmp_path),
        queue,
        registry,
        agent_version="1",
        source_commit="abc",
        cancellation_requested=lambda: cancelling[0],
        cleanup_timeout_seconds=0.01,
    )
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(runner.run_once()))
    thread.start()
    assert started.wait(1)

    cancelling[0] = True
    thread.join(1)

    assert outcome == [None]
    assert runner.state is RunnerState.CANCELLATION_CLEANUP_PENDING
    assert queue.results == []
    assert queue.terminal == []
    assert runner.run_once() is None
    assert queue.claims == 1

    release.set()
    assert stopped.wait(1)
    assert runner.run_once() is not None
    assert queue.results[0].status is JobStatus.ABORTED
    assert queue.terminal[0].job.status is JobStatus.ABORTED
    assert runner.state is RunnerState.IDLE


def test_runner_times_out_only_after_the_handler_observes_its_cancellation_token(tmp_path: Path) -> None:
    """Catches a timeout being persisted before the handler has stopped mutating."""
    started, stopped = threading.Event(), threading.Event()
    timestamps = iter((0.0, 6.0))
    from scripts.remote_agent.handlers.agent_status import PingParameters

    registry = HandlerRegistry(["PING"])

    def handler(_parameters, token):
        started.set()
        while not token.cancelled:
            threading.Event().wait(0.005)
        stopped.set()
        return {"stopped": True}

    registry.register("PING", PingParameters, handler)
    queue = FakeQueue(QueuedJob(job(timeout_seconds=5), "source-sha"))
    runner = JobRunner(
        config(tmp_path), queue, registry, agent_version="1", source_commit="abc", monotonic=lambda: next(timestamps)
    )

    result = runner.run_once()

    assert started.is_set() and stopped.is_set()
    assert result.status is JobStatus.FAILED_TIMEOUT
    assert queue.results == [result]
    assert queue.terminal[0].job.status is JobStatus.FAILED_TIMEOUT


def test_runner_gives_observed_completion_precedence_over_a_simultaneous_cancellation_request(tmp_path: Path) -> None:
    """Catches a completed handler being rewritten as aborted solely because a later poll sees cancellation."""
    handler_finished = threading.Event()
    from scripts.remote_agent.handlers.agent_status import PingParameters

    registry = HandlerRegistry(["PING"])

    def handler(_parameters, _token):
        handler_finished.set()
        return {"finished": True}

    registry.register("PING", PingParameters, handler)
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(
        config(tmp_path),
        queue,
        registry,
        agent_version="1",
        source_commit="abc",
        cancellation_requested=handler_finished.is_set,
    )

    result = runner.run_once()

    assert result.status is JobStatus.SUCCEEDED
    assert result.output == {"finished": True}
