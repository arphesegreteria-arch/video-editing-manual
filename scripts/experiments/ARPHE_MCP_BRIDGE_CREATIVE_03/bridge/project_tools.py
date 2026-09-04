from __future__ import annotations

from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name, ensure_no_collision, require_arphe_name


def project_names(manager: Any) -> list[str]:
    result = safe_call(manager, "GetProjectListInCurrentFolder") or []
    return [str(value) for value in result]


def create_project(manager: Any, config: CreativeConfig, registry: Registry, requested: str) -> dict:
    require_capability("CAP_PROJECT", config, manager, None, None)
    name = arphe_name(requested, "CREATIVE")
    existing = project_names(manager)
    ensure_no_collision(name, existing, "Progetto")
    previous = safe_call(manager, "GetCurrentProject")
    previous_name = safe_call(previous, "GetName")
    created = safe_call(manager, "CreateProject", name)
    if not created:
        return {"ok": False, "action": "create_project", "stage": "create", "requested": name, "previous_project": previous_name}
    created_name = safe_call(created, "GetName")
    current = safe_call(manager, "GetCurrentProject")
    current_name = safe_call(current, "GetName")
    ok = created_name == name and current_name == name
    if ok:
        registry.add_project(name)
    return {"ok": ok, "action": "create_project", "previous_project": previous_name,
            "created_project": created_name, "current_project": current_name, "overwrite": False}


def set_current_project(manager: Any, config: CreativeConfig, registry: Registry, project_name: str) -> dict:
    require_capability("CAP_PROJECT", config, manager, None, None)
    name = require_arphe_name(project_name, "project_name")
    if not (registry.project_allowed(name) or name in config.allowed_projects):
        raise ValidationError("Progetto non creato/allowlisted dal bridge")
    previous = safe_call(manager, "GetCurrentProject")
    loaded = safe_call(manager, "LoadProject", name)
    current = safe_call(manager, "GetCurrentProject")
    current_name = safe_call(current, "GetName")
    return {"ok": loaded is not None and current_name == name, "action": "set_current_project",
            "previous_project": safe_call(previous, "GetName"), "current_project": current_name}


def save_project(manager: Any, project: Any, config: CreativeConfig, registry: Registry) -> dict:
    require_capability("CAP_PROJECT", config, manager, project, safe_call(project, "GetCurrentTimeline"))
    name = safe_call(project, "GetName")
    require_arphe_name(name, "progetto corrente")
    if not (registry.project_allowed(name) or name in config.allowed_projects):
        raise ValidationError("Salvataggio consentito solo per progetti registrati/allowlisted")
    saved = bool(safe_call(manager, "SaveProject"))
    return {"ok": saved, "action": "save_project", "project": name}
