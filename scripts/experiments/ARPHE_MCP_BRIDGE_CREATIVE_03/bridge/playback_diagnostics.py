from __future__ import annotations

import shutil
import subprocess
import ctypes
from ctypes import wintypes
import json
import os
import time
from typing import Any, Callable


PROJECT_SETTINGS = (
    "timelineFrameRate",
    "timelinePlaybackFrameRate",
    "timelineResolutionWidth",
    "timelineResolutionHeight",
    "videoMonitorFormat",
    "optimizedMediaFormat",
    "proxyMediaFormat",
)

CLIP_PROPERTIES = (
    "File Name",
    "Type",
    "Video Codec",
    "Audio Codec",
    "Resolution",
    "FPS",
    "Data Level",
    "Audio Ch",
    "Audio Bit Depth",
    "Audio Sample Rate",
    "Duration",
    "Proxy Media",
    "Optimized Media",
)

NOT_EXPOSED_BY_RESOLVE_API = {
    "gpu_processing_mode": "Global Resolve preference is not exposed by the scripting API.",
    "decode_h264_h265_hardware_acceleration": (
        "Global Resolve decode preference is not exposed by the scripting API."
    ),
    "audio_output_device_and_buffer": (
        "Resolve audio I/O device and buffer preferences are not exposed by the scripting API."
    ),
}


def _call(target: Any, method: str, *args: Any) -> Any:
    if target is None:
        return None
    function = getattr(target, method, None)
    if not callable(function):
        return None
    try:
        return function(*args)
    except Exception:
        return None


def _filtered_mapping(value: Any, allowlist: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {name: value[name] for name in allowlist if name in value}


def _run_fixed_command(command: list[str], timeout: float) -> str:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return completed.stdout


def _nvidia_diagnostics(
    executable_finder: Callable[[str], str | None],
    command_runner: Callable[[list[str], float], str],
) -> dict[str, Any]:
    executable = executable_finder("nvidia-smi")
    if not executable:
        return {"available": False, "reason": "executable_not_found", "gpus": []}
    command = [
        executable,
        "--query-gpu=name,driver_version,memory.total,utilization.gpu,utilization.decoder",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = command_runner(command, 3.0)
    except Exception as exc:
        return {
            "available": False,
            "reason": "probe_failed",
            "error_type": type(exc).__name__,
            "gpus": [],
        }
    gpus = []
    for line in output.splitlines():
        columns = [column.strip() for column in line.split(",")]
        if len(columns) != 5:
            continue
        gpus.append({
            "name": columns[0],
            "driver_version": columns[1],
            "memory_total_mib": columns[2],
            "utilization_gpu_percent": columns[3],
            "utilization_decoder_percent": columns[4],
        })
    return {
        "available": bool(gpus),
        "reason": None if gpus else "no_parseable_gpu_rows",
        "gpus": gpus,
    }


def _sample_media(timeline: Any, limit: int = 8) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    video_tracks = _call(timeline, "GetTrackCount", "video") or 0
    try:
        track_count = max(0, int(video_tracks))
    except (TypeError, ValueError):
        track_count = 0
    for track_index in range(1, track_count + 1):
        items = _call(timeline, "GetItemListInTrack", "video", track_index) or []
        for item in items:
            media_pool_item = _call(item, "GetMediaPoolItem")
            properties = _call(media_pool_item, "GetClipProperty")
            filtered = _filtered_mapping(properties, CLIP_PROPERTIES)
            if filtered and filtered not in samples:
                samples.append(filtered)
            if len(samples) >= limit:
                return samples
    return samples


def collect_playback_diagnostics(
    resolve: Any,
    project: Any,
    timeline: Any,
    workstation_id: str,
    *,
    executable_finder: Callable[[str], str | None] = shutil.which,
    command_runner: Callable[[list[str], float], str] = _run_fixed_command,
) -> dict[str, Any]:
    project_settings = _filtered_mapping(_call(project, "GetSetting"), PROJECT_SETTINGS)
    timeline_settings = _filtered_mapping(_call(timeline, "GetSetting"), PROJECT_SETTINGS)
    return {
        "ok": True,
        "action": "get_playback_diagnostics",
        "workstation_id": workstation_id,
        "resolve": {
            "product_name": _call(resolve, "GetProductName"),
            "version": _call(resolve, "GetVersionString") or _call(resolve, "GetVersion"),
            "current_page": _call(resolve, "GetCurrentPage"),
        },
        "project": {
            "name": _call(project, "GetName"),
            "settings": project_settings,
        },
        "timeline": {
            "name": _call(timeline, "GetName"),
            "settings": timeline_settings,
            "video_track_count": _call(timeline, "GetTrackCount", "video"),
            "audio_track_count": _call(timeline, "GetTrackCount", "audio"),
        },
        "media_samples": _sample_media(timeline),
        "system": {
            "nvidia_smi": _nvidia_diagnostics(executable_finder, command_runner),
            "windows_audio": collect_windows_audio_diagnostics(
                executable_finder=executable_finder,
                command_runner=command_runner,
            ),
        },
        "not_exposed_by_resolve_api": dict(NOT_EXPOSED_BY_RESOLVE_API),
        "privacy": {
            "file_paths_disclosed": False,
            "media_content_read": False,
        },
        "writes_performed": False,
    }


def collect_windows_audio_diagnostics(
    *,
    executable_finder: Callable[[str], str | None] = shutil.which,
    command_runner: Callable[[list[str], float], str] = _run_fixed_command,
) -> dict[str, Any]:
    executable = executable_finder("powershell") or executable_finder("pwsh")
    if not executable:
        return {
            "available": False,
            "reason": "powershell_not_found",
            "devices": [],
            "resolve_audio_preferences_available": False,
        }
    script = (
        "$devices=@(Get-CimInstance -ClassName Win32_SoundDevice -ErrorAction Stop | "
        "Select-Object Name,Status,Manufacturer);"
        "$dpc=Get-CimInstance -ClassName Win32_PerfFormattedData_PerfOS_Processor "
        "-Filter \"Name='_Total'\" -ErrorAction SilentlyContinue;"
        "[pscustomobject]@{audio_devices=$devices;dpc_percent=$dpc.PercentDPCTime} | "
        "ConvertTo-Json -Compress -Depth 4"
    )
    try:
        raw = command_runner([
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ], 5.0)
        payload = json.loads(raw)
    except Exception as exc:
        return {
            "available": False,
            "reason": "probe_failed",
            "error_type": type(exc).__name__,
            "devices": [],
            "resolve_audio_preferences_available": False,
        }
    devices_raw = payload.get("audio_devices", []) if isinstance(payload, dict) else []
    if isinstance(devices_raw, dict):
        devices_raw = [devices_raw]
    devices = []
    for item in devices_raw if isinstance(devices_raw, list) else []:
        if not isinstance(item, dict):
            continue
        devices.append({
            "name": item.get("Name"),
            "status": item.get("Status"),
            "manufacturer": item.get("Manufacturer"),
        })
    return {
        "available": True,
        "reason": None,
        "devices": devices,
        "dpc_percent_snapshot": payload.get("dpc_percent") if isinstance(payload, dict) else None,
        "default_device_known": False,
        "sample_rate_known": False,
        "resolve_audio_preferences_available": False,
    }


def _windows_cpu_reader() -> Callable[[], float | None]:
    if os.name != "nt":
        return lambda: None
    filetime = wintypes.FILETIME
    previous: list[tuple[int, int, int] | None] = [None]

    def as_int(value: Any) -> int:
        return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)

    def read() -> float | None:
        idle, kernel, user = filetime(), filetime(), filetime()
        if not ctypes.windll.kernel32.GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        current = (as_int(idle), as_int(kernel), as_int(user))
        before = previous[0]
        previous[0] = current
        if before is None:
            return None
        idle_delta = current[0] - before[0]
        total_delta = current[1] - before[1] + current[2] - before[2]
        if total_delta <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (total_delta - idle_delta) / total_delta))

    return read


def _windows_memory_percent() -> float | None:
    if os.name != "nt":
        return None

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return float(status.dwMemoryLoad)


def _default_gpu_reader() -> Callable[[], dict[str, float] | None]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return lambda: None

    def read() -> dict[str, float] | None:
        result = _nvidia_diagnostics(lambda _name: executable, _run_fixed_command)
        if not result.get("available"):
            return None
        rows = result.get("gpus") or []
        try:
            return {
                "gpu_percent": max(float(row["utilization_gpu_percent"]) for row in rows),
                "decoder_percent": max(float(row["utilization_decoder_percent"]) for row in rows),
            }
        except (KeyError, TypeError, ValueError):
            return None

    return read


def _aggregate(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"average": None, "maximum": None}
    return {
        "average": round(sum(values) / len(values), 2),
        "maximum": round(max(values), 2),
    }


def sample_playback_performance(
    resolve: Any,
    workstation_id: str,
    *,
    expected_page: str,
    duration_seconds: float = 5.0,
    interval_seconds: float = 0.5,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    cpu_reader: Callable[[], float | None] | None = None,
    memory_reader: Callable[[], float | None] | None = None,
    gpu_reader: Callable[[], dict[str, float] | None] | None = None,
) -> dict[str, Any]:
    if expected_page not in {"edit", "fairlight"}:
        raise ValueError("expected_page deve essere edit o fairlight")
    if not 1.0 <= float(duration_seconds) <= 10.0:
        raise ValueError("duration_seconds deve essere tra 1 e 10")
    if not 0.1 <= float(interval_seconds) <= 1.0:
        raise ValueError("interval_seconds deve essere tra 0.1 e 1")
    current_page = _call(resolve, "GetCurrentPage")
    if current_page != expected_page:
        raise ValueError(
            f"Pagina Resolve corrente {current_page!r}; attesa {expected_page!r}"
        )
    read_cpu = cpu_reader or _windows_cpu_reader()
    read_memory = memory_reader or _windows_memory_percent
    read_gpu = gpu_reader or _default_gpu_reader()
    cpu_values: list[float] = []
    memory_values: list[float] = []
    gpu_values: list[float] = []
    decoder_values: list[float] = []
    sample_count = 0
    started = clock()
    while True:
        cpu = read_cpu()
        memory = read_memory()
        gpu = read_gpu()
        if isinstance(cpu, (int, float)):
            cpu_values.append(float(cpu))
        if isinstance(memory, (int, float)):
            memory_values.append(float(memory))
        if isinstance(gpu, dict):
            if isinstance(gpu.get("gpu_percent"), (int, float)):
                gpu_values.append(float(gpu["gpu_percent"]))
            if isinstance(gpu.get("decoder_percent"), (int, float)):
                decoder_values.append(float(gpu["decoder_percent"]))
        sample_count += 1
        elapsed = clock() - started
        if elapsed >= duration_seconds:
            break
        sleeper(min(interval_seconds, duration_seconds - elapsed))
    return {
        "ok": True,
        "action": "sample_playback_performance",
        "workstation_id": workstation_id,
        "scenario": expected_page,
        "duration_seconds": float(duration_seconds),
        "sample_count": sample_count,
        "cpu_percent": _aggregate(cpu_values),
        "memory_percent": _aggregate(memory_values),
        "nvidia_gpu_percent": _aggregate(gpu_values),
        "nvidia_decoder_percent": _aggregate(decoder_values),
        "instructions": "Avviare la riproduzione prima della chiamata e lasciarla attiva fino al risultato.",
        "writes_performed": False,
    }
