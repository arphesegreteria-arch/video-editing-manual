# -*- coding: utf-8 -*-
"""ARPHE MCP bridge read-only probe: ping + resolve_status."""

import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

mcp = MCPServer(
    "ARPHE Resolve",
    instructions=(
        "ARPHE Resolve MCP bridge - read-only test. "
        "Use resolve_status to inspect the currently open Resolve Studio context."
    ),
)


def _configure_resolve_api() -> dict[str, Any]:
    programdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    programfiles = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    root = programdata / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
    modules = root / "Modules"
    candidates = [
        programfiles / "Blackmagic Design" / "DaVinci Resolve" / "fusionscript.dll",
        programfiles / "Blackmagic Design" / "DaVinci Resolve Studio" / "fusionscript.dll",
    ]

    if modules.exists() and str(modules) not in sys.path:
        sys.path.insert(0, str(modules))
    os.environ.setdefault("RESOLVE_SCRIPT_API", str(root))

    selected = os.environ.get("RESOLVE_SCRIPT_LIB")
    if not selected or not Path(selected).exists():
        selected = None
        for candidate in candidates:
            if candidate.exists():
                selected = str(candidate)
                os.environ["RESOLVE_SCRIPT_LIB"] = selected
                break

    return {
        "modules_path": str(modules),
        "modules_exists": modules.exists(),
        "resolve_script_lib": selected,
    }


def _safe_call(obj: Any, method_name: str, *args: Any) -> Any:
    if obj is None:
        return None
    try:
        method = getattr(obj, method_name, None)
        return method(*args) if callable(method) else None
    except Exception:
        return None


@mcp.tool()
def ping() -> dict[str, Any]:
    """Return a harmless health check for the local ARPHE MCP bridge."""
    return {
        "ok": True,
        "bridge": "ARPHE_MCP_BRIDGE_READ_01",
        "mode": "READ_ONLY",
        "write_tools_enabled": False,
    }


@mcp.tool()
def resolve_status() -> dict[str, Any]:
    """Read the currently open Resolve Studio project/timeline without modifying it."""
    api_paths = _configure_resolve_api()

    try:
        import DaVinciResolveScript as dvr
    except Exception as exc:
        return {"ok": False, "stage": "import", "error": f"{type(exc).__name__}: {exc}", "api_paths": api_paths}

    try:
        resolve = dvr.scriptapp("Resolve")
    except Exception as exc:
        return {"ok": False, "stage": "connect", "error": f"{type(exc).__name__}: {exc}", "api_paths": api_paths}

    if resolve is None:
        return {
            "ok": False,
            "stage": "connect",
            "error": "Resolve non raggiungibile. Aprire Studio e usare External scripting using = Local.",
            "api_paths": api_paths,
        }

    pm = _safe_call(resolve, "GetProjectManager")
    project = _safe_call(pm, "GetCurrentProject")
    timeline = _safe_call(project, "GetCurrentTimeline") if project else None

    result: dict[str, Any] = {
        "ok": True,
        "mode": "READ_ONLY",
        "resolve_version": _safe_call(resolve, "GetVersionString") or _safe_call(resolve, "GetVersion"),
        "project_name": _safe_call(project, "GetName") if project else None,
        "timeline_name": _safe_call(timeline, "GetName") if timeline else None,
        "timeline_fps": _safe_call(timeline, "GetSetting", "timelineFrameRate") if timeline else None,
        "video_track_count": _safe_call(timeline, "GetTrackCount", "video") if timeline else None,
        "audio_track_count": _safe_call(timeline, "GetTrackCount", "audio") if timeline else None,
        "v1_clip_count": None,
        "a1_clip_count": None,
    }

    if timeline:
        try:
            result["v1_clip_count"] = len(timeline.GetItemListInTrack("video", 1) or [])
        except Exception as exc:
            result["v1_error"] = f"{type(exc).__name__}: {exc}"
        try:
            result["a1_clip_count"] = len(timeline.GetItemListInTrack("audio", 1) or [])
        except Exception as exc:
            result["a1_error"] = f"{type(exc).__name__}: {exc}"

    return result


if __name__ == "__main__":
    mcp.run()
