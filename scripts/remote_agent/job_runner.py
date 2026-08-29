"""Single-job, allowlist-first execution for the remote agent."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import inspect
import re
import threading
import time
from typing import Any

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.github_queue import QueuedJob
from scripts.remote_agent.handler_registry import HandlerRegistry, RegisteredHandler
from scripts.remote_agent.logging_setup import redact_secrets
from scripts.remote_agent.models import JobResult, JobStatus


class CancellationToken:
    """A cooperative cancellation signal supplied to two-argument handlers."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


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
    ) -> None:
        self._config = config
        self._queue = queue
        self._registry = registry
        self._agent_version = agent_version
        self._source_commit = source_commit
        self._cancellation_requested = cancellation_requested or (lambda: False)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic
        self._active_worker: threading.Thread | None = None
        self._run_lock = threading.Lock()
        self._reserved = False

    def run_once(self) -> JobResult | None:
        """Run one pending job, or return ``None`` when nothing is safely runnable."""
        with self._run_lock:
            if self._reserved or (self._active_worker is not None and self._active_worker.is_alive()):
                return None
            self._active_worker = None
            self._reserved = True
        try:
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

    def _claim_and_execute(self, candidate: QueuedJob, registered: RegisteredHandler, parameters: Any) -> JobResult:
        claimed = getattr(self._queue, "claim")(candidate.job, candidate.sha, idempotent=registered.idempotent)
        running = getattr(self._queue, "mark_running")(claimed)
        job = running.job
        started_at = self._utc_now()
        token = CancellationToken()

        if self._cancellation_requested():
            token.cancel()
            result = self._result(job, started_at, JobStatus.ABORTED, error_type="Cancelled", error_message="cancellation requested before handler start")
        else:
            result = self._execute(job, registered, parameters, token, started_at)
        getattr(self._queue, "write_result")(result)
        getattr(self._queue, "mark_terminal")(running, result.status)
        return result

    def _execute(
        self, job: Any, registered: RegisteredHandler, parameters: Any, token: CancellationToken, started_at: datetime
    ) -> JobResult:
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
        while not completed.wait(timeout=0.05):
            if self._cancellation_requested():
                token.cancel()
                return self._result(job, started_at, JobStatus.ABORTED, error_type="Cancelled", error_message="cancellation requested while handler was running")
            if self._monotonic() >= deadline:
                token.cancel()
                return self._result(job, started_at, JobStatus.FAILED_TIMEOUT, error_type="Timeout", error_message="handler exceeded its configured timeout")

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
