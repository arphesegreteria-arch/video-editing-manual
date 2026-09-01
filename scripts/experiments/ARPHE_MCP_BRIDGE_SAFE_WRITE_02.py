# -*- coding: utf-8 -*-
"""ARPHE MCP bridge with read tools plus one gated safe-write timeline tool."""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

mcp = MCPServer(
    "ARPHE Resolve",
    instructions=(
        "ARPHE Resolve MCP bridge. create_safe_working_timeline is the only "
        "write action and creates only a new empty ARPHE timeline before "
        "returning to the original timeline."
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
        for candidate in candidates:
            if candidate.exists():
                selected = str(candidate)
                os.environ["RESOLVE_SCRIPT_LIB"] = selected
                break
    return {"modules_path": str(modules), "resolve_script_lib": selected}


def _safe_call(obj: Any, method_name: str, *args: Any) -> Any:
    if obj is None:
        return None
    try:
        method = getattr(obj, method_name, None)
        return method(*args) if callable(method) else None
    except Exception:
        return None


def _context():
    paths = _configure_resolve_api()
    try:
        import DaVinciResolveScript as dvr
        resolve = dvr.scriptapp("Resolve")
    except Exception as exc:
        return None, None, None, {"ok": False, "stage": "connect", "error": f"{type(exc).__name__}: {exc}", "api_paths": paths}
    if resolve is None:
        return None, None, None, {"ok": False, "stage": "connect", "error": "Resolve non raggiungibile."}
    pm = _safe_call(resolve, "GetProjectManager")
    project = _safe_call(pm, "GetCurrentProject")
    timeline = _safe_call(project, "GetCurrentTimeline") if project else None
    return resolve, project, timeline, None


def _prefix(value: str) -> str:
    text = re.sub(r"[^A-Z0-9_-]+", "_", (value or "").strip().upper()).strip("_")[:40]
    if not text:
        text = "ARPHE_CHATGPT_TEST"
    if not text.startswith("ARPHE"):
        text = "ARPHE_" + text
    return text


@mcp.tool()
def ping() -> dict[str, Any]:
    """Health check."""
    return {"ok": True, "bridge": "ARPHE_MCP_BRIDGE_SAFE_WRITE_02", "mode": "SAFE_WRITE", "write_tools": ["create_safe_working_timeline"]}


@mcp.tool()
def resolve_status() -> dict[str, Any]:
    """Read the open Resolve context without modifying it."""
    resolve, project, timeline, error = _context()
    if error:
        return error
    result = {
        "ok": True,
        "resolve_version": _safe_call(resolve, "GetVersionString") or _safe_call(resolve, "GetVersion"),
        "project_name": _safe_call(project, "GetName") if project else None,
        "timeline_name": _safe_call(timeline, "GetName") if timeline else None,
        "timeline_fps": _safe_call(timeline, "GetSetting", "timelineFrameRate") if timeline else None,
        "v1_clip_count": None,
        "a1_clip_count": None,
    }
    if timeline:
        result["v1_clip_count"] = len(timeline.GetItemListInTrack("video", 1) or [])
        result["a1_clip_count"] = len(timeline.GetItemListInTrack("audio", 1) or [])
    return result


@mcp.tool()
def create_safe_working_timeline(name_prefix: str = "ARPHE_CHATGPT_TEST") -> dict[str, Any]:
    """Create one empty ARPHE timeline, verify it, then return to the original timeline."""
    resolve, project, original, error = _context()
    if error:
        return error
    if project is None or original is None:
        return {"ok": False, "stage": "preflight", "error": "Serve un progetto con timeline attiva."}

    media_pool = _safe_call(project, "GetMediaPool")
    if media_pool is None:
        return {"ok": False, "stage": "preflight", "error": "MediaPool non disponibile."}

    original_name = _safe_call(original, "GetName")
    before = _safe_call(project, "GetTimelineCount")
    name = f"{_prefix(name_prefix)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    created = media_pool.CreateEmptyTimeline(name)
    if not created:
        return {"ok": False, "stage": "create", "original_timeline": original_name, "requested_timeline": name}

    after = _safe_call(project, "GetTimelineCount")
    returned = bool(project.SetCurrentTimeline(original))
    final = _safe_call(project, "GetCurrentTimeline")
    final_name = _safe_call(final, "GetName") if final else None
    count_ok = not (isinstance(before, int) and isinstance(after, int)) or after == before + 1
    created_name = _safe_call(created, "GetName")
    ok = created_name == name and count_ok and returned and final_name == original_name

    return {
        "ok": ok,
        "action": "create_safe_working_timeline",
        "project": _safe_call(project, "GetName"),
        "original_timeline": original_name,
        "created_timeline": created_name,
        "timeline_count_before": before,
        "timeline_count_after": after,
        "timeline_count_increment_ok": count_ok,
        "returned_to_original": returned,
        "current_timeline_final": final_name,
        "clip_edits_performed": 0,
        "timeline_deletions_performed": 0,
    }


if __name__ == "__main__":
    mcp.run()
