"""Visible-only application lifecycle for the ARPHE Remote Agent."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import logging
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Protocol

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.models import AgentState, JobStatus, MachineHeartbeat


HEARTBEAT_INTERVAL_SECONDS = 60.0
MAX_RETRY_SECONDS = 300.0


class Scheduler(Protocol):
    def wait(self, delay: float, stopped: threading.Event) -> bool: ...

    def wake(self) -> None: ...


class ThreadScheduler:
    """Interruptible real-time scheduler used by the desktop application."""

    def __init__(self) -> None:
        self._wake = threading.Event()

    def wait(self, delay: float, stopped: threading.Event) -> bool:
        deadline = time.monotonic() + max(0.0, delay)
        while not stopped.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self._wake.wait(remaining):
                self._wake.clear()
                return stopped.is_set()
        return True

    def wake(self) -> None:
        self._wake.set()


class CloseMode(str, Enum):
    FINISH_CURRENT = "finish_current"
    ABORT_CURRENT = "abort_current"


class SingleInstanceError(RuntimeError):
    pass


_HELD_INSTANCE_KEYS: set[str] = set()
_HELD_INSTANCE_KEYS_LOCK = threading.Lock()


class SingleInstanceLock:
    """An OS-backed, per-machine lock with a same-process guard for tests."""

    def __init__(self, machine_id: str, *, lock_directory: Path | None = None) -> None:
        base = lock_directory or Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        ) / "ARPHE" / "RemoteAgent"
        self._path = base / f"{machine_id}.lock"
        self._key = str(self._path.resolve()).casefold()
        self._file = None

    def acquire(self) -> None:
        with _HELD_INSTANCE_KEYS_LOCK:
            if self._key in _HELD_INSTANCE_KEYS:
                raise SingleInstanceError("the remote agent is already running for this machine")
            _HELD_INSTANCE_KEYS.add(self._key)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            handle = self._path.open("a+b")
            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, IOError) as exc:
                handle.close()
                raise SingleInstanceError(
                    "the remote agent is already running for this machine"
                ) from exc
            self._file = handle
        except BaseException:
            with _HELD_INSTANCE_KEYS_LOCK:
                _HELD_INSTANCE_KEYS.discard(self._key)
            raise

    def release(self) -> None:
        handle, self._file = self._file, None
        if handle is not None:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
        with _HELD_INSTANCE_KEYS_LOCK:
            _HELD_INSTANCE_KEYS.discard(self._key)

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.release()


@dataclass(frozen=True)
class LifecycleSnapshot:
    machine_id: str
    state: AgentState
    status_message: str
    resolve_state: str
    allowed_aliases: tuple[str, ...]
    current_job: str
    last_job: str
    last_job_status: JobStatus | None
    recent_logs: tuple[str, ...]


class LifecycleController:
    """Own polling, heartbeats, pause and process-safe shutdown."""

    def __init__(
        self,
        config: AgentConfig,
        queue: object,
        runner: object,
        resolve_manager: object,
        *,
        agent_version: str,
        source_commit: str,
        logger: logging.Logger,
        scheduler: Scheduler | None = None,
        monotonic=time.monotonic,
        now=None,
        cancellation_event: threading.Event | None = None,
        instance_lock: SingleInstanceLock | None = None,
    ) -> None:
        self.config = config
        self._queue = queue
        self._runner = runner
        self._resolve = resolve_manager
        self._agent_version = agent_version
        self._source_commit = source_commit
        self._logger = logger
        self._scheduler = scheduler or ThreadScheduler()
        self._monotonic = monotonic
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._cancellation = cancellation_event or threading.Event()
        self._instance_lock = instance_lock
        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self._worker: threading.Thread | None = None
        self._state = AgentState.OFFLINE
        self._status_message = "Offline"
        self._paused = False
        self._poll_in_progress = False
        self._job_active = False
        self._cleanup_pending = False
        self._stop_requested = threading.Event()
        self._stop_after_current = False
        self._closing = False
        self._current_job = "-"
        self._last_job = "-"
        self._last_job_status: JobStatus | None = None
        self._recent_logs: deque[str] = deque(maxlen=100)
        self._retry_delay = float(config.poll_interval_seconds)
        listener = getattr(runner, "add_execution_listener", None)
        self._runner_reports_execution = callable(listener)
        if self._runner_reports_execution:
            listener(self._on_runner_execution_state)

    @property
    def state(self) -> AgentState:
        with self._lock:
            return self._state

    @property
    def status_message(self) -> str:
        with self._lock:
            return self._status_message

    @property
    def retry_delay_seconds(self) -> float:
        with self._lock:
            return self._retry_delay

    @property
    def worker_alive(self) -> bool:
        worker = self._worker
        return bool(worker and worker.is_alive())

    @property
    def last_job_status(self) -> JobStatus | None:
        with self._lock:
            return self._last_job_status

    def start(self, *, ui_visible: bool) -> None:
        if not ui_visible:
            raise RuntimeError("polling requires a visible UI")
        with self._lock:
            if self._worker is not None:
                raise RuntimeError("lifecycle has already been started")
            self._state = AgentState.ONLINE
            self._status_message = "Online"
            self._record("Agent online")
            worker = threading.Thread(
                target=self._run,
                name=f"arphe-lifecycle-{self.config.machine_id}",
                daemon=False,
            )
            self._worker = worker
        worker.start()

    def pause(self) -> None:
        with self._lock:
            if self._state is AgentState.OFFLINE:
                return
            self._paused = True
            if not self._job_active:
                self._state = AgentState.PAUSED
                self._status_message = "Paused - no new jobs"
            self._record("New job claims paused")
        self._scheduler.wake()

    def resume(self) -> None:
        with self._lock:
            if self._state is AgentState.OFFLINE:
                return
            self._paused = False
            if not self._job_active:
                self._state = AgentState.ONLINE
                self._status_message = "Online"
            self._record("Job claims resumed")
        self._scheduler.wake()

    def stop_after_current(self) -> None:
        with self._lock:
            if self._state is AgentState.OFFLINE:
                return
            self._stop_after_current = True
            active = self._job_active
            self._status_message = "Stopping after current job"
            self._record("Stop after current job requested")
        if active:
            self._scheduler.wake()
        else:
            self.shutdown()

    def request_close(self, mode: CloseMode | None = None) -> bool:
        """Return true when the caller may destroy the window immediately."""
        with self._lock:
            active = self._job_active
        if active and mode is None:
            raise ValueError("an active job requires an explicit close mode")
        self._stop_new_claims()
        with self._lock:
            active = self._job_active
        if not active:
            self._begin_shutdown()
            return True
        if mode is None:
            self._resume_new_claims()
            raise ValueError("an active job requires an explicit close mode")
        with self._lock:
            self._closing = True
            self._stop_after_current = True
            if mode is CloseMode.ABORT_CURRENT:
                self._status_message = "Aborting current job, then closing"
                self._record("Cooperative abort requested")
                self._cancellation.set()
            else:
                self._status_message = "Finishing current job, then closing"
                self._record("Finish current job before close requested")
        self._scheduler.wake()
        return False

    def shutdown(self, *, timeout: float | None = None) -> None:
        """Stop all work and join the non-daemon lifecycle worker before returning."""
        self._begin_shutdown()
        worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout)
            if worker.is_alive():
                raise TimeoutError("remote agent worker did not stop")

    def _begin_shutdown(self) -> None:
        """Close the gates immediately; joining is deliberately a separate boundary."""
        self._stop_new_claims()
        with self._lock:
            self._cancellation.set()
            self._stop_requested.set()
        self._scheduler.wake()

    def wait_until_stopped(self, timeout: float | None = None) -> None:
        if not self._stopped.wait(timeout):
            raise TimeoutError("remote agent did not stop")
        worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=0)

    def snapshot(self) -> LifecycleSnapshot:
        with self._lock:
            resolve_status = self._safe_resolve_status()
            return LifecycleSnapshot(
                machine_id=self.config.machine_id,
                state=self._state,
                status_message=self._status_message,
                resolve_state=resolve_status,
                allowed_aliases=self.config.folders.aliases(),
                current_job=self._current_job,
                last_job=self._last_job,
                last_job_status=self._last_job_status,
                recent_logs=tuple(self._recent_logs),
            )

    def _run(self) -> None:
        next_poll = self._monotonic()
        next_heartbeat = next_poll
        try:
            while not self._stop_requested.is_set():
                now = self._monotonic()
                if now >= next_heartbeat:
                    if not self._send_heartbeat():
                        next_poll = now + self._register_outage()
                    next_heartbeat = now + HEARTBEAT_INTERVAL_SECONDS

                with self._lock:
                    may_poll = not self._paused and (
                        not self._stop_after_current or self._cleanup_pending
                    )
                if may_poll and now >= next_poll and not self._stop_requested.is_set():
                    try:
                        cleanup_pending = self._run_one_job()
                    except Exception:
                        next_poll = self._monotonic() + self._register_outage()
                    else:
                        if cleanup_pending:
                            next_poll = self._monotonic() + 0.1
                        else:
                            with self._lock:
                                self._retry_delay = float(self.config.poll_interval_seconds)
                            next_poll = self._monotonic() + self.config.poll_interval_seconds

                with self._lock:
                    stop_after = self._stop_after_current and not self._job_active
                if stop_after:
                    self._stop_requested.set()
                    break

                now = self._monotonic()
                deadlines = [next_heartbeat]
                with self._lock:
                    if not self._paused or self._cleanup_pending:
                        deadlines.append(next_poll)
                self._scheduler.wait(max(0.0, min(deadlines) - now), self._stop_requested)
        finally:
            self._finalize()

    def _run_one_job(self) -> bool:
        with self._lock:
            self._poll_in_progress = True
            if not self._runner_reports_execution:
                self._job_active = True
                self._state = AgentState.RUNNING
                self._current_job = "Processing queue job"
                self._status_message = "Running one allowlisted job"
        cleanup_pending = False
        try:
            result = getattr(self._runner, "run_once")()
            runner_state = getattr(getattr(self._runner, "state", None), "value", None)
            cleanup_pending = runner_state == "CANCELLATION_CLEANUP_PENDING"
            with self._lock:
                self._cleanup_pending = cleanup_pending
                if cleanup_pending:
                    self._status_message = "Waiting for cooperative handler cleanup"
            if result is not None:
                with self._lock:
                    self._last_job = str(getattr(result, "job_id", "-"))
                    self._last_job_status = getattr(result, "status", None)
                    self._record(f"Job {self._last_job}: {self._last_job_status}")
        finally:
            with self._lock:
                self._poll_in_progress = False
                if not cleanup_pending:
                    if not self._runner_reports_execution:
                        self._job_active = False
                    self._cleanup_pending = False
                    if not self._runner_reports_execution:
                        self._current_job = "-"
                if not self._stop_after_current and not cleanup_pending and not self._job_active:
                    self._state = AgentState.PAUSED if self._paused else AgentState.ONLINE
                    self._status_message = "Paused - no new jobs" if self._paused else "Online"
        return cleanup_pending

    def _on_runner_execution_state(self, execution: object) -> None:
        """Mirror only a confirmed remote RUNNING job into UI-visible lifecycle state."""
        active = bool(getattr(execution, "active", False))
        current = getattr(execution, "current_job_id", None)
        current_job = current if isinstance(current, str) and current else "-"
        with self._lock:
            self._job_active = active
            self._current_job = current_job
            if active:
                self._state = AgentState.RUNNING
                self._status_message = "Running one allowlisted job"
            elif not self._cleanup_pending and not self._stop_after_current:
                self._state = AgentState.PAUSED if self._paused else AgentState.ONLINE
                self._status_message = "Paused - no new jobs" if self._paused else "Online"

    def _stop_new_claims(self) -> None:
        stopper = getattr(self._runner, "stop_accepting_new_claims", None)
        if callable(stopper):
            stopper()

    def _resume_new_claims(self) -> None:
        resumer = getattr(self._runner, "resume_accepting_new_claims", None)
        if callable(resumer):
            resumer()

    def _register_outage(self) -> float:
        with self._lock:
            current = max(float(self.config.poll_interval_seconds), self._retry_delay)
            self._retry_delay = min(MAX_RETRY_SECONDS, current * 2)
            self._state = AgentState.ERROR
            self._status_message = "OFFLINE - GitHub unavailable"
            self._record("GitHub unavailable; retry delayed")
            return self._retry_delay

    def _send_heartbeat(self, state: AgentState | None = None) -> bool:
        resolve_status = self._resolve_status()
        with self._lock:
            current_state = state or self._state
            current_job = None if self._current_job in {"-", "Processing queue job"} else self._current_job
        heartbeat = MachineHeartbeat(
            machine_id=self.config.machine_id,
            state=current_state,
            last_heartbeat_at=self._utc_now(),
            agent_version=self._agent_version,
            source_commit=self._source_commit,
            resolve_connected=bool(resolve_status.get("connected", False)),
            resolve_version=self._safe_optional_text(resolve_status.get("version")),
            current_job_id=current_job,
            workspace_free_bytes=self._free_bytes(self.config.folders.workspace),
            exports_free_bytes=self._free_bytes(self.config.folders.exports),
        )
        try:
            getattr(self._queue, "write_heartbeat")(heartbeat)
            return True
        except Exception:
            self._logger.error("GitHub heartbeat failed", exc_info=True)
            return False

    def _finalize(self) -> None:
        try:
            self._send_heartbeat(AgentState.OFFLINE)
        finally:
            with self._lock:
                self._state = AgentState.OFFLINE
                self._status_message = "Offline"
                self._job_active = False
                self._cleanup_pending = False
                self._current_job = "-"
                self._record("Agent offline")
            if self._instance_lock is not None:
                self._instance_lock.release()
            self._stopped.set()

    def _resolve_status(self) -> dict:
        try:
            status = getattr(self._resolve, "get_status")()
            return status if isinstance(status, dict) else {}
        except Exception:
            return {}

    def _safe_resolve_status(self) -> str:
        status = self._resolve_status().get("status", "unavailable")
        return str(getattr(status, "value", status))

    @staticmethod
    def _safe_optional_text(value: object) -> str | None:
        return str(value)[:128] if value is not None else None

    @staticmethod
    def _free_bytes(path: Path) -> int | None:
        try:
            return shutil.disk_usage(path).free
        except OSError:
            return None

    def _utc_now(self) -> datetime:
        value = self._now()
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _record(self, message: str) -> None:
        self._recent_logs.append(message[:500])
