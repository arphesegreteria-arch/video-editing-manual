from __future__ import annotations

from pathlib import Path
import threading

import pytest

from scripts.remote_agent.config import ResolveConfig
from scripts.remote_agent.cancellation import CancellationToken
from scripts.remote_agent.resolve_manager import (
    ResolveManager,
    ResolveProcessState,
    ResolveStatus,
    _load_resolve_script_module,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class SequenceClock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class FakeProject:
    def __init__(self, name: str, timeline_name: str = "Audit timeline") -> None:
        self._name = name
        self._timeline_name = timeline_name

    def GetName(self) -> str:
        return self._name

    def GetCurrentTimeline(self):
        return type("Timeline", (), {"GetName": lambda _: self._timeline_name})()


class FakeResolve:
    def __init__(self, project_name: str = "ARPHE_TEST") -> None:
        self._project = FakeProject(project_name)

    def GetProjectManager(self):
        return type(
            "ProjectManager", (), {"GetCurrentProject": lambda _: self._project}
        )()

    def GetVersion(self):
        return [19, 1, 2, 3, "Studio"]


def call_api_immediately(api_connector, timeout_seconds: float):
    return api_connector()


def resolve_process(
    executable_path: Path, *, pid: int = 101, create_time: float = 1000.0
) -> dict[str, str | int | float]:
    return {
        "exe": str(executable_path),
        "pid": pid,
        "create_time": create_time,
    }


def resolve_config(tmp_path: Path, *, launch_if_needed: bool = False) -> ResolveConfig:
    return ResolveConfig(
        executable_path=tmp_path / "DaVinci Resolve" / "Resolve.exe",
        launch_if_needed=launch_if_needed,
    )


def test_process_state_reports_not_running_without_connecting_to_a_live_api(tmp_path) -> None:
    """Catches status probing an API when the configured Resolve process is absent."""
    api_calls = 0

    def unavailable_api():
        nonlocal api_calls
        api_calls += 1
        return None

    manager = ResolveManager(
        resolve_config(tmp_path),
        process_executables=lambda: [],
        api_connector=unavailable_api,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: pytest.fail(f"unexpected sleep: {seconds}"),
    )

    assert manager.get_process_state() is ResolveProcessState.NOT_RUNNING
    assert manager.get_status()["status"] == ResolveStatus.NOT_RUNNING
    assert api_calls == 0


def test_process_state_requires_the_exact_configured_executable_identity(tmp_path) -> None:
    """Catches treating another Resolve.exe, including a job-supplied path, as configured Resolve."""
    config = resolve_config(tmp_path)
    job_supplied_path = tmp_path / "untrusted-job" / "Resolve.exe"
    manager = ResolveManager(
        config,
        process_executables=lambda: [job_supplied_path],
        api_connector=lambda: pytest.fail("wrong executable must not connect"),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: pytest.fail(f"unexpected sleep: {seconds}"),
    )

    assert manager.get_process_state() is ResolveProcessState.WRONG_EXECUTABLE
    assert manager.get_status()["status"] == ResolveStatus.WRONG_EXECUTABLE


def test_process_state_fails_closed_when_configured_and_wrong_resolve_are_both_running(
    tmp_path,
) -> None:
    """Catches accepting a scripting API when more than one Resolve executable is present."""
    config = resolve_config(tmp_path)
    manager = ResolveManager(
        config,
        process_executables=lambda: [
            config.executable_path,
            tmp_path / "other-install" / "Resolve.exe",
        ],
        api_connector=lambda: pytest.fail("ambiguous process identity must not connect"),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: pytest.fail(f"unexpected sleep: {seconds}"),
    )

    assert manager.get_process_state() is ResolveProcessState.WRONG_EXECUTABLE
    assert manager.get_status()["status"] == ResolveStatus.WRONG_EXECUTABLE


def test_process_state_fails_closed_when_configured_executable_has_multiple_processes(
    tmp_path,
) -> None:
    """Catches accepting an ambiguous pair of processes from the configured installation."""
    config = resolve_config(tmp_path)
    manager = ResolveManager(
        config,
        process_executables=lambda: [
            resolve_process(config.executable_path, pid=101, create_time=1000.0),
            resolve_process(config.executable_path, pid=102, create_time=1001.0),
        ],
        api_connector=lambda: pytest.fail("ambiguous configured processes must not connect"),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: pytest.fail(f"unexpected sleep: {seconds}"),
    )

    assert manager.get_process_state() is ResolveProcessState.WRONG_EXECUTABLE
    assert manager.get_status()["status"] == ResolveStatus.WRONG_EXECUTABLE


def test_process_state_accepts_a_case_insensitive_match_for_configured_executable(tmp_path) -> None:
    """Catches false negatives when Windows reports the configured executable with different casing."""
    config = resolve_config(tmp_path)
    differently_cased = Path(str(config.executable_path).swapcase())
    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(differently_cased)],
        api_connector=lambda: None,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: pytest.fail(f"unexpected sleep: {seconds}"),
    )

    assert manager.get_process_state() is ResolveProcessState.RUNNING


def test_launch_only_uses_the_local_configured_executable_when_allowed(tmp_path) -> None:
    """Catches a launcher receiving any path other than the local ResolveConfig executable."""
    config = resolve_config(tmp_path, launch_if_needed=True)
    launched: list[Path] = []
    manager = ResolveManager(
        config,
        process_executables=lambda: [],
        api_connector=lambda: None,
        launcher=launched.append,
        clock=FakeClock(),
        sleep=lambda seconds: None,
        api_call_runner=call_api_immediately,
    )

    assert manager.launch_if_allowed() is True
    assert launched == [config.executable_path]


def test_launch_refuses_when_local_configuration_disables_it(tmp_path) -> None:
    """Catches a remote job being able to start Resolve despite local launch policy."""
    manager = ResolveManager(
        resolve_config(tmp_path, launch_if_needed=False),
        process_executables=lambda: [],
        api_connector=lambda: None,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: None,
    )

    assert manager.launch_if_allowed() is False


def test_launch_refuses_when_another_resolve_executable_is_running(tmp_path) -> None:
    """Catches starting a second Resolve while the manager reports a wrong executable."""
    config = resolve_config(tmp_path, launch_if_needed=True)
    manager = ResolveManager(
        config,
        process_executables=lambda: [tmp_path / "other-install" / "Resolve.exe"],
        api_connector=lambda: None,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: None,
    )

    assert manager.launch_if_allowed() is False


def test_connect_waits_only_until_the_bounded_timeout_when_running_api_is_unavailable(
    tmp_path,
) -> None:
    """Catches an unavailable scripting API causing an unbounded connection wait."""
    config = resolve_config(tmp_path)
    clock = FakeClock()
    api_attempts = 0

    def unavailable_api():
        nonlocal api_attempts
        api_attempts += 1
        return None

    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=unavailable_api,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=clock,
        sleep=clock.sleep,
        api_call_runner=call_api_immediately,
    )

    assert manager.connect(timeout_seconds=1.0) is None
    assert 1.0 <= clock.now <= 1.25
    assert api_attempts >= 2
    assert manager.get_status()["status"] == ResolveStatus.RUNNING_UNAVAILABLE


def test_connect_does_not_pass_a_negative_sleep_when_the_clock_crosses_deadline(
    tmp_path,
) -> None:
    """Catches a clock race turning the bounded wait into an invalid negative sleep."""
    config = resolve_config(tmp_path)
    sleeps: list[float] = []
    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=lambda: None,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=SequenceClock([0.0, 0.5, 1.1]),
        sleep=sleeps.append,
        api_call_runner=call_api_immediately,
    )

    assert manager.connect(timeout_seconds=1.0) is None
    assert sleeps == []


def test_connect_returns_by_deadline_when_the_synchronous_connector_blocks(tmp_path) -> None:
    """Catches a blocking Resolve scripting call holding the agent past its timeout."""
    config = resolve_config(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    result: list[object | None] = []

    def blocking_connector():
        entered.set()
        release.wait()
        return FakeResolve()

    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=blocking_connector,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
    )
    caller = threading.Thread(target=lambda: result.append(manager.connect(0.05)))
    caller.start()
    try:
        assert entered.wait(0.2)
        caller.join(0.3)
        assert not caller.is_alive()
        assert result == [None]
    finally:
        release.set()
        caller.join(0.3)


def test_late_connector_success_is_discarded_after_connection_deadline(tmp_path) -> None:
    """Catches a timed-out scripting call reviving a manager after it later succeeds."""
    config = resolve_config(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def late_connector():
        entered.set()
        release.wait()
        finished.set()
        return FakeResolve()

    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=late_connector,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
    )
    caller = threading.Thread(target=lambda: manager.connect(0.05))
    caller.start()
    try:
        assert entered.wait(0.2)
        caller.join(0.3)
        assert not caller.is_alive()
        release.set()
        assert finished.wait(0.3)
        assert manager.get_status()["status"] == ResolveStatus.RUNNING_UNAVAILABLE
        with pytest.raises(RuntimeError, match="not connected"):
            manager.require_test_project()
    finally:
        release.set()
        caller.join(0.3)


def test_connect_reports_project_timeline_and_version_after_api_becomes_available(tmp_path) -> None:
    """Catches a successful API connection not being reflected in the public Resolve status."""
    config = resolve_config(tmp_path)
    clock = FakeClock()
    resolve = FakeResolve()
    attempts = 0

    def delayed_api():
        nonlocal attempts
        attempts += 1
        return None if attempts == 1 else resolve

    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=delayed_api,
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=clock,
        sleep=clock.sleep,
        api_call_runner=call_api_immediately,
    )

    assert manager.connect(timeout_seconds=1.0) is resolve
    assert manager.get_status() == {
        "status": ResolveStatus.CONNECTED,
        "connected": True,
        "project": "ARPHE_TEST",
        "timeline": "Audit timeline",
        "version": "19.1.2.3.Studio",
    }


@pytest.mark.parametrize("project_name", ["CLIENT_WORK", "ARPHE_TEST_COPY", "arphe_audit_20260829"])
def test_require_test_project_refuses_non_disposable_current_projects(
    tmp_path, project_name: str
) -> None:
    """Catches destructive handlers proceeding in a project outside the configured test namespace."""
    config = resolve_config(tmp_path)
    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=lambda: FakeResolve(project_name),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: None,
        api_call_runner=call_api_immediately,
    )

    manager.connect(timeout_seconds=0.1)

    with pytest.raises(PermissionError, match="disposable Resolve project"):
        manager.require_test_project()


@pytest.mark.parametrize("project_name", ["ARPHE_TEST", "ARPHE_AUDIT_20260829"])
def test_require_test_project_allows_only_configured_disposable_projects(
    tmp_path, project_name: str
) -> None:
    """Catches the project safety gate blocking the exact test or audit project convention."""
    config = resolve_config(tmp_path)
    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=lambda: FakeResolve(project_name),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: None,
        api_call_runner=call_api_immediately,
    )

    manager.connect(timeout_seconds=0.1)

    assert manager.require_test_project() == project_name


def test_process_replacement_invalidates_cached_connection_before_status_or_destructive_use(
    tmp_path,
) -> None:
    """Catches a cached API session being trusted after configured Resolve is replaced."""
    config = resolve_config(tmp_path)
    processes = [resolve_process(config.executable_path)]
    manager = ResolveManager(
        config,
        process_executables=lambda: processes,
        api_connector=lambda: FakeResolve(),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: None,
        api_call_runner=call_api_immediately,
    )

    assert manager.connect(timeout_seconds=0.1) is not None
    processes[:] = [tmp_path / "replacement" / "Resolve.exe"]

    assert manager.get_status()["status"] == ResolveStatus.WRONG_EXECUTABLE
    with pytest.raises(RuntimeError, match="not connected"):
        manager.require_test_project()


def test_same_path_process_replacement_invalidates_cached_connection_identity(tmp_path) -> None:
    """Catches PID reuse at the configured path preserving a stale Resolve API session."""
    config = resolve_config(tmp_path)
    processes = [resolve_process(config.executable_path, pid=101, create_time=1000.0)]
    manager = ResolveManager(
        config,
        process_executables=lambda: processes,
        api_connector=lambda: FakeResolve(),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: None,
        api_call_runner=call_api_immediately,
    )

    assert manager.connect(timeout_seconds=0.1) is not None
    processes[:] = [resolve_process(config.executable_path, pid=202, create_time=2000.0)]

    assert manager.get_status()["status"] == ResolveStatus.RUNNING_UNAVAILABLE
    with pytest.raises(RuntimeError, match="not connected"):
        manager.require_test_project()


def test_import_media_uses_an_injected_adapter_only_after_the_disposable_project_gate(tmp_path) -> None:
    """Catches media import bypassing the disposable-project check or directly invoking Resolve in a handler."""
    config = resolve_config(tmp_path)
    imported: list[tuple[str, str | None, CancellationToken]] = []
    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=lambda: FakeResolve(),
        launcher=lambda path: pytest.fail(f"unexpected launch: {path}"),
        clock=FakeClock(),
        sleep=lambda seconds: pytest.fail(f"unexpected sleep: {seconds}"),
        api_call_runner=call_api_immediately,
        media_importer=lambda path, target_bin, token: imported.append((path, target_bin, token)) or {"imported": [path], "target_bin": target_bin},
    )
    assert manager.connect(timeout_seconds=0.1) is not None

    token = CancellationToken()
    result = manager.import_media("incoming/clip.mp4", "Remote Agent", token)

    assert result == {"imported": ["incoming/clip.mp4"], "target_bin": "Remote Agent"}
    assert imported == [("incoming/clip.mp4", "Remote Agent", token)]


def test_resolve_script_loader_imports_from_a_trusted_installed_modules_directory(tmp_path) -> None:
    modules = tmp_path / "Developer" / "Scripting" / "Modules"
    modules.mkdir(parents=True)
    (modules / "DaVinciResolveScript.py").write_text(
        "def scriptapp(name):\n    return {'application': name}\n", encoding="utf-8"
    )

    loaded = _load_resolve_script_module((modules,))

    assert loaded.scriptapp("Resolve") == {"application": "Resolve"}


def test_builtin_resolve_adapters_are_guarded_and_return_only_safe_metadata(tmp_path) -> None:
    class Clip:
        def GetName(self):
            return "clip.mp4"

    class MediaPool:
        def ImportMedia(self, paths):
            assert paths == [str((tmp_path / "incoming" / "clip.mp4").resolve())]
            return [Clip()]

        def CreateTimelineFromClips(self, name, clips):
            assert name == "ARPHE_REMOTE_TRACKING_PROBE"
            assert len(clips) == 1
            tracker = type("Tracker", (), {"GetName": lambda self: "Tracker1"})()
            comp = type("Comp", (), {"AddTool": lambda self, tool: tracker if tool == "Tracker" else None})()
            item = type("Item", (), {"AddFusionComp": lambda self: comp})()
            return type(
                "ProbeTimeline",
                (),
                {
                    "GetName": lambda self: name,
                    "GetItemListInTrack": lambda self, kind, index: [item] if (kind, index) == ("video", 1) else [],
                },
            )()

    class RenderProject(FakeProject):
        def __init__(self):
            super().__init__("ARPHE_TEST")
            self.media_pool = MediaPool()
            self.timeline = type(
                "RenderTimeline",
                (),
                {
                    "GetName": lambda self: "Long test timeline",
                    "GetStartFrame": lambda self: 1000,
                    "GetEndFrame": lambda self: 5000,
                },
            )()

        def GetMediaPool(self):
            return self.media_pool

        def GetCurrentTimeline(self):
            return self.timeline

        def SetRenderSettings(self, settings):
            self.settings = settings
            return True

        def AddRenderJob(self):
            output = Path(self.settings["TargetDir"]) / self.settings["CustomName"]
            output.write_bytes(b"render")
            return "render-job-1"

        def StartRendering(self, job_id):
            return job_id == "render-job-1"

        def IsRenderingInProgress(self):
            return False

    class RenderResolve(FakeResolve):
        def __init__(self):
            self._project = RenderProject()

    config = resolve_config(tmp_path)
    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=RenderResolve,
        launcher=lambda _path: None,
        clock=FakeClock(),
        sleep=lambda _seconds: None,
        api_call_runner=call_api_immediately,
    )
    assert manager.connect(0.1) is not None
    source = (tmp_path / "incoming" / "clip.mp4").resolve()
    source.parent.mkdir()
    source.write_bytes(b"clip")
    target = (tmp_path / "exports" / "probe.mp4").resolve()
    target.parent.mkdir()
    token = CancellationToken()

    imported = manager.import_local_media(source, "incoming/clip.mp4", None, token)
    audit = manager.run_capability_audit({}, token)
    tracking = manager.run_tracking_probe(source, "incoming/clip.mp4", token)
    rendered = manager.run_render_probe(target, "exports/probe.mp4", token)

    assert imported == {"imported": ["incoming/clip.mp4"], "imported_count": 1, "target_bin": None}
    assert audit["project"] == "ARPHE_TEST" and audit["capabilities"]["render"] is True
    assert tracking["source_path"] == "incoming/clip.mp4" and tracking["tracker_created"] is True
    assert tracking["timeline"] == "ARPHE_REMOTE_TRACKING_PROBE"
    assert rendered["path"] == "exports/probe.mp4"
    assert rendered["size_bytes"] == 6 and len(rendered["sha256"]) == 64
    assert manager._resolve._project.settings["SelectAllFrames"] is False
    assert manager._resolve._project.settings["MarkIn"] == 1000
    assert manager._resolve._project.settings["MarkOut"] == 1089
    assert rendered["frame_range"] == {"mark_in": 1000, "mark_out": 1089, "frame_count": 90}


def test_status_probe_never_enters_resolve_concurrently_with_a_blocking_operation(tmp_path) -> None:
    entered = threading.Event()
    release = threading.Event()

    class BlockingProject(FakeProject):
        def GetMediaPool(self):
            return object()

        def GetCurrentTimeline(self):
            entered.set()
            assert release.wait(1)
            return super().GetCurrentTimeline()

    class BlockingResolve(FakeResolve):
        def __init__(self):
            self._project = BlockingProject("ARPHE_TEST")

    config = resolve_config(tmp_path)
    manager = ResolveManager(
        config,
        process_executables=lambda: [resolve_process(config.executable_path)],
        api_connector=BlockingResolve,
        launcher=lambda _path: None,
        clock=FakeClock(),
        sleep=lambda _seconds: None,
        api_call_runner=call_api_immediately,
    )
    assert manager.connect(0.1) is not None
    audit_thread = threading.Thread(
        target=lambda: manager.run_capability_audit({}, CancellationToken())
    )
    audit_thread.start()
    assert entered.wait(1)
    finished = threading.Event()
    status = {}
    status_thread = threading.Thread(
        target=lambda: (status.update(manager.get_status()), finished.set())
    )
    status_thread.start()
    try:
        assert finished.wait(0.1)
        assert status["status"] is ResolveStatus.RUNNING_UNAVAILABLE
    finally:
        release.set()
        audit_thread.join(1)
        status_thread.join(1)
