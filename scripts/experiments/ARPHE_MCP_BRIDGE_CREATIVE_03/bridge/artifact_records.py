from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import tempfile
import stat
import threading
from typing import Any, Literal
from uuid import UUID, uuid4

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
KNOWN_STATES = frozenset({"ACTIVE", "ELIGIBLE", "QUARANTINE_COPYING", "QUARANTINED",
                          "PURGE_PENDING", "RESTORED", "PURGED", "ERROR", "REVIEW_REQUIRED"})


class ProducerId(str, Enum):
    CAPTURE_TIMELINE_FRAMES = "capture_timeline_frames"
    PREPARE_RENDER_BATCH = "prepare_render_batch"
    RENDER_PREVIEW = "render_preview"
    APPLY_FREEZE_SBAM = "apply_freeze_sbam"
    AUDIO_WORKER = "audio_worker"
    TIMELINE_DIALOGUE_CLEANUP = "timeline_dialogue_cleanup"
    COLORIST_JOB_STORE = "colorist_job_store"
    WINDOWS_RUNTIME_LOG_ROTATION = "windows_runtime_log_rotation"


def _producer_id(value: str) -> str:
    try:
        return ProducerId(value).value
    except (ValueError, TypeError) as exc:
        raise ValueError("Unknown producer ID") from exc


def _project_uuid(value: str) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value or UUID(value).int == 0:
            raise ValueError
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Project ID must be a canonical non-nil UUID") from exc
    return value


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


def artifact_signature(path: Path, kind: str) -> tuple[int, str, tuple[str, ...]]:
    """The single frozen-payload signature used by registration, hygiene, and holds."""
    if kind == "file":
        return path.stat().st_size, sha256_file(path), (path.name,)
    if kind != "directory" or not path.is_dir():
        raise ValueError("Artifact identity cannot be verified")
    total = 0
    digest = hashlib.sha256()
    names: list[str] = []
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix().casefold()):
        if item.is_symlink() or _is_reparse(item):
            raise ValueError("Contenuto symlink o reparse non consentito")
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError("Contenuto staging non regolare")
        relative = item.relative_to(path).as_posix()
        size = item.stat().st_size
        file_digest = sha256_file(item)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        names.append(relative)
        total += size
    return total, digest.hexdigest(), tuple(names)


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
    if type(quarantine_seconds) is not int or quarantine_seconds != 1296000:
        raise ValueError("La quarantena di produzione deve durare 1296000 secondi")
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
    project_id: str | None = None
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
    def __init__(self, path: Path, workstation_id: str,
                 managed_roots: dict[str, Path] | None = None):
        self.path = path.resolve()
        self.workstation_id = workstation_id
        self._registration_owner: tuple[int, str] | None = None
        self.managed_roots = {
            key: value.resolve() for key, value in (managed_roots or {}).items()
        }

    def _empty(self) -> dict[str, Any]:
        return {
            "schema_version": STORE_SCHEMA_VERSION,
            "workstation_id": self.workstation_id,
            "artifacts": {},
            "artifact_projects": {},
            "maintenance": {},
            "pending_operation": None,
            "retention_events": [],
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
        events = data.setdefault("retention_events", [])
        if not isinstance(events, list):
            raise ValueError("Registro eventi retention non valido")
        for event in events:
            if not isinstance(event, dict) or set(event) != {"action", "timestamp", "workstation_id", "artifact_id", "pre_state", "post_state", "restore_performed", "code"}:
                raise ValueError("Evento retention non valido")
            if (event["action"] not in {"KEEP", "RELEASE", "KEEP_REFUSED"}
                    or event["workstation_id"] != self.workstation_id
                    or not isinstance(event["artifact_id"], str)
                    or event["pre_state"] not in KNOWN_STATES
                    or event["post_state"] not in KNOWN_STATES
                    or type(event["restore_performed"]) is not bool
                    or not isinstance(event["code"], str) or not event["code"]):
                raise ValueError("Evento retention non valido")
            if _time(event["timestamp"]) is None:
                raise ValueError("Timestamp evento retention non valido")
        projects = data.setdefault("artifact_projects", {})
        if not isinstance(projects, dict):
            raise ValueError("Invalid artifact project ledger")
        for project_id, binding in projects.items():
            _project_uuid(project_id)
            if binding != {"project_id": project_id, "workstation_id": self.workstation_id}:
                raise ValueError("Conflicting artifact project ownership")
        for raw in data["artifacts"].values():
            if not isinstance(raw, dict):
                raise ValueError("Invalid artifact record")
            project_id = raw.get("project_id")
            if project_id is not None:
                _project_uuid(project_id)
                if project_id not in projects or raw.get("workstation_id") != self.workstation_id:
                    raise ValueError("Persisted artifact project binding is missing or foreign")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
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
            self._registration_owner = (threading.get_ident(), token)
            yield
        finally:
            self._registration_owner = None
            if descriptor >= 0:
                os.close(descriptor)
            try:
                if self.registration_lock_path.read_text(encoding="ascii") == token:
                    self.registration_lock_path.unlink()
            except OSError:
                pass

    def registration_guard(self):
        return self._registration_lock()

    def owns_registration_guard(self) -> bool:
        """True only for this instance's live guard on the calling thread."""
        owner = self._registration_owner
        if owner is None or owner[0] != threading.get_ident():
            return False
        try:
            _reject_links(self.registration_lock_path)
            return self.registration_lock_path.read_text(encoding="ascii") == owner[1]
        except (OSError, ValueError):
            return False

    def records(self) -> list[ArtifactRecord]:
        data = self._load()
        return [_record(value) for _, value in sorted(data["artifacts"].items())]

    def bind_project(self, project_id: str) -> str:
        """Persist Resolve's UUID before creating outputs; never derive it from a name."""
        project_id = _project_uuid(project_id)
        with self.registration_guard():
            data = self._load()
            binding = {"project_id": project_id, "workstation_id": self.workstation_id}
            if project_id not in data["artifact_projects"]:
                data["artifact_projects"][project_id] = binding
                self._save(data)
        return project_id

    def register_produced_path(
        self, path: Path, *, project_id: str, category: str, protection_class: str,
        producer: ProducerId | str, managed_root_id: str,
        kind: Literal["file", "directory"] = "file", artifact_id: str | None = None,
        batch_id: str | None = None, hold_reasons: tuple[str, ...] = (),
    ) -> ArtifactRecord:
        """Only known local projects and exact producer identities can claim outputs."""
        project_id = _project_uuid(project_id)
        producer = _producer_id(producer)
        valid = ((protection_class == "DISPOSABLE" and category in KNOWN_CATEGORIES)
                 or (protection_class == "PROTECTED" and category in PROTECTED_CATEGORIES))
        if not valid or kind not in {"file", "directory"}:
            raise ValueError("Invalid produced artifact category, protection or kind")
        if managed_root_id not in self.managed_roots:
            raise ValueError("Unknown managed root")
        if any(not isinstance(value, str) or not value for value in hold_reasons):
            raise ValueError("Invalid artifact hold")
        # Publication may already own this exact store's live guard. A foreign
        # instance/thread or a stale token still takes the ordinary lock path.
        guard = nullcontext() if self.owns_registration_guard() else self.registration_guard()
        with guard:
            data = self._load()
            if project_id not in data["artifact_projects"]:
                raise ValueError("Unknown project ID")
            return self._register_path(
                path, kind, category, protection_class, producer, managed_root_id,
                batch_id=batch_id, hold_reasons=hold_reasons,
                project_id=project_id, artifact_id=artifact_id,
                refresh=protection_class == "PROTECTED",
            )

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
            raise ValueError("Categoria disposable non valida")
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
        refresh: bool = True,
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

    def register_protected_bundle(self, specs: tuple[dict[str, Any], ...]) -> tuple[ArtifactRecord, ...]:
        """Register a complete protected bundle under one fail-closed lock."""
        records: list[ArtifactRecord] = []
        with self._registration_lock():
            for spec in specs:
                category = str(spec["category"])
                if category not in PROTECTED_CATEGORIES:
                    raise ValueError("Categoria protetta non valida")
                records.append(self._register_path(
                    Path(spec["path"]), str(spec.get("kind", "file")), category,
                    "PROTECTED", spec["producer"], str(spec["managed_root_id"]),
                    dependencies=tuple(spec.get("dependencies", ())),
                    review_state=spec.get("review_state"),
                    hold_reasons=tuple(spec.get("hold_reasons", ())), refresh=True,
                ))
        return tuple(records)

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
        project_id: str | None = None,
        artifact_id: str | None = None,
    ) -> ArtifactRecord:
        producer = _producer_id(producer)
        if protection_class == "DISPOSABLE" and category not in KNOWN_CATEGORIES:
            raise ValueError("Categoria disposable non valida")
        if protection_class == "PROTECTED" and category not in PROTECTED_CATEGORIES:
            raise ValueError("Categoria protetta non valida")
        _reject_links(path)
        canonical = path.resolve(strict=True)
        if self.managed_roots:
            root = self.managed_roots.get(managed_root_id)
            if root is None:
                raise ValueError("Radice gestita sconosciuta")
            _reject_links(root)
            try:
                canonical.relative_to(root.resolve(strict=True))
            except ValueError as exc:
                raise ValueError("Artefatto fuori dalla radice gestita") from exc
        if kind == "file" and not canonical.is_file():
            raise ValueError("Artefatto file non valido")
        if kind == "directory" and not canonical.is_dir():
            raise ValueError("Artefatto directory non valido")
        data = self._load()
        size, digest, _ = artifact_signature(canonical, kind)
        if artifact_id is not None:
            raw = data["artifacts"].get(artifact_id)
            if raw is None or raw.get("artifact_id") != artifact_id or raw.get("path") != str(canonical):
                raise ValueError("Unknown or mismatched artifact identity")
        for stored_id, raw in data["artifacts"].items():
            existing = _record(raw)
            if existing.path == str(canonical) and existing.state != "PURGED":
                if existing.workstation_id != self.workstation_id or existing.artifact_id != stored_id:
                    raise ValueError("Artifact belongs to another workstation or identity")
                if project_id is not None or existing.project_id is not None:
                    if (existing.project_id != project_id or existing.producer != producer
                            or existing.managed_root_id != managed_root_id or existing.kind != kind
                            or existing.batch_id != batch_id
                            or (artifact_id is not None and existing.artifact_id != artifact_id)):
                        raise ValueError("Artifact project, producer or path identity mismatch")
                    if existing.state not in {"ACTIVE", "RESTORED", "ELIGIBLE"}:
                        raise ValueError("Artifact state does not permit producer registration")
                    if existing.protection_class == "PROTECTED" and protection_class != "PROTECTED":
                        raise ValueError("Cannot downgrade artifact protection")
                    if existing.protection_class == protection_class and existing.category != category:
                        raise ValueError("Cannot change artifact category")
                    hold_reasons = tuple(dict.fromkeys((*existing.hold_reasons, *hold_reasons)))
                    dependencies = tuple(dict.fromkeys((*existing.dependencies, *dependencies)))
                if not refresh and not (
                    existing.protection_class == "DISPOSABLE" and protection_class == "PROTECTED"
                ):
                    return existing
                if protection_class != "PROTECTED":
                    raise ValueError("Solo gli artefatti protetti possono essere aggiornati")
                updated = ArtifactRecord(
                    **{**asdict(existing), "category": category,
                       "protection_class": "PROTECTED", "producer": producer,
                       "managed_root_id": managed_root_id, "state": "ACTIVE",
                       "size_bytes": size, "sha256": digest,
                       "dependencies": tuple(dependencies), "review_state": review_state,
                       "hold_reasons": tuple(hold_reasons)}
                )
                data["artifacts"][stored_id] = _record_payload(updated)
                self._save(data)
                return updated
        if artifact_id is not None:
            raise ValueError("Artifact identity cannot be reused")
        record = ArtifactRecord(
            project_id=project_id, artifact_id=str(uuid4()), workstation_id=self.workstation_id,
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

    def _hold_target(self, data: dict[str, Any], artifact_id: str) -> ArtifactRecord:
        if (not isinstance(artifact_id, str) or not artifact_id or Path(artifact_id).name != artifact_id
                or artifact_id in {".", ".."}):
            raise ValueError("Invalid artifact identity")
        raw = data["artifacts"].get(artifact_id)
        if raw is None:
            raise ValueError("Unknown artifact identity")
        record = _record(raw)
        if record.workstation_id != self.workstation_id:
            raise ValueError("Artifact workstation mismatch")
        if record.managed_root_id not in self.managed_roots:
            raise ValueError("Unknown managed root")
        path = Path(record.path)
        root = self.managed_roots[record.managed_root_id]
        _reject_links(root)
        _reject_links(path)
        canonical = path.resolve(strict=True)
        try:
            canonical.relative_to(root.resolve(strict=True))
        except ValueError as exc:
            raise ValueError("Artifact outside managed root") from exc
        size, digest, _ = artifact_signature(canonical, record.kind)
        if size != record.size_bytes or digest != record.sha256:
            raise ValueError("Artifact content changed")
        return record

    def _event(self, action: str, record: ArtifactRecord, updated: ArtifactRecord,
               now: datetime, *, restore_performed: bool = False, code: str = "OK") -> dict[str, Any]:
        return {"action": action, "timestamp": _text(now), "workstation_id": self.workstation_id,
                "artifact_id": record.artifact_id, "pre_state": record.state,
                "post_state": updated.state, "restore_performed": restore_performed, "code": code}

    def keep_artifact(self, artifact_id: str, now_utc: datetime) -> ArtifactRecord:
        now = _utc(now_utc)
        with self.registration_guard():
            data = self._load()
            try:
                record = self._hold_target(data, artifact_id)
            except ValueError:
                raw = data["artifacts"].get(artifact_id) if isinstance(artifact_id, str) else None
                if isinstance(raw, dict):
                    record = _record(raw)
                    if record.workstation_id == self.workstation_id:
                        data["retention_events"].append(self._event(
                            "KEEP_REFUSED", record, record, now, code="IDENTITY_REFUSED"))
                        self._save(data)
                raise
            if record.state not in {"ACTIVE", "ELIGIBLE", "RESTORED"}:
                data["retention_events"].append(self._event(
                    "KEEP_REFUSED", record, record, now, code="STATE_REFUSED"))
                self._save(data)
                raise ValueError("Artifact state cannot be kept")
            if "USER_KEEP" in record.hold_reasons:
                return record
            updated = ArtifactRecord(**{**asdict(record), "hold_reasons": (*record.hold_reasons, "USER_KEEP")})
            data["artifacts"][artifact_id] = _record_payload(updated)
            data["retention_events"].append(self._event("KEEP", record, updated, now))
            self._save(data)
            return updated

    def complete_restore_with_keep(self, previous: ArtifactRecord, restored: ArtifactRecord,
                                   now_utc: datetime) -> ArtifactRecord:
        """Atomically publish a restored payload together with its user hold and audit event.

        The caller owns this store's registration guard and has already made the verified
        filesystem restore reversible through its pending-operation journal.
        """
        now = _utc(now_utc)
        if not self.owns_registration_guard():
            raise RegistrationLockedError("registrazione artefatti bloccata")
        data = self._load()
        raw = data["artifacts"].get(previous.artifact_id)
        if raw is None or _record(raw) != previous or restored.workstation_id != self.workstation_id:
            raise ValueError("Artifact restore commit mismatch")
        held = restored if "USER_KEEP" in restored.hold_reasons else ArtifactRecord(
            **{**asdict(restored), "hold_reasons": (*restored.hold_reasons, "USER_KEEP")})
        data["artifacts"][held.artifact_id] = _record_payload(held)
        data["pending_operation"] = None
        data["retention_events"].append(self._event(
            "KEEP", previous, held, now, restore_performed=True, code="RESTORE_KEPT"))
        self._save(data)
        return held

    def release_kept_artifact(self, artifact_id: str, policy: ArtifactPolicy,
                              now_utc: datetime) -> ArtifactRecord:
        now = _utc(now_utc)
        with self.registration_guard():
            data = self._load()
            record = self._hold_target(data, artifact_id)
            if "USER_KEEP" not in record.hold_reasons:
                return record
            if record.category not in policy.rules:
                raise ValueError("Artifact category missing from policy")
            updated = ArtifactRecord(**{**asdict(record), "hold_reasons": tuple(
                reason for reason in record.hold_reasons if reason != "USER_KEEP"),
                "state": "ACTIVE", "eligible_at": now + timedelta(
                    seconds=policy.rules[record.category].active_seconds)})
            data["artifacts"][artifact_id] = _record_payload(updated)
            data["retention_events"].append(self._event("RELEASE", record, updated, now))
            self._save(data)
            return updated

    def maintenance_state(self) -> MaintenanceState:
        raw = self._load()["maintenance"]
        return MaintenanceState(_time(raw.get("last_attempt_at")), raw.get("last_result"))

    def set_maintenance_state(self, *, last_attempt_at: datetime, last_result: str) -> None:
        # Status is a whole-registry RMW too: serialize it with producer writes.
        with self.registration_guard():
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

    def update_pending_operation(self, operation: dict[str, Any],
                                 record: ArtifactRecord | None = None) -> None:
        """Persist the journal phase and its record state in one durable replace."""
        data = self._load()
        pending = data.get("pending_operation")
        if pending is None or pending.get("artifact_id") != operation.get("artifact_id"):
            raise ValueError("Pending artifact operation mismatch")
        if record is not None:
            if (record.workstation_id != self.workstation_id
                    or record.artifact_id != operation.get("artifact_id")
                    or record.artifact_id not in data["artifacts"]):
                raise ValueError("Pending artifact record mismatch")
            data["artifacts"][record.artifact_id] = _record_payload(record)
        data["pending_operation"] = dict(operation)
        self._save(data)


def artifact_store_for(config: CreativeConfig) -> ArtifactStore:
    candidates = {
        "render_root": getattr(config, "render_root", None),
        "runtime_log_root": getattr(config, "runtime_log_root", None),
        "audio_root": getattr(config, "audio_root", None),
        "audio_jobs_root": getattr(config, "audio_jobs_root", None),
        "profile_root": config.artifact_registry_path.parent,
        "asset_root": getattr(config, "asset_root", None),
        "resolve_archive_root": getattr(config, "resolve_archive_root", None),
    }
    return ArtifactStore(config.artifact_registry_path, config.workstation_id, {
        key: value for key, value in candidates.items() if isinstance(value, Path)
    })
