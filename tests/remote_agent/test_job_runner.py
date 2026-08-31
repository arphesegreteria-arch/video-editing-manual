from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import logging
from pathlib import Path
import threading

import pytest

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.github_queue import QueuedJob
from scripts.remote_agent.handler_registry import HandlerRegistry
from scripts.remote_agent.job_runner import JobRunner, RunnerState
from scripts.remote_agent.logging_setup import configure_redacting_logger
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
        self.terminal_inputs: list[QueuedJob] = []

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
        self.terminal_inputs.append(running)
        terminal = QueuedJob(running.job.model_copy(update={"status": status}), "terminal-sha")
        self.terminal.append(terminal)
        return terminal


def registry(*, enabled: bool = True) -> HandlerRegistry:
    handler_registry = HandlerRegistry(["PING"] if enabled else [])
    from scripts.remote_agent.handlers.agent_status import PingParameters

    handler_registry.register("PING", PingParameters, lambda _parameters: {"pong": True}, idempotent=True)
    return handler_registry


def safe_logger(
    stream: StringIO | None = None,
    *,
    handler: logging.Handler | None = None,
) -> logging.Logger:
    """Build an in-memory logger through the production redaction contract."""
    logger = logging.Logger("arphe.remote_agent.HOME_DEV")
    backend = handler if handler is not None else logging.StreamHandler(
        stream if stream is not None else StringIO()
    )
    return configure_redacting_logger(logger, [backend])


class RecordingStreamHandler(logging.StreamHandler):
    def __init__(self, stream: StringIO) -> None:
        super().__init__(stream)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        super().emit(record)


def test_runner_fails_closed_when_logger_wiring_is_missing(tmp_path: Path) -> None:
    """Catches production construction silently falling back to a bare named logger."""
    with pytest.raises(TypeError, match="logger"):
        JobRunner(
            config(tmp_path),
            FakeQueue(QueuedJob(job(), "source-sha")),
            registry(),
            agent_version="1",
            source_commit="abc",
        )


def test_runner_rejects_non_redacting_or_propagating_logger_wiring(tmp_path: Path) -> None:
    """Catches raw handler failures reaching an unformatted handler or the root logger."""
    unsafe = logging.Logger("arphe.remote_agent.HOME_DEV")
    unsafe.propagate = False
    unsafe.addHandler(logging.StreamHandler(StringIO()))
    propagating = safe_logger()
    propagating.propagate = True
    muted = safe_logger()
    muted.handlers[0].setLevel(logging.CRITICAL)

    for logger in (unsafe, propagating, muted):
        with pytest.raises(ValueError, match="centrally configured redacting logger"):
            JobRunner(
                config(tmp_path),
                FakeQueue(QueuedJob(job(), "source-sha")),
                registry(),
                agent_version="1",
                source_commit="abc",
                logger=logger,
            )


def test_runner_validates_target_and_profile_before_claim(tmp_path: Path) -> None:
    """Catches claiming a job addressed to another machine or disabled by the local profile."""
    target_queue = FakeQueue(QueuedJob(job(target_machine="POLI_01"), "source-sha"))
    target_runner = JobRunner(
        config(tmp_path),
        target_queue,
        registry(),
        agent_version="1",
        source_commit="abc",
        logger=safe_logger(),
    )
    profile_queue = FakeQueue(QueuedJob(job(), "source-sha"))
    profile_runner = JobRunner(
        config(tmp_path),
        profile_queue,
        registry(enabled=False),
        agent_version="1",
        source_commit="abc",
        logger=safe_logger(),
    )

    assert target_runner.run_once() is None
    assert profile_runner.run_once() is None
    assert target_queue.claims == profile_queue.claims == 0
    assert target_queue.results == profile_queue.results == []


def test_runner_claims_runs_and_writes_structured_success_result(tmp_path: Path) -> None:
    """Catches the runner skipping a queue transition or losing a handler's structured output."""
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(
        config(tmp_path),
        queue,
        registry(),
        agent_version="1",
        source_commit="abc",
        logger=safe_logger(),
    )

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
    runner = JobRunner(
        config(tmp_path),
        queue,
        registry(),
        agent_version="1",
        source_commit="abc",
        cancellation_requested=lambda: True,
        logger=safe_logger(),
    )

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
    runner = JobRunner(
        config(tmp_path), queue, handler_registry, agent_version="1", source_commit="abc", logger=safe_logger()
    )
    outcome = []
    thread = threading.Thread(target=lambda: outcome.append(runner.run_once()))
    thread.start(); assert started.wait(1)
    assert runner.run_once() is None and queue.claims == 1
    release.set(); thread.join(1)
    result = outcome[0]
    assert result.status is JobStatus.FAILED
    assert "abc" not in result.error_message
    assert queue.results == [result]


@pytest.mark.parametrize(
    "exception_text",
    [
        "Authorization: Bearer alpha beta gamma",
        "{'Authorization': 'Bearer alpha beta gamma'}",
        "token=alpha beta gamma",
        "alpha beta gamma " + "x" * 5001,
    ],
)
def test_runner_persists_an_opaque_terminal_result_for_hostile_exception_text(
    tmp_path: Path, exception_text: str
) -> None:
    """Catches raw handler exception text escaping remotely or breaking terminal persistence."""
    from scripts.remote_agent.handlers.agent_status import PingParameters

    handler_registry = HandlerRegistry(["PING"])

    def handler(_parameters):
        raise RuntimeError(exception_text)

    handler_registry.register("PING", PingParameters, handler)
    queue = FakeQueue(QueuedJob(job(), "source-sha"))
    runner = JobRunner(
        config(tmp_path), queue, handler_registry, agent_version="1", source_commit="abc", logger=safe_logger()
    )

    result = runner.run_once()

    assert result is not None
    assert result.status is JobStatus.FAILED
    assert result.error_type == "HandlerFailure"
    assert result.error_message == "handler failed; see redacted local logs"
    assert all(fragment not in result.error_message for fragment in ("alpha", "beta", "gamma", "x" * 32))
    assert queue.results == [result]
    assert [item.job.status for item in queue.terminal] == [JobStatus.FAILED]
    assert [item.sha for item in queue.terminal_inputs] == ["running-sha"]


def test_runner_routes_raw_handler_failure_only_through_redacting_backend(tmp_path: Path) -> None:
    """Catches exception detail leaking to root while proving the local handler receives it."""
    from scripts.remote_agent.handlers.agent_status import PingParameters

    hostile_text = "token=alpha beta gamma"
    handler_registry = HandlerRegistry(["PING"])

    def handler(_parameters):
        raise RuntimeError(hostile_text)

    handler_registry.register("PING", PingParameters, handler)
    local_stream = StringIO()
    local_handler = RecordingStreamHandler(local_stream)
    root_stream = StringIO()
    root_handler = logging.StreamHandler(root_stream)
    root_logger = logging.getLogger()
    root_logger.addHandler(root_handler)
    try:
        runner = JobRunner(
            config(tmp_path),
            FakeQueue(QueuedJob(job(), "source-sha")),
            handler_registry,
            agent_version="1",
            source_commit="abc",
            logger=safe_logger(handler=local_handler),
        )
        result = runner.run_once()
    finally:
        root_logger.removeHandler(root_handler)

    assert len(local_handler.records) == 1
    assert hostile_text in str(local_handler.records[0].exc_info[1])
    assert hostile_text not in local_stream.getvalue()
    assert "token=[REDACTED]" in local_stream.getvalue()
    assert root_stream.getvalue() == ""
    assert result is not None
    assert result.error_type == "HandlerFailure"
    assert result.error_message == "handler failed; see redacted local logs"


def test_runner_suppresses_raw_failure_if_logger_becomes_unsafe_after_construction(
    tmp_path: Path,
) -> None:
    """Catches later logger mutation bypassing the constructor's fail-closed check."""
    from scripts.remote_agent.handlers.agent_status import PingParameters

    handler_registry = HandlerRegistry(["PING"])

    def handler(_parameters):
        raise RuntimeError("token=late mutation secret")

    handler_registry.register("PING", PingParameters, handler)
    local_stream = StringIO()
    logger = safe_logger(local_stream)
    runner = JobRunner(
        config(tmp_path),
        FakeQueue(QueuedJob(job(), "source-sha")),
        handler_registry,
        agent_version="1",
        source_commit="abc",
        logger=logger,
    )
    root_stream = StringIO()
    root_handler = logging.StreamHandler(root_stream)
    root_logger = logging.getLogger()
    root_logger.addHandler(root_handler)
    logger.propagate = True
    try:
        result = runner.run_once()
    finally:
        root_logger.removeHandler(root_handler)

    assert local_stream.getvalue() == ""
    assert root_stream.getvalue() == ""
    assert result is not None
    assert result.error_type == "HandlerFailure"
    assert result.error_message == "handler failed; see redacted local logs"


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
    runner = JobRunner(
        config(tmp_path),
        queue,
        r,
        agent_version="1",
        source_commit="abc",
        cancellation_requested=lambda: cancelling[0],
        logger=safe_logger(),
    )
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
        logger=safe_logger(),
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
        config(tmp_path),
        queue,
        registry,
        agent_version="1",
        source_commit="abc",
        monotonic=lambda: next(timestamps),
        logger=safe_logger(),
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
        logger=safe_logger(),
    )

    result = runner.run_once()

    assert result.status is JobStatus.SUCCEEDED
    assert result.output == {"finished": True}
