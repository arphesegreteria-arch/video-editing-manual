from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
import logging
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.models import AgentState, JobStatus


def _config(tmp_path: Path) -> AgentConfig:
    folders = {}
    for alias in ("incoming", "test_media", "workspace", "exports"):
        path = (tmp_path / alias).resolve()
        path.mkdir()
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


class ManualScheduler:
    """Controllable wait boundary: no wall-clock polling in lifecycle tests."""

    def __init__(self) -> None:
        self.delays: list[float] = []
        self._permits = threading.Semaphore(0)

    def wait(self, delay: float, stopped: threading.Event) -> bool:
        self.delays.append(delay)
        while not stopped.is_set():
            if self._permits.acquire(timeout=0.01):
                return stopped.is_set()
        return True

    def wake(self) -> None:
        self._permits.release()

    def advance(self) -> None:
        self._permits.release()


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RecordingQueue:
    def __init__(self) -> None:
        self.heartbeats = []

    def write_heartbeat(self, heartbeat) -> None:
        self.heartbeats.append(heartbeat)


class RecordingRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return None


class FakeResolve:
    def connect(self, timeout_seconds):
        return None

    def get_status(self):
        return {"status": "connected", "connected": True, "version": "19.1"}


def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached")


def _controller(tmp_path, *, runner=None, queue=None, scheduler=None, clock=None, cancel=None, resolve=None):
    from scripts.remote_agent.lifecycle import LifecycleController

    return LifecycleController(
        _config(tmp_path),
        queue or RecordingQueue(),
        runner or RecordingRunner(),
        resolve or FakeResolve(),
        agent_version="1.0",
        source_commit="abc123",
        logger=logging.getLogger("test.lifecycle"),
        scheduler=scheduler or ManualScheduler(),
        monotonic=clock or FakeClock(),
        cancellation_event=cancel,
    )


def test_polling_starts_only_after_visible_start_and_never_after_shutdown(tmp_path):
    runner = RecordingRunner()
    scheduler = ManualScheduler()
    controller = _controller(tmp_path, runner=runner, scheduler=scheduler)

    assert runner.calls == 0
    controller.start(ui_visible=True)
    _wait_for(lambda: runner.calls == 1)

    controller.shutdown()
    calls_at_shutdown = runner.calls
    scheduler.advance()
    time.sleep(0.03)

    assert runner.calls == calls_at_shutdown
    assert controller.state is AgentState.OFFLINE
    assert not controller.worker_alive


def test_start_refuses_hidden_ui(tmp_path):
    controller = _controller(tmp_path)

    with pytest.raises(RuntimeError, match="visible"):
        controller.start(ui_visible=False)

    assert controller.state is AgentState.OFFLINE


def test_pause_keeps_heartbeat_but_claims_no_new_work(tmp_path):
    runner = RecordingRunner()
    queue = RecordingQueue()
    scheduler = ManualScheduler()
    clock = FakeClock()
    controller = _controller(
        tmp_path, runner=runner, queue=queue, scheduler=scheduler, clock=clock
    )
    controller.start(ui_visible=True)
    _wait_for(lambda: runner.calls == 1 and len(queue.heartbeats) == 1)

    controller.pause()
    clock.advance(60)
    scheduler.advance()
    _wait_for(lambda: len(queue.heartbeats) == 2)

    assert runner.calls == 1
    assert controller.state is AgentState.PAUSED
    assert queue.heartbeats[-1].state is AgentState.PAUSED
    controller.shutdown()


def test_pause_closes_claim_gate_before_an_inflight_poll_returns(tmp_path):
    class GateAwareRunner:
        def __init__(self):
            self.listed = threading.Event()
            self.release = threading.Event()
            self.finished = threading.Event()
            self.claimed = False
            self.gate = True

        def add_execution_listener(self, _listener):
            return None

        def run_once(self):
            self.listed.set()
            assert self.release.wait(1)
            if self.gate:
                self.claimed = True
            self.finished.set()
            return None

        def stop_accepting_new_claims(self):
            self.gate = False

        def resume_accepting_new_claims(self):
            self.gate = True

    runner = GateAwareRunner()
    controller = _controller(tmp_path, runner=runner)
    controller.start(ui_visible=True)
    assert runner.listed.wait(1)

    controller.pause()
    runner.release.set()
    assert runner.finished.wait(1)

    assert runner.claimed is False
    assert runner.gate is False
    controller.resume()
    assert runner.gate is True
    controller.shutdown()


class BlockingRunner:
    def __init__(self, cancellation: threading.Event) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.cancellation = cancellation
        self.result_status = None

    def run_once(self):
        self.entered.set()
        while not self.release.wait(0.005):
            if self.cancellation.is_set():
                self.result_status = JobStatus.ABORTED
                return type("Result", (), {"job_id": "job-1", "status": JobStatus.ABORTED})()
        self.result_status = JobStatus.SUCCEEDED
        return type("Result", (), {"job_id": "job-1", "status": JobStatus.SUCCEEDED})()


def test_idle_close_stays_visible_until_worker_and_offline_heartbeat_finish(tmp_path):
    queue = RecordingQueue()
    controller = _controller(tmp_path, queue=queue)
    controller.start(ui_visible=True)
    _wait_for(lambda: len(queue.heartbeats) == 1)

    assert controller.request_close() is False
    controller.wait_until_stopped(timeout=1)

    assert controller.state is AgentState.OFFLINE
    assert queue.heartbeats[-1].state is AgentState.OFFLINE
    assert not controller.worker_alive


def test_slow_idle_poll_stays_online_and_can_close_without_a_job_prompt(tmp_path):
    """Catches a queue listing being mistaken for an active job during close."""
    class SlowPollingRunner:
        def __init__(self):
            self.entered = threading.Event()
            self.released = threading.Event()

        def add_execution_listener(self, _listener):
            # Queue I/O is deliberately not a running job.
            return None

        def run_once(self):
            self.entered.set()
            assert self.released.wait(1)
            return None

        def stop_accepting_new_claims(self):
            self.released.set()

    runner = SlowPollingRunner()
    controller = _controller(tmp_path, runner=runner)
    controller.start(ui_visible=True)
    assert runner.entered.wait(1)

    assert controller.state is AgentState.ONLINE
    assert controller.snapshot().current_job == "-"
    assert controller.request_close() is False
    controller.wait_until_stopped(timeout=1)
    assert controller.state is AgentState.OFFLINE


def test_idle_close_returns_while_a_queue_poll_is_still_blocked(tmp_path):
    """Catches an idle close freezing the UI for the queue HTTP timeout."""
    class UninterruptiblePollingRunner:
        def __init__(self):
            self.entered = threading.Event()
            self.release = threading.Event()

        def add_execution_listener(self, _listener):
            return None

        def stop_accepting_new_claims(self):
            return None

        def run_once(self):
            self.entered.set()
            assert self.release.wait(1)
            return None

    runner = UninterruptiblePollingRunner()
    controller = _controller(tmp_path, runner=runner)
    controller.start(ui_visible=True)
    assert runner.entered.wait(1)

    finished = threading.Event()
    closing = threading.Thread(target=lambda: (controller.request_close(), finished.set()))
    closing.start()
    try:
        assert finished.wait(0.1)
        assert controller.worker_alive
        assert "Closing" in controller.status_message
    finally:
        runner.release.set()
        closing.join(1)
        controller.wait_until_stopped(timeout=1)


def test_idle_close_atomically_blocks_a_claim_crossing_its_boundary(tmp_path):
    """An idle close owns the claim boundary even when RUNNING is delayed."""
    from scripts.remote_agent.github_queue import QueuedJob
    from scripts.remote_agent.handler_registry import HandlerRegistry
    from scripts.remote_agent.handlers.agent_status import PingParameters
    from scripts.remote_agent.job_runner import JobRunner
    from scripts.remote_agent.lifecycle import LifecycleController
    from scripts.remote_agent.logging_setup import configure_redacting_logger
    from scripts.remote_agent.models import Job
    from scripts.remote_agent.models import JobStatus as ModelJobStatus

    mark_running_entered = threading.Event()
    release_mark_running = threading.Event()
    release_active_notification = threading.Event()
    handler_called = threading.Event()

    queued_job = Job.model_validate(
        {
            "job_id": "close-boundary-job",
            "target_machine": "HOME_DEV",
            "action": "PING",
            "created_at": "2026-08-28T00:00:00Z",
            "requested_by": "arphe",
            "retryable": False,
            "timeout_seconds": 5,
            "parameters": {},
        }
    )

    class BoundaryQueue(RecordingQueue):
        def __init__(self) -> None:
            super().__init__()
            self.claims = 0
            self.running = 0
            self.results = []
            self.terminal = []

        def list_pending(self, _machine_id):
            return [QueuedJob(queued_job, "source-sha")]

        def claim(self, candidate, _sha, *, idempotent):
            self.claims += 1
            claimed = candidate.model_copy(
                update={
                    "status": ModelJobStatus.CLAIMED,
                    "claimed_by": candidate.target_machine,
                    "lease_expires_at": datetime(2026, 8, 29, tzinfo=timezone.utc),
                }
            )
            return QueuedJob(claimed, "claimed-sha")

        def mark_running(self, claimed):
            self.running += 1
            mark_running_entered.set()
            assert release_mark_running.wait(1)
            return QueuedJob(claimed.job.model_copy(update={"status": ModelJobStatus.RUNNING}), "running-sha")

        def write_result(self, result):
            self.results.append(result)

        def mark_terminal(self, running, status):
            terminal = QueuedJob(running.job.model_copy(update={"status": status}), "terminal-sha")
            self.terminal.append(terminal)
            return terminal

    class CoordinatedRunner(JobRunner):
        """Makes the old two-step lifecycle interleaving deterministic."""

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._close_handshake_used = False
            self._published_active = threading.Event()

        def hold_active_notification(self) -> None:
            def observe(state):
                if state.active:
                    self._published_active.set()
                    assert release_active_notification.wait(1)

            self.add_execution_listener(observe)

        def close_claim_gate_if_idle(self):
            self._close_handshake_used = True
            state = super().close_claim_gate_if_idle()
            release_mark_running.set()
            return state

        def stop_accepting_new_claims(self):
            super().stop_accepting_new_claims()
            release_mark_running.set()
            if not self._close_handshake_used:
                assert self._published_active.wait(1)

    registry = HandlerRegistry(["PING"])

    def handler(_parameters, _token):
        handler_called.set()
        return {"ran": True}

    registry.register("PING", PingParameters, handler)
    queue = BoundaryQueue()
    logger = configure_redacting_logger(
        logging.Logger("arphe.remote_agent.HOME_DEV"), [logging.StreamHandler(StringIO())]
    )
    agent_config = _config(tmp_path)
    runner = CoordinatedRunner(
        agent_config,
        queue,
        registry,
        agent_version="1.0",
        source_commit="abc123",
        logger=logger,
    )
    controller = LifecycleController(
        agent_config,
        queue,
        runner,
        FakeResolve(),
        agent_version="1.0",
        source_commit="abc123",
        logger=logging.getLogger("test.lifecycle"),
        scheduler=ManualScheduler(),
        monotonic=FakeClock(),
    )
    runner.hold_active_notification()
    controller.start(ui_visible=True)
    assert mark_running_entered.wait(1)

    try:
        assert controller.request_close() is False
        controller.wait_until_stopped(timeout=1)

        assert not handler_called.is_set()
        assert [result.status for result in queue.results] == [JobStatus.ABORTED]
        assert [item.job.status for item in queue.terminal] == [JobStatus.ABORTED]
        assert controller.state is AgentState.OFFLINE
        assert controller.snapshot().current_job == "-"
        assert all(heartbeat.current_job_id is None for heartbeat in queue.heartbeats)
    finally:
        release_mark_running.set()
        release_active_notification.set()
        controller.shutdown(timeout=1)


def test_heartbeat_uses_the_runner_current_job_id(tmp_path):
    """Catches heartbeats silently omitting a job id published by the runner."""
    from scripts.remote_agent.job_runner import RunnerExecutionState

    class StatePublishingRunner:
        def __init__(self):
            self._listener = None

        def add_execution_listener(self, listener):
            self._listener = listener

        def run_once(self):
            return None

    queue = RecordingQueue()
    runner = StatePublishingRunner()
    controller = _controller(tmp_path, runner=runner, queue=queue)

    runner._listener(RunnerExecutionState(active=True, current_job_id="job-current"))
    controller._send_heartbeat()

    assert queue.heartbeats[-1].state is AgentState.RUNNING
    assert queue.heartbeats[-1].current_job_id == "job-current"


def test_ui_snapshot_never_calls_a_blocking_resolve_api(tmp_path):
    class BlockingResolve:
        def __init__(self):
            self.called = threading.Event()
            self.release = threading.Event()

        def get_status(self):
            self.called.set()
            assert self.release.wait(1)
            return {"status": "connected", "connected": True}

    resolve = BlockingResolve()
    controller = _controller(tmp_path, resolve=resolve)
    finished = threading.Event()
    captured = {}

    thread = threading.Thread(
        target=lambda: (captured.setdefault("snapshot", controller.snapshot()), finished.set())
    )
    thread.start()
    try:
        assert finished.wait(0.1)
        assert not resolve.called.is_set()
        assert captured["snapshot"].resolve_state == "unavailable"
    finally:
        resolve.release.set()
        thread.join(1)


def test_start_agent_runs_directly_by_path_without_importing_the_ui(tmp_path):
    """Catches package imports failing when Task 8 launches the entry point by path."""
    entry_point = Path(__file__).parents[2] / "scripts" / "remote_agent" / "start_agent.py"

    result = subprocess.run(
        [sys.executable, str(entry_point), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--config" in result.stdout
    assert "--source-commit" not in result.stdout


def test_source_commit_is_detected_with_fixed_shell_free_git_invocation(tmp_path):
    from scripts.remote_agent.app import detect_source_commit

    calls = []
    exact = "a" * 40

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return type("Completed", (), {"returncode": 0, "stdout": exact + "\n", "stderr": ""})()

    assert detect_source_commit(tmp_path, run=run) == exact
    assert calls[0][0] == ["git", "rev-parse", "HEAD"]
    assert calls[0][1]["cwd"] == tmp_path
    assert calls[0][1]["shell"] is False


def test_source_commit_detection_fails_closed_on_unavailable_or_invalid_revision(tmp_path):
    from scripts.remote_agent.app import detect_source_commit

    def run(_argv, **_kwargs):
        return type("Completed", (), {"returncode": 1, "stdout": "unknown", "stderr": "failure"})()

    with pytest.raises(RuntimeError, match="source commit"):
        detect_source_commit(tmp_path, run=run)

    def missing_git(_argv, **_kwargs):
        raise FileNotFoundError("git")

    with pytest.raises(RuntimeError, match="source commit"):
        detect_source_commit(tmp_path, run=missing_git)


def test_finish_current_then_close_joins_worker(tmp_path):
    from scripts.remote_agent.lifecycle import CloseMode

    cancellation = threading.Event()
    runner = BlockingRunner(cancellation)
    controller = _controller(tmp_path, runner=runner, cancel=cancellation)
    controller.start(ui_visible=True)
    assert runner.entered.wait(1)

    assert controller.request_close(CloseMode.FINISH_CURRENT) is False
    assert not cancellation.is_set()
    runner.release.set()
    controller.wait_until_stopped(timeout=1)

    assert runner.result_status is JobStatus.SUCCEEDED
    assert controller.state is AgentState.OFFLINE
    assert not controller.worker_alive


def test_abort_current_then_close_requests_cooperative_abort_and_joins(tmp_path):
    from scripts.remote_agent.lifecycle import CloseMode

    cancellation = threading.Event()
    runner = BlockingRunner(cancellation)
    controller = _controller(tmp_path, runner=runner, cancel=cancellation)
    controller.start(ui_visible=True)
    assert runner.entered.wait(1)

    assert controller.request_close(CloseMode.ABORT_CURRENT) is False
    controller.wait_until_stopped(timeout=1)

    assert cancellation.is_set()
    assert runner.result_status is JobStatus.ABORTED
    assert controller.last_job_status is JobStatus.ABORTED
    assert controller.state is AgentState.OFFLINE
    assert not controller.worker_alive


def test_abort_close_waits_for_runner_cleanup_before_going_offline(tmp_path):
    from scripts.remote_agent.lifecycle import CloseMode, ThreadScheduler

    class DeferredAbortRunner:
        def __init__(self, cancellation):
            self.cancellation = cancellation
            self.entered = threading.Event()
            self.cleanup_release = threading.Event()
            self.state = type("State", (), {"value": "IDLE"})()

        def run_once(self):
            self.entered.set()
            if self.state.value == "IDLE":
                while not self.cancellation.wait(0.005):
                    pass
                self.state = type(
                    "State", (), {"value": "CANCELLATION_CLEANUP_PENDING"}
                )()
                return None
            if not self.cleanup_release.is_set():
                return None
            self.state = type("State", (), {"value": "IDLE"})()
            return type(
                "Result", (), {"job_id": "job-1", "status": JobStatus.ABORTED}
            )()

    cancellation = threading.Event()
    runner = DeferredAbortRunner(cancellation)
    controller = _controller(
        tmp_path,
        runner=runner,
        cancel=cancellation,
        scheduler=ThreadScheduler(),
        clock=time.monotonic,
    )
    controller.start(ui_visible=True)
    assert runner.entered.wait(1)

    controller.request_close(CloseMode.ABORT_CURRENT)
    _wait_for(lambda: runner.state.value == "CANCELLATION_CLEANUP_PENDING")
    time.sleep(0.03)
    assert controller.worker_alive
    assert controller.state is not AgentState.OFFLINE

    runner.cleanup_release.set()
    controller.wait_until_stopped(timeout=1)

    assert controller.last_job_status is JobStatus.ABORTED
    assert controller.state is AgentState.OFFLINE


def test_stop_after_current_goes_offline_without_another_poll(tmp_path):
    cancellation = threading.Event()
    runner = BlockingRunner(cancellation)
    controller = _controller(tmp_path, runner=runner, cancel=cancellation)
    controller.start(ui_visible=True)
    assert runner.entered.wait(1)

    controller.stop_after_current()
    runner.release.set()
    controller.wait_until_stopped(timeout=1)

    assert runner.result_status is JobStatus.SUCCEEDED
    assert controller.state is AgentState.OFFLINE


def test_github_outage_is_visible_and_backoff_is_capped(tmp_path):
    class FailingRunner:
        def __init__(self):
            self.calls = 0

        def run_once(self):
            self.calls += 1
            raise RuntimeError("GitHub unavailable")

    runner = FailingRunner()
    scheduler = ManualScheduler()
    clock = FakeClock()
    controller = _controller(tmp_path, runner=runner, scheduler=scheduler, clock=clock)
    controller.start(ui_visible=True)
    _wait_for(lambda: runner.calls == 1)
    assert controller.state is AgentState.ERROR
    assert "GitHub" in controller.status_message

    for expected in (60, 120, 240, 300, 300):
        clock.advance(expected)
        scheduler.advance()
        _wait_for(lambda: runner.calls >= 2)
        assert controller.retry_delay_seconds <= 300
    controller.shutdown()


def test_single_instance_lock_rejects_same_machine(tmp_path):
    from scripts.remote_agent.lifecycle import SingleInstanceError, SingleInstanceLock

    first = SingleInstanceLock("HOME_DEV", lock_directory=tmp_path)
    second = SingleInstanceLock("HOME_DEV", lock_directory=tmp_path)
    first.acquire()
    try:
        with pytest.raises(SingleInstanceError):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()


def test_production_builder_injects_configured_redacting_logger(monkeypatch, tmp_path):
    from scripts.remote_agent import app

    config = _config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    sentinel_logger = object()
    captured = {}

    monkeypatch.setattr(app, "configure_logging", lambda machine_id: sentinel_logger)
    monkeypatch.setattr(app, "CredentialStore", lambda _config: type("S", (), {"get_token": lambda self: "token"})())
    monkeypatch.setattr(app, "GitHubQueue", lambda *_args, **_kwargs: RecordingQueue())
    monkeypatch.setattr(app, "FileBroker", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(app, "ResolveManager", lambda *_args, **_kwargs: FakeResolve())
    monkeypatch.setattr(app, "register_handlers", lambda *_args, **_kwargs: None)

    class CapturingRunner:
        def __init__(self, *_args, **kwargs):
            captured.update(kwargs)

        def run_once(self):
            return None

    monkeypatch.setattr(app, "JobRunner", CapturingRunner)

    built = app.build_application(config_path, acquire_lock=False)

    assert captured["logger"] is sentinel_logger
    assert built.logger is sentinel_logger


def test_production_builder_checks_resolve_connection_before_ui_start(monkeypatch, tmp_path):
    from scripts.remote_agent import app

    config = _config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    calls = []

    class ConnectingResolve(FakeResolve):
        def connect(self, timeout_seconds):
            calls.append(timeout_seconds)
            return None

    monkeypatch.setattr(app, "configure_logging", lambda _machine_id: object())
    monkeypatch.setattr(app, "CredentialStore", lambda _config: type("S", (), {"get_token": lambda self: "token"})())
    monkeypatch.setattr(app, "GitHubQueue", lambda *_args, **_kwargs: RecordingQueue())
    monkeypatch.setattr(app, "FileBroker", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(app, "ResolveManager", lambda *_args, **_kwargs: ConnectingResolve())
    monkeypatch.setattr(app, "register_handlers", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "JobRunner", lambda *_args, **_kwargs: RecordingRunner())

    app.build_application(config_path, acquire_lock=False)

    assert calls == [5.0]


def test_window_model_exposes_required_operator_fields(tmp_path):
    from scripts.remote_agent.ui.main_window import MainWindowModel

    controller = _controller(tmp_path)
    model = MainWindowModel(controller)

    snapshot = model.snapshot()

    assert snapshot.machine_id == "HOME_DEV"
    assert snapshot.allowed_aliases == ("incoming", "test_media", "workspace", "exports")
    assert snapshot.agent_state is AgentState.OFFLINE
    assert snapshot.resolve_state
    assert snapshot.current_job == "-"
    assert snapshot.last_job == "-"
    assert isinstance(snapshot.recent_logs, tuple)


def test_window_run_stops_the_agent_when_tk_mainloop_exits_without_a_close_event():
    """The visible window is the lifetime boundary for all agent activity."""
    from scripts.remote_agent.ui.main_window import MainWindow

    class RootThatExits:
        def update_idletasks(self):
            pass

        def deiconify(self):
            pass

        def winfo_viewable(self):
            return True

        def mainloop(self):
            return None

    class Controller:
        def __init__(self):
            self.start_calls = []
            self.shutdown_calls = 0

        def start(self, *, ui_visible):
            self.start_calls.append(ui_visible)

        def shutdown(self):
            self.shutdown_calls += 1

    window = object.__new__(MainWindow)
    window._root = RootThatExits()
    window._controller = Controller()
    window._refresh = lambda: None

    window.run()

    assert window._controller.start_calls == [True]
    assert window._controller.shutdown_calls == 1


def test_window_realizes_itself_after_deiconify_before_opening_the_polling_gate():
    """A merely requested window is not enough: Tk must have mapped it first."""
    from scripts.remote_agent.ui.main_window import MainWindow

    class RootThatMapsOnIdle:
        def __init__(self):
            self.deiconified = False
            self.mapped = False

        def update_idletasks(self):
            if self.deiconified:
                self.mapped = True

        def deiconify(self):
            self.deiconified = True

        def winfo_viewable(self):
            return self.mapped

        def mainloop(self):
            return None

    class Controller:
        def __init__(self):
            self.visible_at_start = None

        def start(self, *, ui_visible):
            self.visible_at_start = ui_visible

        def shutdown(self):
            pass

    window = object.__new__(MainWindow)
    window._root = RootThatMapsOnIdle()
    window._controller = Controller()
    window._refresh = lambda: None

    window.run()

    assert window._controller.visible_at_start is True
