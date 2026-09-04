from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any


def safe_call(obj: Any, method_name: str, *args: Any) -> Any:
    if obj is None:
        return None
    try:
        method = getattr(obj, method_name, None)
        return method(*args) if callable(method) else None
    except Exception:
        return None


def configure_api() -> dict[str, Any]:
    programdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    programfiles = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    root = programdata / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
    modules = root / "Modules"
    candidates = (
        programfiles / "Blackmagic Design" / "DaVinci Resolve" / "fusionscript.dll",
        programfiles / "Blackmagic Design" / "DaVinci Resolve Studio" / "fusionscript.dll",
    )
    if modules.is_dir() and str(modules) not in sys.path:
        sys.path.insert(0, str(modules))
    os.environ.setdefault("RESOLVE_SCRIPT_API", str(root))
    selected = os.environ.get("RESOLVE_SCRIPT_LIB")
    if not selected or not Path(selected).is_file():
        selected = next((str(path) for path in candidates if path.is_file()), None)
        if selected:
            os.environ["RESOLVE_SCRIPT_LIB"] = selected
    return {"modules_path": str(modules), "resolve_script_lib": selected}


def context() -> tuple[Any, Any, Any, Any, dict[str, Any] | None]:
    paths = configure_api()
    try:
        import DaVinciResolveScript as dvr
        resolve = dvr.scriptapp("Resolve")
    except Exception as exc:
        return None, None, None, None, {"ok": False, "stage": "connect", "error": f"{type(exc).__name__}: {exc}", "api_paths": paths}
    if resolve is None:
        return None, None, None, None, {"ok": False, "stage": "connect", "error": "Resolve non raggiungibile."}
    manager = safe_call(resolve, "GetProjectManager")
    project = safe_call(manager, "GetCurrentProject")
    timeline = safe_call(project, "GetCurrentTimeline") if project else None
    return resolve, manager, project, timeline, None
