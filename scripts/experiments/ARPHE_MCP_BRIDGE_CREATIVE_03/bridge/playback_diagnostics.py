from __future__ import annotations

import shutil
import subprocess
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
        },
        "not_exposed_by_resolve_api": dict(NOT_EXPOSED_BY_RESOLVE_API),
        "privacy": {
            "file_paths_disclosed": False,
            "media_content_read": False,
        },
        "writes_performed": False,
    }
