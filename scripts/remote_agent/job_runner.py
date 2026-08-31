"""Single-job, allowlist-first execution for the remote agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import inspect
import logging
import threading
import time
from typing import Any

from scripts.remote_agent.cancellation import CancellationToken
from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.github_queue import QueuedJob
from scripts.remote_agent.handler_registry import HandlerRegistry, RegisteredHandler
from scripts.remote_agent.logging_setup import require_redacting_logger
from scripts.remote_agent.models import JobResult, JobStatus


_HANDLER_FAILURE_TYPE = "HandlerFailure"
_HANDLER_FAILURE_MESSAGE = "handler failed; see redacted local logs"


class RunnerState(str, Enum):
    """Externally visible local safety state for the one-job gate."""

    IDLE = "IDLE"
    CANCELLATION_CLEANUP_PENDING = "CANCELLATION_CLEANUP_PENDING"


@dataclass(frozen=True)
class RunnerExecutionState:
    """The one job that has crossed the remote ``RUNNING`` transition."""

    active: bool
    current_job_id: str | None

    def __post_init__(self) -> None:
        if self.active != (self.current_job_id is not None):
            raise ValueError("active runner state must have exactly one current job id")


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
        logger: logging.Logger,
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
        self._logger = require_redacting_logger(logger, config.machine_id)
        self._active_worker: threading.Thread | None = None
        self._pending_cleanup: _PendingCleanup | None = None
        self._state = RunnerState.IDLE
        self._run_lock = threading.Lock()
        self._reserved = False
        self._claims_allowed = True
        self._execution_state = RunnerExecutionState(active=False, current_job_id=None)
        self._execution_listeners: list[Callable[[RunnerExecutionState], None]] = []

    @property
    def state(self) -> RunnerState:
        """Return whether a timed-out/cancelled handler still owns the job gate."""
        with self._run_lock:
            return self._state

    @property
    def execution_state(self) -> RunnerExecutionState:
        """Return a thread-safe snapshot of the actual remote running job."""
        with self._run_lock:
            return self._execution_state

    @property
    def current_job_id(self) -> str | None:
        """Return the job id only after its document is marked ``RUNNING``."""
        return self.execution_state.current_job_id

    def add_execution_listener(self, listener: Callable[[RunnerExecutionState], None]) -> None:
        """Notify a lifecycle owner when a job enters or leaves execution."""
        with self._run_lock:
            self._execution_listeners.append(listener)

    def stop_accepting_new_claims(self) -> None:
        """Close the claim gate without waiting for an in-flight queue request."""
        with self._run_lock:
            self._claims_allowed = False

    def close_claim_gate_if_idle(self) -> RunnerExecutionState:
        """Atomically close new claims unless a job was already executing.

        The returned snapshot and gate update share ``_run_lock`` with the
        claimed-job activation transition.  A lifecycle owner can therefore
        distinguish a genuinely active job from a claim that is still crossing
        the queue boundary without reopening the gate.
        """
        with self._run_lock:
            state = self._execution_state
            if not state.active:
                self._claims_allowed = False
            return state

    def resume_accepting_new_claims(self) -> None:
        """Reopen the claim gate when an operator cancels a close request."""
        with self._run_lock:
            self._claims_allowed = True

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
                if not self._claims_are_allowed():
                    return None
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
        if not self._activate_claimed_job_if_allowed(job.job_id):
            result = self._result(
                job,
                started_at,
                JobStatus.ABORTED,
                error_type="Cancelled",
                error_message="cancellation requested before handler start",
            )
            self._persist_terminal(running, result)
            return result
        cleanup_pending = False
        try:
            if self._cancellation_requested():
                token.cancel()
                result = self._result(
                    job,
                    started_at,
                    JobStatus.ABORTED,
                    error_type="Cancelled",
                    error_message="cancellation requested before handler start",
                )
            else:
                result = self._execute(running, registered, parameters, token, started_at)
            if isinstance(result, _PendingCleanup):
                cleanup_pending = True
                with self._run_lock:
                    self._pending_cleanup = result
                    self._state = RunnerState.CANCELLATION_CLEANUP_PENDING
                return None
            self._persist_terminal(running, result)
            return result
        finally:
            if not cleanup_pending:
                self._set_execution_state(RunnerExecutionState(active=False, current_job_id=None))

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
            self._log_handler_failure(job, exception)
            return self._result(
                job,
                started_at,
                JobStatus.FAILED,
                error_type=_HANDLER_FAILURE_TYPE,
                error_message=_HANDLER_FAILURE_MESSAGE,
            )
        output = outcome.get("output")
        if not isinstance(output, dict):
            return self._result(job, started_at, JobStatus.FAILED, error_type="HandlerContractError", error_message="handler output must be a JSON object")
        try:
            return self._result(job, started_at, JobStatus.SUCCEEDED, output=output)
        except ValueError:
            return self._result(job, started_at, JobStatus.FAILED, error_type="UnsafeOutput", error_message="handler output was rejected")

    def _log_handler_failure(self, job: Any, exception: BaseException) -> None:
        """Emit raw failure detail only while the injected logger remains safe."""
        try:
            logger = require_redacting_logger(self._logger, self._config.machine_id)
        except ValueError:
            return
        logger.error(
            "remote handler execution failed for job_id=%s action=%s",
            job.job_id,
            job.action,
            exc_info=(type(exception), exception, exception.__traceback__),
        )

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
        self._set_execution_state(RunnerExecutionState(active=False, current_job_id=None))
        return result

    def _claims_are_allowed(self) -> bool:
        with self._run_lock:
            return self._claims_allowed

    def _activate_claimed_job_if_allowed(self, job_id: str) -> bool:
        """Publish a claimed job only when the close gate is still open."""
        state = RunnerExecutionState(active=True, current_job_id=job_id)
        with self._run_lock:
            if not self._claims_allowed:
                return False
            if self._execution_state == state:
                return True
            self._execution_state = state
            listeners = tuple(self._execution_listeners)
        self._notify_execution_listeners(state, listeners)
        return True

    def _set_execution_state(self, state: RunnerExecutionState) -> None:
        with self._run_lock:
            if self._execution_state == state:
                return
            self._execution_state = state
            listeners = tuple(self._execution_listeners)
        self._notify_execution_listeners(state, listeners)

    def _notify_execution_listeners(
        self, state: RunnerExecutionState, listeners: tuple[Callable[[RunnerExecutionState], None], ...]
    ) -> None:
        for listener in listeners:
            try:
                listener(state)
            except Exception:
                self._logger.exception("remote runner execution-state listener failed")

    def _persist_terminal(self, running: QueuedJob, result: JobResult) -> None:
        getattr(self._queue, "write_result")(result)
        getattr(self._queue, "mark_terminal")(running, result.status)

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
        common = {
            "job_id": job.job_id,
            "machine_id": self._config.machine_id,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "action": job.action,
            "duration_seconds": max(0.0, (finished_at - started_at).total_seconds()),
            "agent_version": self._agent_version,
            "source_commit": self._source_commit,
        }
        try:
            return JobResult(
                **common,
                output=output or {},
                error_type=error_type,
                error_message=error_message,
            )
        except ValueError:
            return JobResult(
                **common,
                output={},
                error_type="ResultConstructionError",
                error_message="handler result could not be safely serialized",
            )

    def _utc_now(self) -> datetime:
        value = self._now()
        return value.astimezone(timezone.utc) if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
