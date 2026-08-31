"""Single-job, allowlist-first execution for the remote agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import inspect
import re
import threading
import time
from typing import Any

from scripts.remote_agent.cancellation import CancellationToken
from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.github_queue import QueuedJob
from scripts.remote_agent.handler_registry import HandlerRegistry, RegisteredHandler
from scripts.remote_agent.logging_setup import redact_secrets
from scripts.remote_agent.models import JobResult, JobStatus


class RunnerState(str, Enum):
    """Externally visible local safety state for the one-job gate."""

    IDLE = "IDLE"
    CANCELLATION_CLEANUP_PENDING = "CANCELLATION_CLEANUP_PENDING"


@dataclass(frozen=True)
class _PendingCleanup:
    """A cancellation whose handler must exit before terminal persistence."""

    running: QueuedJob
    started_at: datetime
    status: JobStatus
    error_type: str
    error_message: str
    worker: threading.Thread


class JobRunner:
    """Claim at most one locally permitted job and write one terminal result."""

    def __init__(
        self,
        config: AgentConfig,
        queue: object,
        registry: HandlerRegistry,
        *,
        agent_version: str,
        source_commit: str,
        cancellation_requested: Callable[[], bool] | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        cleanup_timeout_seconds: float = 5.0,
    ) -> None:
        if cleanup_timeout_seconds <= 0:
            raise ValueError("cleanup_timeout_seconds must be positive")
        self._config = config
        self._queue = queue
        self._registry = registry
        self._agent_version = agent_version
        self._source_commit = source_commit
        self._cancellation_requested = cancellation_requested or (lambda: False)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic
        self._cleanup_timeout_seconds = cleanup_timeout_seconds
        self._active_worker: threading.Thread | None = None
        self._pending_cleanup: _PendingCleanup | None = None
        self._state = RunnerState.IDLE
        self._run_lock = threading.Lock()
        self._reserved = False

    @property
    def state(self) -> RunnerState:
        """Return whether a timed-out/cancelled handler still owns the job gate."""
        with self._run_lock:
            return self._state

    def run_once(self) -> JobResult | None:
        """Run one pending job, or return ``None`` when nothing is safely runnable."""
        with self._run_lock:
            if self._reserved:
                return None
            pending_cleanup = self._pending_cleanup
            if pending_cleanup is not None and pending_cleanup.worker.is_alive():
                return None
            if self._active_worker is not None and self._active_worker.is_alive():
                return None
            self._active_worker = None
            self._reserved = True
        try:
            if pending_cleanup is not None:
                return self._finish_pending_cleanup(pending_cleanup)
            candidates = getattr(self._queue, "list_pending")(self._config.machine_id)
            for candidate in candidates:
                job = candidate.job
                if not job.matches_machine(self._config.machine_id):
                    continue
                try:
                    registered = self._registry.get(job.action)
                    parameters = self._registry.validate_parameters(job.action, job.parameters)
                except (KeyError, PermissionError, ValueError):
                    continue
                return self._claim_and_execute(candidate, registered, parameters)
            return None
        finally:
            with self._run_lock:
                self._reserved = False

    def _claim_and_execute(self, candidate: QueuedJob, registered: RegisteredHandler, parameters: Any) -> JobResult | None:
        claimed = getattr(self._queue, "claim")(candidate.job, candidate.sha, idempotent=registered.idempotent)
        running = getattr(self._queue, "mark_running")(claimed)
        job = running.job
        started_at = self._utc_now()
        token = CancellationToken()

        if self._cancellation_requested():
            token.cancel()
            result = self._result(job, started_at, JobStatus.ABORTED, error_type="Cancelled", error_message="cancellation requested before handler start")
        else:
            result = self._execute(running, registered, parameters, token, started_at)
        if isinstance(result, _PendingCleanup):
            with self._run_lock:
                self._pending_cleanup = result
                self._state = RunnerState.CANCELLATION_CLEANUP_PENDING
            return None
        self._persist_terminal(running, result)
        return result

    def _execute(
        self, running: QueuedJob, registered: RegisteredHandler, parameters: Any, token: CancellationToken, started_at: datetime
    ) -> JobResult | _PendingCleanup:
        job = running.job
        completed = threading.Event()
        outcome: dict[str, Any] = {}

        def invoke() -> None:
            try:
                outcome["output"] = self._invoke(registered, parameters, token)
            except BaseException as exc:  # Handler failures become safe terminal results.
                outcome["exception"] = exc
            finally:
                completed.set()

        worker = threading.Thread(target=invoke, daemon=True, name=f"remote-agent-{job.job_id}")
        self._active_worker = worker
        worker.start()
        deadline = self._monotonic() + job.timeout_seconds
        while True:
            if completed.wait(timeout=0.05):
                break
            # Completion wins if it was observed before cancellation/deadline
            # is requested; otherwise cancellation takes precedence over timeout.
            if completed.is_set():
                break
            if self._cancellation_requested():
                token.cancel()
                return self._cancel_and_join(
                    running,
                    started_at,
                    JobStatus.ABORTED,
                    "Cancelled",
                    "cancellation requested while handler was running",
                    completed,
                    worker,
                )
            if self._monotonic() >= deadline:
                token.cancel()
                return self._cancel_and_join(
                    running,
                    started_at,
                    JobStatus.FAILED_TIMEOUT,
                    "Timeout",
                    "handler exceeded its configured timeout",
                    completed,
                    worker,
                )

        self._active_worker = None
        if token.cancelled:
            return self._result(job, started_at, JobStatus.ABORTED, error_type="Cancelled", error_message="handler observed cancellation")
        if "exception" in outcome:
            exception = outcome["exception"]
            return self._result(
                job,
                started_at,
                JobStatus.FAILED,
                error_type=type(exception).__name__,
                error_message=self._safe_error(str(exception)),
            )
        output = outcome.get("output")
        if not isinstance(output, dict):
            return self._result(job, started_at, JobStatus.FAILED, error_type="HandlerContractError", error_message="handler output must be a JSON object")
        try:
            return self._result(job, started_at, JobStatus.SUCCEEDED, output=output)
        except ValueError as exc:
            return self._result(job, started_at, JobStatus.FAILED, error_type="UnsafeOutput", error_message=self._safe_error(str(exc)))

    def _cancel_and_join(
        self,
        running: QueuedJob,
        started_at: datetime,
        status: JobStatus,
        error_type: str,
        error_message: str,
        completed: threading.Event,
        worker: threading.Thread,
    ) -> JobResult | _PendingCleanup:
        """Bound cleanup before a terminal cancellation result can be persisted."""
        if completed.wait(timeout=self._cleanup_timeout_seconds):
            worker.join(timeout=self._cleanup_timeout_seconds)
            if not worker.is_alive():
                self._active_worker = None
                return self._result(running.job, started_at, status, error_type=error_type, error_message=error_message)
        return _PendingCleanup(running, started_at, status, error_type, error_message, worker)

    def _finish_pending_cleanup(self, pending: _PendingCleanup) -> JobResult:
        """Persist the deferred terminal result only after the handler is no longer alive."""
        if pending.worker.is_alive():
            raise RuntimeError("cannot finish cleanup while worker is alive")
        pending.worker.join(timeout=0)
        result = self._result(
            pending.running.job,
            pending.started_at,
            pending.status,
            error_type=pending.error_type,
            error_message=pending.error_message,
        )
        self._persist_terminal(pending.running, result)
        with self._run_lock:
            self._pending_cleanup = None
            self._active_worker = None
            self._state = RunnerState.IDLE
        return result

    def _persist_terminal(self, running: QueuedJob, result: JobResult) -> None:
        getattr(self._queue, "write_result")(result)
        getattr(self._queue, "mark_terminal")(running, result.status)

    @staticmethod
    def _safe_error(message: str) -> str:
        message = re.sub(r"(?i)\b(token|secret|password|authorization|credential|api[_-]?key)\s*[:=]\s*[^\s,;]+", "[REDACTED]", message)
        return redact_secrets(message, ())

    @staticmethod
    def _invoke(registered: RegisteredHandler, parameters: Any, token: CancellationToken) -> Any:
        handler = registered.handler
        try:
            inspect.signature(handler).bind(parameters, token)
        except TypeError:
            return handler(parameters)
        return handler(parameters, token)

    def _result(
        self,
        job: Any,
        started_at: datetime,
        status: JobStatus,
        *,
        output: dict[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> JobResult:
        finished_at = self._utc_now()
        return JobResult(
            job_id=job.job_id,
            machine_id=self._config.machine_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            action=job.action,
            duration_seconds=max(0.0, (finished_at - started_at).total_seconds()),
            output=output or {},
            error_type=error_type,
            error_message=error_message,
            agent_version=self._agent_version,
            source_commit=self._source_commit,
        )

    def _utc_now(self) -> datetime:
        value = self._now()
        return value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
