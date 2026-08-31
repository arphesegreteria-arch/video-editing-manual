"""Guarded local lifecycle and scripting-API access for DaVinci Resolve."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
import math
import ntpath
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any

from scripts.remote_agent.cancellation import CancellationToken, require_not_cancelled
from scripts.remote_agent.config import ResolveConfig


class ResolveProcessState(str, Enum):
    """Observed local process state, without making an API connection."""

    NOT_RUNNING = "not_running"
    RUNNING = "running"
    WRONG_EXECUTABLE = "wrong_executable"


class ResolveStatus(str, Enum):
    """User-facing Resolve status for the agent lifecycle."""

    NOT_RUNNING = "not_running"
    RUNNING_UNAVAILABLE = "running_unavailable"
    CONNECTED = "connected"
    WRONG_EXECUTABLE = "wrong_executable"


ProcessExecutableProvider = Callable[[], Iterable[object]]
ResolveApiConnector = Callable[[], Any | None]
ResolveLauncher = Callable[[Path], None]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]
ApiCallRunner = Callable[[ResolveApiConnector, float], Any | None]
MediaImporter = Callable[[str, str | None, CancellationToken], dict[str, Any]]

_CONNECTION_POLL_SECONDS = 0.25


@dataclass(frozen=True)
class ResolveProcessIdentity:
    """Stable identity for one locally observed Resolve process."""

    pid: int
    create_time: float


def _configured_process_executables() -> Iterable[object]:
    """Return local executable paths without importing psutil in unit tests."""
    import psutil

    for process in psutil.process_iter(["exe", "pid", "create_time"]):
        try:
            process_info = process.info
            executable = process_info.get("exe")
        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            continue
        if executable:
            yield process_info


def _connect_to_resolve() -> Any | None:
    """Load Resolve's locally installed scripting module on demand."""
    try:
        import DaVinciResolveScript as resolve_script
    except ImportError:
        return None
    return resolve_script.scriptapp("Resolve")


def _launch_configured_executable(executable_path: Path) -> None:
    """Start one explicitly configured executable without involving a shell."""
    subprocess.Popen([str(executable_path)])


def _call_api_with_timeout(
    api_connector: ResolveApiConnector, timeout_seconds: float
) -> Any | None:
    """Run an untrusted synchronous API call without blocking application shutdown.

    The worker is daemonized and owns no manager state. A result produced after
    the caller's deadline is therefore discarded rather than reviving a stopped
    or timed-out agent lifecycle.
    """
    results: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            results.put((True, api_connector()))
        except Exception:
            results.put((False, None))

    threading.Thread(target=invoke, daemon=True).start()
    try:
        succeeded, result = results.get(timeout=timeout_seconds)
    except queue.Empty:
        return None
    return result if succeeded else None


def _normalized_windows_path(path: str | Path) -> str:
    return ntpath.normcase(ntpath.normpath(str(path)))


def _process_executable_path(process: object) -> str | Path | None:
    """Accept straightforward injected paths plus psutil process records."""
    if isinstance(process, (str, Path)):
        return process
    if isinstance(process, Mapping):
        executable = process.get("exe")
        return executable if isinstance(executable, (str, Path)) else None
    info = getattr(process, "info", None)
    if isinstance(info, Mapping):
        executable = info.get("exe")
        return executable if isinstance(executable, (str, Path)) else None
    executable = getattr(process, "exe", None)
    if callable(executable):
        try:
            executable = executable()
        except Exception:
            return None
    return executable if isinstance(executable, (str, Path)) else None


def _process_field(process: object, field: str) -> object | None:
    if isinstance(process, Mapping):
        return process.get(field)
    info = getattr(process, "info", None)
    if isinstance(info, Mapping):
        return info.get(field)
    value = getattr(process, field, None)
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _process_identity(process: object) -> ResolveProcessIdentity | None:
    pid = _process_field(process, "pid")
    create_time = _process_field(process, "create_time")
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or not isinstance(create_time, (int, float))
        or isinstance(create_time, bool)
        or not math.isfinite(create_time)
    ):
        return None
    return ResolveProcessIdentity(pid=pid, create_time=float(create_time))


class ResolveManager:
    """Connect only to the locally configured Resolve Studio installation.

    Each side-effecting dependency is injected so tests never inspect a live
    process, import Resolve's scripting module, or start Resolve.
    """

    def __init__(
        self,
        config: ResolveConfig,
        *,
        process_executables: ProcessExecutableProvider = _configured_process_executables,
        api_connector: ResolveApiConnector = _connect_to_resolve,
        launcher: ResolveLauncher = _launch_configured_executable,
        clock: Clock = time.monotonic,
        sleep: Sleeper = time.sleep,
        api_call_runner: ApiCallRunner = _call_api_with_timeout,
        media_importer: MediaImporter | None = None,
    ) -> None:
        self._config = config
        self._process_executables = process_executables
        self._api_connector = api_connector
        self._launcher = launcher
        self._clock = clock
        self._sleep = sleep
        self._api_call_runner = api_call_runner
        self._media_importer = media_importer
        self._resolve: Any | None = None
        self._resolve_identity: ResolveProcessIdentity | None = None

    def _observe_process(self) -> tuple[ResolveProcessState, ResolveProcessIdentity | None]:
        """Identify only the exact locally configured Resolve executable."""
        configured_path = _normalized_windows_path(self._config.executable_path)
        configured_name = ntpath.basename(str(self._config.executable_path)).casefold()
        configured_processes: list[ResolveProcessIdentity | None] = []
        has_wrong_resolve = False
        for process in self._process_executables():
            executable = _process_executable_path(process)
            if executable is None:
                continue
            if _normalized_windows_path(executable) == configured_path:
                configured_processes.append(_process_identity(process))
            elif ntpath.basename(str(executable)).casefold() == configured_name:
                has_wrong_resolve = True
        if has_wrong_resolve or len(configured_processes) > 1:
            return ResolveProcessState.WRONG_EXECUTABLE, None
        if len(configured_processes) == 1:
            return ResolveProcessState.RUNNING, configured_processes[0]
        return ResolveProcessState.NOT_RUNNING, None

    def get_process_state(self) -> ResolveProcessState:
        return self._observe_process()[0]

    def _current_process_observation(
        self,
    ) -> tuple[ResolveProcessState, ResolveProcessIdentity | None]:
        """Return process state and invalidate a cached API for any identity change."""
        process_state, process_identity = self._observe_process()
        if (
            process_state is not ResolveProcessState.RUNNING
            or process_identity is None
            or (
                self._resolve is not None
                and process_identity != self._resolve_identity
            )
        ):
            self._resolve = None
            self._resolve_identity = None
        return process_state, process_identity

    def _current_process_state(self) -> ResolveProcessState:
        return self._current_process_observation()[0]

    def launch_if_allowed(self) -> bool:
        """Launch only the executable chosen in local ResolveConfig."""
        if not self._config.launch_if_needed:
            return False
        if self.get_process_state() is not ResolveProcessState.NOT_RUNNING:
            return False
        self._launcher(self._config.executable_path)
        return True

    def connect(self, timeout_seconds: float) -> Any | None:
        """Wait a bounded time for the scripting API of configured Resolve only."""
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise ValueError("timeout_seconds must be a non-negative number")
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("timeout_seconds must be a non-negative number")

        process_state, _ = self._current_process_observation()
        if process_state is ResolveProcessState.WRONG_EXECUTABLE:
            self._resolve = None
            return None
        if process_state is ResolveProcessState.NOT_RUNNING:
            self.launch_if_allowed()

        deadline = self._clock() + timeout_seconds
        while True:
            process_state, process_identity = self._current_process_observation()
            if process_state is ResolveProcessState.WRONG_EXECUTABLE:
                return None
            remaining = deadline - self._clock()
            if remaining <= 0:
                self._resolve = None
                return None
            if process_state is ResolveProcessState.RUNNING and process_identity is not None:
                resolve = self._api_call_runner(self._api_connector, remaining)
                remaining = deadline - self._clock()
                if remaining <= 0:
                    self._resolve = None
                    self._resolve_identity = None
                    return None
                if resolve is not None:
                    state_after_call, identity_after_call = self._current_process_observation()
                    if (
                        state_after_call is ResolveProcessState.RUNNING
                        and identity_after_call == process_identity
                    ):
                        self._resolve = resolve
                        self._resolve_identity = process_identity
                        return resolve
            remaining = deadline - self._clock()
            if remaining <= 0:
                self._resolve = None
                self._resolve_identity = None
                return None
            self._sleep(min(_CONNECTION_POLL_SECONDS, remaining))

    def _current_project(self) -> Any:
        if self._resolve is None:
            raise RuntimeError("Resolve is not connected")
        try:
            project = self._resolve.GetProjectManager().GetCurrentProject()
        except Exception as exc:
            raise RuntimeError("Resolve current project is unavailable") from exc
        if project is None:
            raise RuntimeError("Resolve current project is unavailable")
        return project

    @staticmethod
    def _name(value: Any) -> str | None:
        try:
            name = value.GetName()
        except Exception:
            return None
        return name if isinstance(name, str) and name else None

    def get_status(self) -> dict[str, ResolveStatus | bool | str | None]:
        """Return safe, small status details for the agent UI and heartbeat."""
        process_state = self._current_process_state()
        if process_state is ResolveProcessState.WRONG_EXECUTABLE:
            return {
                "status": ResolveStatus.WRONG_EXECUTABLE,
                "connected": False,
                "project": None,
                "timeline": None,
                "version": None,
            }
        if process_state is ResolveProcessState.NOT_RUNNING or self._resolve is None:
            status = (
                ResolveStatus.NOT_RUNNING
                if process_state is ResolveProcessState.NOT_RUNNING
                else ResolveStatus.RUNNING_UNAVAILABLE
            )
            return {
                "status": status,
                "connected": False,
                "project": None,
                "timeline": None,
                "version": None,
            }

        try:
            project = self._current_project()
            timeline = project.GetCurrentTimeline()
            version = self._resolve.GetVersion()
        except Exception:
            return {
                "status": ResolveStatus.RUNNING_UNAVAILABLE,
                "connected": False,
                "project": None,
                "timeline": None,
                "version": None,
            }
        version_text = (
            ".".join(str(part) for part in version)
            if isinstance(version, (list, tuple))
            else str(version) if version is not None else None
        )
        return {
            "status": ResolveStatus.CONNECTED,
            "connected": True,
            "project": self._name(project),
            "timeline": self._name(timeline) if timeline is not None else None,
            "version": version_text,
        }

    def require_test_project(self) -> str:
        """Permit destructive Resolve handlers only in disposable project namespaces."""
        if self._current_process_state() is not ResolveProcessState.RUNNING:
            raise RuntimeError("Resolve is not connected")
        project_name = self._name(self._current_project())
        if project_name is None:
            raise RuntimeError("Resolve current project is unavailable")
        if (
            project_name != self._config.test_project
            and not project_name.startswith(self._config.audit_project_prefix)
        ):
            raise PermissionError("destructive operations require a disposable Resolve project")
        return project_name

    def import_media(
        self, alias_relative_path: str, target_bin: str | None, token: CancellationToken
    ) -> dict[str, Any]:
        """Import only an already broker-validated alias path through an injected adapter."""
        require_not_cancelled(token)
        self.require_test_project()
        if self._media_importer is None:
            raise RuntimeError("Resolve media import adapter is not configured")
        result = self._media_importer(alias_relative_path, target_bin, token)
        require_not_cancelled(token)
        if not isinstance(result, dict):
            raise RuntimeError("Resolve media import adapter returned invalid output")
        return result
