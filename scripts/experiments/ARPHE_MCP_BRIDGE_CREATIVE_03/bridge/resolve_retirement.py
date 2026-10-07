from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from uuid import uuid4

from .artifact_records import sha256_file
from .config import CreativeConfig
from .resolve_connection import safe_call
from .safety import ValidationError, require_arphe_name


UTC = timezone.utc
SCHEMA_VERSION = 1
ALLOWED_KINDS = {"timeline", "project"}
ALLOWED_STATES = {"PREPARED", "APPROVED", "EXECUTING", "EXECUTED", "RECOVERED"}
TECHNICAL_ROLES = {"technical", "alessio"}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp retirement privo di timezone")
    return value.astimezone(UTC)


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(record: dict[str, Any]) -> str:
    keys = (
        "retirement_id", "workstation_id", "kind", "project_name", "timeline_name",
        "archive_name", "archive_sha256", "archive_size_bytes", "created_at",
        "project_last_modified",
    )
    return hashlib.sha256(_canonical({key: record.get(key) for key in keys}).encode("utf-8")).hexdigest()


class ResolveRetirementStore:
    def __init__(self, path: Path, workstation_id: str):
        self.path = path.resolve()
        self.workstation_id = workstation_id

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "workstation_id": self.workstation_id,
                "retirements": {}}

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Versione registry retirement non supportata")
        if data.get("workstation_id") != self.workstation_id:
            raise ValueError("Registry retirement appartenente a un'altra workstation")
        if not isinstance(data.get("retirements"), dict):
            raise ValueError("Registry retirement non valido")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def add(self, record: dict[str, Any]) -> None:
        if record.get("workstation_id") != self.workstation_id:
            raise ValueError("Retirement appartenente a un'altra workstation")
        data = self._load()
        identifier = str(record["retirement_id"])
        if identifier in data["retirements"]:
            raise ValueError("Retirement ID duplicato")
        data["retirements"][identifier] = dict(record)
        self._save(data)

    def get(self, retirement_id: str) -> dict[str, Any]:
        record = self._load()["retirements"].get(retirement_id)
        if record is None:
            raise ValidationError("Retirement non trovato")
        if record.get("status") not in ALLOWED_STATES:
            raise ValueError("Stato retirement non valido")
        return dict(record)

    def replace(self, record: dict[str, Any]) -> None:
        if record.get("workstation_id") != self.workstation_id:
            raise ValueError("Retirement appartenente a un'altra workstation")
        data = self._load()
        identifier = str(record["retirement_id"])
        if identifier not in data["retirements"]:
            raise KeyError(identifier)
        data["retirements"][identifier] = dict(record)
        self._save(data)

    def records(self) -> list[dict[str, Any]]:
        return [dict(value) for value in self._load()["retirements"].values()]


def retirement_store_for(config: CreativeConfig) -> ResolveRetirementStore:
    return ResolveRetirementStore(config.resolve_retirement_registry_path, config.workstation_id)


def _timeline(project: Any, name: str) -> Any | None:
    count = int(safe_call(project, "GetTimelineCount") or 0)
    for index in range(1, count + 1):
        candidate = safe_call(project, "GetTimelineByIndex", index)
        if str(safe_call(candidate, "GetName") or "") == name:
            return candidate
    return None


def _require_project(manager: Any, project: Any, project_name: str, config: CreativeConfig,
                     registry: Any) -> None:
    require_arphe_name(project_name, "progetto")
    if project is None or str(safe_call(project, "GetName") or "") != project_name:
        raise ValidationError("Il progetto target deve essere il progetto Resolve corrente")
    if not (registry.project_allowed(project_name) or project_name in config.allowed_projects):
        raise ValidationError("Progetto non registrato o allowlisted")
    if project_name not in list(safe_call(manager, "GetProjectListInCurrentFolder") or []):
        raise ValidationError("Progetto non presente nella cartella Resolve corrente")
    if registry.render_lock(project_name):
        raise ValidationError("Progetto protetto da un render batch attivo")


def _project_last_modified(manager: Any, project_name: str) -> int | str:
    value = safe_call(manager, "GetProjectLastModifiedTime", project_name)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    attributes = safe_call(manager, "GetProjectAttributesInCurrentFolder")
    if isinstance(attributes, dict):
        project_attributes = attributes.get(project_name)
        if isinstance(project_attributes, dict):
            fallback = project_attributes.get("lastModifiedDate")
            if isinstance(fallback, str) and fallback.strip():
                return fallback.strip()
    raise RuntimeError("Last-modified progetto non leggibile")


def _archive_path(config: CreativeConfig, project_name: str, retirement_id: str,
                  now: datetime) -> Path:
    safe_project = re.sub(r"[^A-Za-z0-9_-]+", "_", project_name)[:64]
    root = config.resolve_archive_root.resolve()
    directory = root / safe_project
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{now.strftime('%Y%m%dT%H%M%SZ')}_{retirement_id}.drp"


def _validate_archive(config: CreativeConfig, record: dict[str, Any]) -> Path:
    root = config.resolve_archive_root.resolve()
    path = Path(str(record["archive_path"])).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError("Archivio fuori dalla radice Resolve gestita") from exc
    if not path.is_file() or path.stat().st_size != int(record["archive_size_bytes"]):
        raise ValidationError("Archivio Resolve assente o con dimensione diversa")
    if sha256_file(path) != record["archive_sha256"]:
        raise ValidationError("Hash archivio Resolve non valido")
    return path


def prepare_retirement(manager: Any, project: Any, config: CreativeConfig, registry: Any,
                       store: ResolveRetirementStore, kind: str, project_name: str,
                       timeline_name: str | None, now: datetime) -> dict[str, Any]:
    selected_now = _utc(now)
    if kind not in ALLOWED_KINDS:
        raise ValidationError("Tipo retirement non valido")
    _require_project(manager, project, project_name, config, registry)
    if kind == "timeline":
        require_arphe_name(str(timeline_name or ""), "timeline")
        if not (registry.timeline_allowed(project_name, str(timeline_name)) or
                str(timeline_name) in config.allowed_timelines):
            raise ValidationError("Timeline non registrata o allowlisted")
        target = _timeline(project, str(timeline_name))
        if target is None:
            raise ValidationError("Timeline target non trovata")
        current = safe_call(project, "GetCurrentTimeline")
        if current is target or str(safe_call(current, "GetName") or "") == timeline_name:
            raise ValidationError("Selezionare un'altra timeline prima del retirement")
    elif timeline_name not in (None, ""):
        raise ValidationError("timeline_name non ammesso per retirement progetto")
    if not safe_call(manager, "SaveProject"):
        raise RuntimeError("Salvataggio progetto fallito")
    retirement_id = str(uuid4())
    archive = _archive_path(config, project_name, retirement_id, selected_now)
    if archive.exists():
        raise RuntimeError("Collisione archivio Resolve")
    if not safe_call(manager, "ExportProject", project_name, str(archive), True):
        if archive.is_file():
            archive.unlink()
        raise RuntimeError("ExportProject fallito")
    if not archive.is_file() or archive.stat().st_size <= 0:
        raise RuntimeError("Archivio .drp assente o vuoto")
    modified = _project_last_modified(manager, project_name)
    record = {
        "retirement_id": retirement_id,
        "workstation_id": config.workstation_id,
        "kind": kind,
        "project_name": project_name,
        "timeline_name": timeline_name,
        "archive_path": str(archive.resolve()),
        "archive_name": archive.name,
        "archive_sha256": sha256_file(archive),
        "archive_size_bytes": archive.stat().st_size,
        "created_at": selected_now.isoformat(),
        "project_last_modified": modified,
        "status": "PREPARED",
        "approved_at": None,
        "approved_by": None,
        "executed_at": None,
        "recovered_at": None,
        "recovery_project": None,
    }
    record["fingerprint"] = _fingerprint(record)
    store.add(record)
    return {"ok": True, "action": "prepare_resolve_retirement", "retirement_id": retirement_id,
            "status": "PREPARED", "kind": kind, "project_name": project_name,
            "timeline_name": timeline_name, "archive_name": archive.name,
            "archive_sha256": record["archive_sha256"], "fingerprint": record["fingerprint"],
            "removal_performed": False}


def approve_retirement(store: ResolveRetirementStore, retirement_id: str, operator_role: str,
                       now: datetime) -> dict[str, Any]:
    record = store.get(retirement_id)
    if record["status"] == "APPROVED":
        return {"ok": True, "action": "approve_resolve_retirement",
                "retirement_id": retirement_id, "status": "APPROVED", "idempotent": True}
    if record["status"] != "PREPARED":
        raise ValidationError("Retirement non approvabile nello stato corrente")
    role = str(operator_role).strip().casefold()
    if role not in TECHNICAL_ROLES:
        raise ValidationError("Approvazione riservata ad Alessio o personale tecnico")
    if record.get("fingerprint") != _fingerprint(record):
        raise ValidationError("Fingerprint retirement non valido")
    record.update(status="APPROVED", approved_at=_utc(now).isoformat(), approved_by=role)
    store.replace(record)
    return {"ok": True, "action": "approve_resolve_retirement",
            "retirement_id": retirement_id, "status": "APPROVED",
            "fingerprint": record["fingerprint"]}


def _finalize(store: ResolveRetirementStore, record: dict[str, Any], registry: Any,
              now: datetime) -> dict[str, Any]:
    if record["kind"] == "timeline":
        registry.remove_timeline(record["project_name"], record["timeline_name"])
    else:
        registry.remove_project(record["project_name"])
    record.update(status="EXECUTED", executed_at=_utc(now).isoformat())
    store.replace(record)
    return {"ok": True, "action": "execute_resolve_retirement",
            "retirement_id": record["retirement_id"], "status": "EXECUTED",
            "archive_name": record["archive_name"], "recoverable": True}


def execute_retirement(manager: Any, project: Any, config: CreativeConfig, registry: Any,
                       store: ResolveRetirementStore, retirement_id: str,
                       now: datetime) -> dict[str, Any]:
    record = store.get(retirement_id)
    if record["status"] in {"EXECUTED", "RECOVERED"}:
        return {"ok": True, "action": "execute_resolve_retirement",
                "retirement_id": retirement_id, "status": record["status"], "idempotent": True}
    if record["status"] not in {"APPROVED", "EXECUTING"}:
        raise ValidationError("Retirement privo di approvazione")
    if record.get("fingerprint") != _fingerprint(record):
        raise ValidationError("Fingerprint retirement non valido")
    _validate_archive(config, record)
    if registry.render_lock(record["project_name"]):
        raise ValidationError("Progetto protetto da un render batch attivo")
    projects = list(safe_call(manager, "GetProjectListInCurrentFolder") or [])
    if record["kind"] == "project" and record["project_name"] not in projects:
        if record["status"] == "EXECUTING":
            return _finalize(store, record, registry, now)
        raise ValidationError("Progetto target non trovato")
    if record["kind"] == "timeline":
        if project is None or str(safe_call(project, "GetName") or "") != record["project_name"]:
            raise ValidationError("Il progetto target deve essere corrente")
        target = _timeline(project, record["timeline_name"])
        if target is None and record["status"] == "EXECUTING":
            return _finalize(store, record, registry, now)
        if target is None:
            raise ValidationError("Timeline target non trovata")
        current = safe_call(project, "GetCurrentTimeline")
        if current is target or str(safe_call(current, "GetName") or "") == record["timeline_name"]:
            raise ValidationError("Selezionare un'altra timeline prima del retirement")
    modified = _project_last_modified(manager, record["project_name"])
    if modified != record["project_last_modified"]:
        raise ValidationError("Progetto modificato dopo l'archivio; preparare una nuova proposta")
    if record["status"] == "APPROVED":
        record["status"] = "EXECUTING"
        store.replace(record)
    if record["kind"] == "timeline":
        pool = safe_call(project, "GetMediaPool")
        if pool is None or not safe_call(pool, "DeleteTimelines", [target]):
            raise RuntimeError("DeleteTimelines fallito")
        if _timeline(project, record["timeline_name"]) is not None:
            raise RuntimeError("Verifica post-delete timeline fallita")
        if not safe_call(manager, "SaveProject"):
            raise RuntimeError("Salvataggio post-delete fallito")
    else:
        current_project = safe_call(manager, "GetCurrentProject")
        if current_project is not None and str(safe_call(current_project, "GetName") or "") == record["project_name"]:
            if not safe_call(manager, "CloseProject", current_project):
                raise RuntimeError("CloseProject fallito")
        if not safe_call(manager, "DeleteProject", record["project_name"]):
            safe_call(manager, "LoadProject", record["project_name"])
            raise RuntimeError("DeleteProject fallito; tentato ripristino progetto corrente")
        if record["project_name"] in list(safe_call(manager, "GetProjectListInCurrentFolder") or []):
            raise RuntimeError("Verifica post-delete progetto fallita")
    return _finalize(store, record, registry, now)


def recover_retirement(manager: Any, config: CreativeConfig, store: ResolveRetirementStore,
                       retirement_id: str, now: datetime) -> dict[str, Any]:
    record = store.get(retirement_id)
    if record["status"] == "RECOVERED":
        return {"ok": True, "action": "recover_resolve_retirement",
                "retirement_id": retirement_id, "status": "RECOVERED",
                "recovery_project": record["recovery_project"], "idempotent": True}
    if record["status"] != "EXECUTED":
        raise ValidationError("Recovery consentito solo dopo un retirement eseguito")
    archive = _validate_archive(config, record)
    suffix = retirement_id.replace("-", "")[:8]
    timestamp = _utc(now).strftime("%Y%m%dT%H%M%SZ")
    prefix = "ARPHE_RECOVERY_"
    fixed_length = len(prefix) + 1 + len(timestamp) + 1 + len(suffix)
    original = re.sub(r"[^A-Za-z0-9_-]+", "_", record["project_name"])[6:]
    original = original[:64 - fixed_length]
    recovery_name = f"{prefix}{original}_{timestamp}_{suffix}"
    if recovery_name in list(safe_call(manager, "GetProjectListInCurrentFolder") or []):
        raise ValidationError("Nome progetto recovery già esistente")
    if not safe_call(manager, "ImportProject", str(archive), recovery_name):
        raise RuntimeError("ImportProject recovery fallito")
    if recovery_name not in list(safe_call(manager, "GetProjectListInCurrentFolder") or []):
        raise RuntimeError("Verifica progetto recovery fallita")
    record.update(status="RECOVERED", recovered_at=_utc(now).isoformat(),
                  recovery_project=recovery_name)
    store.replace(record)
    return {"ok": True, "action": "recover_resolve_retirement",
            "retirement_id": retirement_id, "status": "RECOVERED",
            "recovery_project": recovery_name, "original_untouched": True}


def inspect_retirements(config: CreativeConfig, store: ResolveRetirementStore,
                        now: datetime) -> dict[str, Any]:
    selected_now = _utc(now)
    records = sorted(store.records(), key=lambda item: item["created_at"], reverse=True)
    rank: dict[str, int] = {}
    items = []
    for record in records:
        project = record["project_name"]
        rank[project] = rank.get(project, 0) + 1
        created = datetime.fromisoformat(record["created_at"]).astimezone(UTC)
        retain = rank[project] <= 3 or selected_now - created <= timedelta(days=30)
        items.append({
            "retirement_id": record["retirement_id"], "kind": record["kind"],
            "project_name": project, "timeline_name": record.get("timeline_name"),
            "status": record["status"], "archive_name": record["archive_name"],
            "archive_sha256": record["archive_sha256"],
            "created_at": record["created_at"],
            "archive_retention": "RETAIN" if retain else "CANDIDATE",
        })
    return {"ok": True, "action": "inspect_resolve_retirements",
            "workstation_id": config.workstation_id, "items": items,
            "policy": {"retain_days": 30, "retain_latest_per_project": 3,
                       "automatic_delete": False}}
