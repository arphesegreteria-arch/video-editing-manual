from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal
from uuid import uuid4

from .config import CreativeConfig


UTC = timezone.utc
POLICY_SCHEMA_VERSION = 1
STORE_SCHEMA_VERSION = 1
KNOWN_CATEGORIES = frozenset({
    "DIAGNOSTIC_CAPTURE",
    "TEMP_REPORT",
    "TECHNICAL_PREVIEW",
    "RENDER_STAGING",
    "FAILED_RENDER_STAGING",
    "ROTATED_LOG",
})
KNOWN_STATES = frozenset({"ACTIVE", "ELIGIBLE", "QUARANTINED", "RESTORED", "PURGED", "ERROR"})


def _utc(value: datetime | None = None) -> datetime:
    selected = value or datetime.now(UTC)
    if selected.tzinfo is None:
        raise ValueError("Timestamp artefatto privo di timezone")
    return selected.astimezone(UTC)


def _text(value: datetime | None) -> str | None:
    return None if value is None else _utc(value).isoformat()


def _time(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value))
    return _utc(parsed)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class RetentionRule:
    category: str
    active_seconds: int
    terminal_batch_states: tuple[str, ...]


@dataclass(frozen=True)
class ArtifactPolicy:
    policy_version: str
    quarantine_seconds: int
    rules: dict[str, RetentionRule]


def load_artifact_policy(path: Path) -> ArtifactPolicy:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if raw.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("Versione policy artefatti non supportata")
    if not isinstance(raw.get("policy_version"), str) or not raw["policy_version"]:
        raise ValueError("policy_version artefatti non valida")
    quarantine_seconds = raw.get("quarantine_seconds")
    if quarantine_seconds != 604800:
        raise ValueError("La quarantena di produzione deve durare 604800 secondi")
    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, dict) or set(rules_raw) != KNOWN_CATEGORIES:
        raise ValueError("categorie policy artefatti non valide")
    rules: dict[str, RetentionRule] = {}
    for category, value in rules_raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"Regola categoria non valida: {category}")
        active_seconds = value.get("active_seconds")
        states = value.get("terminal_batch_states", [])
        if not isinstance(active_seconds, int) or active_seconds < 86400:
            raise ValueError(f"Retention categoria non valida: {category}")
        if not isinstance(states, list) or any(not isinstance(item, str) for item in states):
            raise ValueError(f"Stati terminali categoria non validi: {category}")
        rules[category] = RetentionRule(category, active_seconds, tuple(states))
    return ArtifactPolicy(str(raw["policy_version"]), quarantine_seconds, rules)


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    workstation_id: str
    category: str
    protection_class: str
    kind: Literal["file", "directory"]
    path: str
    managed_root_id: str
    producer: str
    created_at: datetime
    state: str = "ACTIVE"
    batch_id: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    terminal_observed_at: datetime | None = None
    eligible_at: datetime | None = None
    quarantined_at: datetime | None = None
    purge_after: datetime | None = None
    original_path: str | None = None
    quarantine_path: str | None = None
    last_error: str | None = None
    policy_version: str | None = None


@dataclass(frozen=True)
class MaintenanceState:
    last_attempt_at: datetime | None = None
    last_result: str | None = None


def _record_payload(record: ArtifactRecord) -> dict[str, Any]:
    payload = asdict(record)
    for field in ("created_at", "terminal_observed_at", "eligible_at", "quarantined_at", "purge_after"):
        payload[field] = _text(getattr(record, field))
    return payload


def _record(raw: dict[str, Any]) -> ArtifactRecord:
    values = dict(raw)
    for field in ("created_at", "terminal_observed_at", "eligible_at", "quarantined_at", "purge_after"):
        values[field] = _time(values.get(field))
    record = ArtifactRecord(**values)
    if record.category not in KNOWN_CATEGORIES or record.protection_class != "DISPOSABLE":
        raise ValueError("Record artefatto con categoria o protezione non valida")
    if record.kind not in {"file", "directory"} or record.state not in KNOWN_STATES:
        raise ValueError("Record artefatto con tipo o stato non valido")
    return record


class ArtifactStore:
    def __init__(self, path: Path, workstation_id: str):
        self.path = path.resolve()
        self.workstation_id = workstation_id

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_version": STORE_SCHEMA_VERSION,
            "workstation_id": self.workstation_id,
            "artifacts": {},
            "maintenance": {},
            "pending_operation": None,
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if data.get("schema_version") != STORE_SCHEMA_VERSION:
            raise ValueError("Versione registry artefatti non supportata")
        if data.get("workstation_id") != self.workstation_id:
            raise ValueError("Registry artefatti appartenente a un'altra workstation")
        if not isinstance(data.get("artifacts"), dict) or not isinstance(data.get("maintenance"), dict):
            raise ValueError("Registry artefatti non valido")
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

    def records(self) -> list[ArtifactRecord]:
        data = self._load()
        return [_record(value) for _, value in sorted(data["artifacts"].items())]

    def register_path(
        self,
        path: Path,
        kind: Literal["file", "directory"],
        category: str,
        producer: str,
        managed_root_id: str,
        *,
        batch_id: str | None = None,
        created_at: datetime | None = None,
        policy_version: str | None = None,
    ) -> ArtifactRecord:
        if category not in KNOWN_CATEGORIES:
            raise ValueError("Categoria artefatto non valida")
        canonical = path.resolve(strict=True)
        if kind == "file" and not canonical.is_file():
            raise ValueError("Artefatto file non valido")
        if kind == "directory" and not canonical.is_dir():
            raise ValueError("Artefatto directory non valido")
        data = self._load()
        for raw in data["artifacts"].values():
            existing = _record(raw)
            if existing.path == str(canonical) and existing.state != "PURGED":
                return existing
        size = canonical.stat().st_size if kind == "file" else None
        digest = sha256_file(canonical) if kind == "file" else None
        record = ArtifactRecord(
            artifact_id=str(uuid4()),
            workstation_id=self.workstation_id,
            category=category,
            protection_class="DISPOSABLE",
            kind=kind,
            path=str(canonical),
            managed_root_id=managed_root_id,
            producer=producer,
            created_at=_utc(created_at),
            batch_id=batch_id,
            size_bytes=size,
            sha256=digest,
            policy_version=policy_version,
        )
        data["artifacts"][record.artifact_id] = _record_payload(record)
        self._save(data)
        return record

    def replace(self, record: ArtifactRecord) -> None:
        if record.workstation_id != self.workstation_id:
            raise ValueError("Artefatto appartenente a un'altra workstation")
        data = self._load()
        if record.artifact_id not in data["artifacts"]:
            raise KeyError(record.artifact_id)
        data["artifacts"][record.artifact_id] = _record_payload(record)
        self._save(data)

    def maintenance_state(self) -> MaintenanceState:
        raw = self._load()["maintenance"]
        return MaintenanceState(_time(raw.get("last_attempt_at")), raw.get("last_result"))

    def set_maintenance_state(self, *, last_attempt_at: datetime, last_result: str) -> None:
        data = self._load()
        existing = _time(data["maintenance"].get("last_attempt_at"))
        selected = _utc(last_attempt_at)
        if existing is not None and selected < existing:
            selected = existing
        data["maintenance"] = {"last_attempt_at": _text(selected), "last_result": str(last_result)}
        self._save(data)


def artifact_store_for(config: CreativeConfig) -> ArtifactStore:
    return ArtifactStore(config.artifact_registry_path, config.workstation_id)
