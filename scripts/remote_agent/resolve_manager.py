"""Guarded local lifecycle and scripting-API access for DaVinci Resolve."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from enum import Enum
import math
import ntpath
from pathlib import Path
import subprocess
import time
from typing import Any

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

_CONNECTION_POLL_SECONDS = 0.25


def _configured_process_executables() -> Iterable[object]:
    """Return local executable paths without importing psutil in unit tests."""
    import psutil

    for process in psutil.process_iter(["exe"]):
        try:
            executable = process.info.get("exe")
        except (psutil.AccessDenied, psutil.NoSuchProcess, AttributeError):
            continue
        if executable:
            yield executable


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
    ) -> None:
        self._config = config
        self._process_executables = process_executables
        self._api_connector = api_connector
        self._launcher = launcher
        self._clock = clock
        self._sleep = sleep
        self._resolve: Any | None = None

    def get_process_state(self) -> ResolveProcessState:
        """Identify only the exact locally configured Resolve executable."""
        configured_path = _normalized_windows_path(self._config.executable_path)
        configured_name = ntpath.basename(str(self._config.executable_path)).casefold()
        has_wrong_resolve = False
        for process in self._process_executables():
            executable = _process_executable_path(process)
            if executable is None:
                continue
            if _normalized_windows_path(executable) == configured_path:
                return ResolveProcessState.RUNNING
            if ntpath.basename(str(executable)).casefold() == configured_name:
                has_wrong_resolve = True
        if has_wrong_resolve:
            return ResolveProcessState.WRONG_EXECUTABLE
        return ResolveProcessState.NOT_RUNNING

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

        process_state = self.get_process_state()
        if process_state is ResolveProcessState.WRONG_EXECUTABLE:
            self._resolve = None
            return None
        if process_state is ResolveProcessState.NOT_RUNNING:
            self.launch_if_allowed()

        deadline = self._clock() + timeout_seconds
        while True:
            process_state = self.get_process_state()
            if process_state is ResolveProcessState.WRONG_EXECUTABLE:
                self._resolve = None
                return None
            if process_state is ResolveProcessState.RUNNING:
                try:
                    resolve = self._api_connector()
                except Exception:
                    resolve = None
                if resolve is not None:
                    self._resolve = resolve
                    return resolve
            if self._clock() >= deadline:
                self._resolve = None
                return None
            self._sleep(min(_CONNECTION_POLL_SECONDS, deadline - self._clock()))

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
        process_state = self.get_process_state()
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
        project_name = self._name(self._current_project())
        if project_name is None:
            raise RuntimeError("Resolve current project is unavailable")
        if (
            project_name != self._config.test_project
            and not project_name.startswith(self._config.audit_project_prefix)
        ):
            raise PermissionError("destructive operations require a disposable Resolve project")
        return project_name
