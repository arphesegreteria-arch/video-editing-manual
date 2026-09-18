from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, require_arphe_name


def _timeline_map(project: Any) -> dict[str, Any]:
    count = int(safe_call(project, "GetTimelineCount") or 0)
    result = {}
    for index in range(1, count + 1):
        timeline = safe_call(project, "GetTimelineByIndex", index)
        name = str(safe_call(timeline, "GetName") or "")
        if timeline and name:
            result[name] = timeline
    return result


def _allowed_file(path: Path, config: CreativeConfig) -> bool:
    roots = [*config.media_roots, config.audio_root, Path.home() / "Desktop",
             Path.home() / "OneDrive" / "Desktop"]
    return any(path == root.resolve() or root.resolve() in path.parents for root in roots)


def _canonical(project_name: str, projects: list[str], timelines: list[str], files: list[str]) -> str:
    payload = {"project": project_name, "projects": sorted(projects),
               "timelines": sorted(timelines), "files": sorted(files)}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def preview_publish_cleanup(manager: Any, project: Any, config: CreativeConfig, registry: Registry,
                            keep_timeline_names: list[str], candidate_timeline_names: list[str],
                            candidate_project_names: list[str], candidate_file_paths: list[str]) -> dict:
    """Return an exact, non-destructive cleanup plan and its confirmation token."""
    project_name = str(safe_call(project, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    if not registry.project_allowed(project_name) and project_name not in config.allowed_projects:
        raise ValidationError("Il progetto corrente non è gestito dal bridge")
    if len(set(keep_timeline_names)) != len(keep_timeline_names):
        raise ValidationError("Timeline da conservare duplicate")
    if len(set(candidate_timeline_names)) != len(candidate_timeline_names):
        raise ValidationError("Timeline candidate duplicate")
    if set(keep_timeline_names) & set(candidate_timeline_names):
        raise ValidationError("Una timeline non può essere conservata e rimossa insieme")
    if len(set(candidate_project_names)) != len(candidate_project_names):
        raise ValidationError("Progetti candidati duplicati")
    known_projects = set(safe_call(manager, "GetProjectListInCurrentFolder") or [])
    for name in candidate_project_names:
        require_arphe_name(name, "progetto")
        if name == project_name:
            raise ValidationError("Il progetto corrente non può essere rimosso")
        if name not in known_projects or not registry.project_allowed(name):
            raise ValidationError(f"Progetto non disponibile o non registrato: {name}")
    available = _timeline_map(project)
    missing_keep = [name for name in keep_timeline_names if name not in available]
    if missing_keep:
        raise ValidationError("Timeline da conservare mancanti: " + ", ".join(missing_keep))
    for name in candidate_timeline_names:
        require_arphe_name(name, "timeline")
        if name not in available or not registry.timeline_allowed(project_name, name):
            raise ValidationError(f"Timeline non disponibile o non registrata: {name}")
    current_name = str(safe_call(safe_call(project, "GetCurrentTimeline"), "GetName") or "")
    if current_name in candidate_timeline_names:
        raise ValidationError("La timeline corrente non può essere rimossa")
    if len(candidate_timeline_names) >= len(available):
        raise ValidationError("La pulizia deve lasciare almeno una timeline")
    files = []
    for raw in candidate_file_paths:
        path = Path(raw).expanduser().resolve(strict=True)
        if not path.is_file() or not _allowed_file(path, config):
            raise ValidationError(f"File non consentito: {raw}")
        files.append({"path": str(path), "bytes": path.stat().st_size})
    normalized_files = [item["path"] for item in files]
    token = _canonical(project_name, candidate_project_names, candidate_timeline_names, normalized_files)
    return {"ok": True, "action": "preview_publish_cleanup", "project": project_name,
            "keep_timelines": keep_timeline_names, "candidate_timelines": candidate_timeline_names,
            "candidate_projects": candidate_project_names,
            "candidate_files": files, "reclaimable_bytes": sum(item["bytes"] for item in files),
            "confirmation_token": token, "writes_performed": False}


def apply_publish_cleanup(manager: Any, project: Any, config: CreativeConfig, registry: Registry,
                          keep_timeline_names: list[str], candidate_timeline_names: list[str],
                          candidate_project_names: list[str], candidate_file_paths: list[str],
                          confirmation_token: str) -> dict:
    """Apply a previewed plan, deleting timelines and moving files to the recycle bin."""
    require_capability("CAP_CLEANUP", config, manager, project, safe_call(project, "GetCurrentTimeline"))
    preview = preview_publish_cleanup(manager, project, config, registry, keep_timeline_names,
                                      candidate_timeline_names, candidate_project_names,
                                      candidate_file_paths)
    if confirmation_token != preview["confirmation_token"]:
        raise ValidationError("Conferma pulizia non valida o piano modificato")
    pool = safe_call(project, "GetMediaPool")
    timelines = _timeline_map(project)
    targets = [timelines[name] for name in candidate_timeline_names]
    if targets and not bool(safe_call(pool, "DeleteTimelines", targets)):
        raise RuntimeError("Resolve ha rifiutato la rimozione delle timeline")
    for name in candidate_timeline_names:
        registry.remove_timeline(preview["project"], name)
    deleted_projects = []
    for name in candidate_project_names:
        if not bool(safe_call(manager, "DeleteProject", name)):
            raise RuntimeError(f"Resolve ha rifiutato la rimozione del progetto: {name}")
        registry.remove_project(name)
        deleted_projects.append(name)
    recycled = []
    for item in preview["candidate_files"]:
        _send_to_recycle_bin(Path(item["path"]))
        recycled.append(item["path"])
    saved = bool(safe_call(manager, "SaveProject"))
    return {"ok": saved, "action": "apply_publish_cleanup", "project": preview["project"],
            "deleted_timelines": candidate_timeline_names, "recycled_files": recycled,
            "deleted_projects": deleted_projects,
            "reclaimed_bytes": preview["reclaimable_bytes"], "project_saved": saved}


def _send_to_recycle_bin(path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 3
    operation.pFrom = str(path) + "\0\0"
    operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise RuntimeError(f"Invio al Cestino fallito: {path}")
