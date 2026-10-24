from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import stat
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
PROTECTED_CATEGORIES = frozenset({
    "AUDIO_SOURCE",
    "AUDIO_DERIVATIVE",
    "AUDIO_MANIFEST",
    "COLORIST_STATE",
    "COLORIST_ASSET",
    "BACKUP_EVIDENCE",
    "RESOLVE_REFERENCE",
})
KNOWN_STATES = frozenset({"ACTIVE", "ELIGIBLE", "QUARANTINED", "RESTORED", "PURGED", "ERROR"})


class RegistrationLockedError(RuntimeError):
    pass


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
    purge_enabled: bool
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
    if raw.get("purge_enabled") is not False:
        raise ValueError("Il purge artefatti deve restare disabilitato")
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
    return ArtifactPolicy(str(raw["policy_version"]), quarantine_seconds, False, rules)


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
    dependencies: tuple[str, ...] = ()
    review_state: str | None = None
    hold_reasons: tuple[str, ...] = ()


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
    values["dependencies"] = tuple(str(value) for value in values.get("dependencies", ()))
    values["hold_reasons"] = tuple(str(value) for value in values.get("hold_reasons", ()))
    record = ArtifactRecord(**values)
    valid_category = (
        record.protection_class == "DISPOSABLE" and record.category in KNOWN_CATEGORIES
    ) or (
        record.protection_class == "PROTECTED" and record.category in PROTECTED_CATEGORIES
    )
    if not valid_category:
        raise ValueError("Record artefatto con categoria o protezione non valida")
    if record.kind not in {"file", "directory"} or record.state not in KNOWN_STATES:
        raise ValueError("Record artefatto con tipo o stato non valido")
    return record


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _reject_links(path: Path) -> None:
    current = path.absolute()
    while True:
        if current.exists() and (current.is_symlink() or _is_reparse(current)):
            raise ValueError("Percorso symlink o reparse non consentito")
        parent = current.parent
        if parent == current:
            return
        current = parent


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

    @property
    def registration_lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".registration.lock")

    @contextmanager
    def _registration_lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        try:
            descriptor = os.open(
                str(self.registration_lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
        except FileExistsError as exc:
            raise RegistrationLockedError(
                "registrazione artefatti bloccata; lock manuale richiesto"
            ) from exc
        try:
            os.write(descriptor, token.encode("ascii"))
            os.close(descriptor)
            descriptor = -1
            yield
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                if self.registration_lock_path.read_text(encoding="ascii") == token:
                    self.registration_lock_path.unlink()
            except OSError:
                pass

    def registration_guard(self):
        return self._registration_lock()

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
        with self._registration_lock():
            return self._register_path(
                path, kind, category, "DISPOSABLE", producer, managed_root_id,
                batch_id=batch_id, created_at=created_at, policy_version=policy_version,
            )

    def register_protected_path(
        self,
        path: Path,
        *,
        category: str,
        producer: str,
        managed_root_id: str,
        kind: Literal["file", "directory"] = "file",
        dependencies: tuple[str, ...] = (),
        review_state: str | None = None,
        hold_reasons: tuple[str, ...] = (),
        created_at: datetime | None = None,
        refresh: bool = False,
    ) -> ArtifactRecord:
        if category not in PROTECTED_CATEGORIES:
            raise ValueError("Categoria protetta non valida")
        if review_state not in {None, "PENDING", "ACCEPTED", "REJECTED"}:
            raise ValueError("Stato review artefatto non valido")
        if (any(not isinstance(value, str) or not value for value in dependencies)
                or len(set(dependencies)) != len(dependencies)
                or any(not isinstance(value, str) or not value for value in hold_reasons)):
            raise ValueError("Dipendenze o hold artefatto non validi")
        with self._registration_lock():
            return self._register_path(
                path, kind, category, "PROTECTED", producer, managed_root_id,
                created_at=created_at, dependencies=dependencies,
                review_state=review_state, hold_reasons=hold_reasons, refresh=refresh,
            )

    def _register_path(
        self,
        path: Path,
        kind: Literal["file", "directory"],
        category: str,
        protection_class: str,
        producer: str,
        managed_root_id: str,
        *,
        batch_id: str | None = None,
        created_at: datetime | None = None,
        policy_version: str | None = None,
        dependencies: tuple[str, ...] = (),
        review_state: str | None = None,
        hold_reasons: tuple[str, ...] = (),
        refresh: bool = False,
    ) -> ArtifactRecord:
        _reject_links(path)
        canonical = path.resolve(strict=True)
        if kind == "file" and not canonical.is_file():
            raise ValueError("Artefatto file non valido")
        if kind == "directory" and not canonical.is_dir():
            raise ValueError("Artefatto directory non valido")
        data = self._load()
        size = canonical.stat().st_size if kind == "file" else None
        digest = sha256_file(canonical) if kind == "file" else None
        for artifact_id, raw in data["artifacts"].items():
            existing = _record(raw)
            if existing.path == str(canonical) and existing.state != "PURGED":
                if not refresh:
                    return existing
                if existing.protection_class != "PROTECTED" or protection_class != "PROTECTED":
                    raise ValueError("Solo gli artefatti protetti possono essere aggiornati")
                updated = ArtifactRecord(
                    **{**asdict(existing), "category": category, "producer": producer,
                       "size_bytes": size, "sha256": digest,
                       "dependencies": tuple(dependencies), "review_state": review_state,
                       "hold_reasons": tuple(hold_reasons)}
                )
                data["artifacts"][artifact_id] = _record_payload(updated)
                self._save(data)
                return updated
        record = ArtifactRecord(
            artifact_id=str(uuid4()), workstation_id=self.workstation_id,
            category=category, protection_class=protection_class, kind=kind,
            path=str(canonical), managed_root_id=managed_root_id, producer=producer,
            created_at=_utc(created_at), batch_id=batch_id, size_bytes=size,
            sha256=digest, policy_version=policy_version,
            dependencies=tuple(dependencies), review_state=review_state,
            hold_reasons=tuple(hold_reasons),
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

    def pending_operation(self) -> dict[str, Any] | None:
        value = self._load().get("pending_operation")
        if value is not None and not isinstance(value, dict):
            raise ValueError("Operazione artefatto pendente non valida")
        return value

    def set_pending_operation(self, operation: dict[str, Any]) -> None:
        data = self._load()
        if data.get("pending_operation") is not None:
            raise RuntimeError("Esiste già un'operazione artefatto pendente")
        data["pending_operation"] = dict(operation)
        self._save(data)

    def clear_pending_operation(self) -> None:
        data = self._load()
        data["pending_operation"] = None
        self._save(data)


def artifact_store_for(config: CreativeConfig) -> ArtifactStore:
    return ArtifactStore(config.artifact_registry_path, config.workstation_id)
