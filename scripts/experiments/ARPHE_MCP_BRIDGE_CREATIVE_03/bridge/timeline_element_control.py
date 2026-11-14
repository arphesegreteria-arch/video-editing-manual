from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any
from uuid import uuid4

from .resolve_connection import safe_call
from .safety import ValidationError


SCHEMA = "ARPHE_TIMELINE_ELEMENT_CONTROL_V1"
UTC = timezone.utc
ALLOWED_OPERATOR_ROLES = frozenset({"SEGRETERIA", "TECNICO", "ALESSIO"})
_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _utc(value: datetime | None = None) -> datetime:
    selected = value or datetime.now(UTC)
    if selected.tzinfo is None:
        raise ValidationError("Timestamp privo di timezone")
    return selected.astimezone(UTC)


def _time_text(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_time(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Timestamp {field} non valido") from exc
    return _utc(parsed)


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve()).casefold()
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _safe_display_name(value: object) -> str:
    text = str(value or "elemento timeline")
    text = re.sub(r"[A-Za-z]:[\\/][^\s]+", " ", text)
    text = text.replace("\\", " ").replace("/", " ")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return (text or "elemento timeline")[:120]


def _required_int(value: object, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field} non valido")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} non valido") from exc
    if result < minimum:
        raise ValidationError(f"{field} non valido")
    return result


@dataclass(frozen=True)
class TimelineElementSnapshot:
    workstation_id: str
    project_name: str
    timeline_name: str
    media_type: str
    track_index: int
    start_frame: int
    end_frame: int
    duration_frames: int
    display_name: str
    media_identity: str
    enabled: bool


def _snapshot_payload(snapshot: TimelineElementSnapshot) -> dict[str, object]:
    return asdict(snapshot)


def _snapshot_from_payload(raw: object) -> TimelineElementSnapshot:
    if not isinstance(raw, dict):
        raise ValidationError("Snapshot elemento non valido")
    expected = set(TimelineElementSnapshot.__dataclass_fields__)
    if set(raw) != expected:
        raise ValidationError("Campi snapshot elemento non validi")
    try:
        result = TimelineElementSnapshot(
            workstation_id=str(raw["workstation_id"]),
            project_name=str(raw["project_name"]),
            timeline_name=str(raw["timeline_name"]),
            media_type=str(raw["media_type"]),
            track_index=_required_int(raw["track_index"], "track_index", 1),
            start_frame=_required_int(raw["start_frame"], "start_frame"),
            end_frame=_required_int(raw["end_frame"], "end_frame"),
            duration_frames=_required_int(raw["duration_frames"], "duration_frames"),
            display_name=_safe_display_name(raw["display_name"]),
            media_identity=str(raw["media_identity"]),
            enabled=raw["enabled"],
        )
    except KeyError as exc:
        raise ValidationError("Snapshot elemento incompleto") from exc
    if result.media_type not in {"video", "audio"}:
        raise ValidationError("media_type elemento non valido")
    if not isinstance(result.enabled, bool):
        raise ValidationError("enabled elemento non valido")
    if result.end_frame <= result.start_frame or result.duration_frames < 0:
        raise ValidationError("Intervallo elemento non valido")
    if not result.workstation_id or not result.project_name or not result.timeline_name:
        raise ValidationError("Identità elemento incompleta")
    if not result.media_identity:
        raise ValidationError("Identità media assente")
    return result


def snapshot_fingerprint(snapshot: TimelineElementSnapshot) -> str:
    return _canonical_digest(_snapshot_payload(snapshot))


def _media_identity(item: object, media_pool_item: object, fallback: dict[str, object]) -> str:
    for candidate in (
        safe_call(media_pool_item, "GetMediaId"),
        safe_call(media_pool_item, "GetUniqueId"),
        safe_call(item, "GetUniqueId"),
    ):
        if candidate not in (None, ""):
            return _safe_display_name(candidate)
    properties = safe_call(media_pool_item, "GetClipProperty")
    safe_properties: dict[str, str] = {}
    if isinstance(properties, dict):
        for key in ("Media ID", "Clip Name", "Reel Name", "Type", "Date Created"):
            value = properties.get(key)
            if value not in (None, ""):
                safe_properties[key] = _safe_display_name(value)
    return "derived:" + _canonical_digest({"metadata": safe_properties, **fallback})


def capture_item_snapshot(
    workstation_id: str,
    project: object,
    timeline: object,
    media_type: str,
    track_index: int,
    item: object,
) -> TimelineElementSnapshot:
    if media_type not in {"video", "audio"}:
        raise ValidationError("media_type deve essere video o audio")
    track = _required_int(track_index, "track_index", 1)
    project_name = _safe_display_name(safe_call(project, "GetName"))
    timeline_name = _safe_display_name(safe_call(timeline, "GetName"))
    start = _required_int(safe_call(item, "GetStart"), "start_frame")
    end = _required_int(safe_call(item, "GetEnd"), "end_frame")
    duration_value = safe_call(item, "GetDuration")
    duration = _required_int(
        end - start if duration_value is None else duration_value,
        "duration_frames",
    )
    enabled = safe_call(item, "GetClipEnabled")
    if not isinstance(enabled, bool):
        raise ValidationError("Stato enabled elemento non disponibile")
    display_name = _safe_display_name(safe_call(item, "GetName"))
    media_pool_item = safe_call(item, "GetMediaPoolItem")
    media_identity = _media_identity(item, media_pool_item, {
        "media_type": media_type,
        "track_index": track,
        "start_frame": start,
        "end_frame": end,
        "display_name": display_name,
    })
    return _snapshot_from_payload({
        "workstation_id": workstation_id,
        "project_name": project_name,
        "timeline_name": timeline_name,
        "media_type": media_type,
        "track_index": track,
        "start_frame": start,
        "end_frame": end,
        "duration_frames": duration,
        "display_name": display_name,
        "media_identity": media_identity,
        "enabled": enabled,
    })


def _ownership_identity(snapshot: TimelineElementSnapshot) -> dict[str, object]:
    payload = _snapshot_payload(snapshot)
    payload.pop("enabled")
    return payload


class TimelineElementStore:
    def __init__(
        self,
        path: Path,
        workstation_id: str,
        handle_ttl_seconds: int = 300,
        removal_ttl_seconds: int = 600,
    ):
        if not workstation_id:
            raise ValidationError("workstation_id richiesto")
        if handle_ttl_seconds <= 0 or removal_ttl_seconds <= 0:
            raise ValidationError("TTL timeline element control non valido")
        self.path = path.resolve()
        self.workstation_id = workstation_id
        self.handle_ttl_seconds = int(handle_ttl_seconds)
        self.removal_ttl_seconds = int(removal_ttl_seconds)
        self._lock = _path_lock(self.path)

    def _empty(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "workstation_id": self.workstation_id,
            "handles": {},
            "ownership": {},
            "removals": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError("Store timeline element control non leggibile") from exc
        if data.get("schema") != SCHEMA:
            raise ValidationError("Schema timeline element control non supportato")
        if data.get("workstation_id") != self.workstation_id:
            raise ValidationError("Store appartenente a un'altra workstation")
        if any(not isinstance(data.get(key), dict) for key in ("handles", "ownership", "removals")):
            raise ValidationError("Store timeline element control non valido")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=self.path.name + ".", dir=str(self.path.parent), text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def issue_handle(
        self,
        snapshot: TimelineElementSnapshot,
        related: tuple[str, ...] = (),
        now: datetime | None = None,
    ) -> dict[str, object]:
        selected = _utc(now)
        if snapshot.workstation_id != self.workstation_id:
            raise ValidationError("Snapshot appartenente a un'altra workstation")
        element_id = _opaque_id("element")
        record: dict[str, object] = {
            "element_id": element_id,
            "fingerprint": snapshot_fingerprint(snapshot),
            "snapshot": _snapshot_payload(snapshot),
            "related": list(related),
            "issued_at": _time_text(selected),
            "expires_at": _time_text(selected + timedelta(seconds=self.handle_ttl_seconds)),
        }
        with self._lock:
            data = self._load()
            data["handles"][element_id] = record
            self._save(data)
        return dict(record)

    def require_handle(
        self, element_id: str, fingerprint: str, now: datetime
    ) -> dict[str, object]:
        with self._lock:
            record = self._load()["handles"].get(element_id)
        if not isinstance(record, dict):
            raise ValidationError("Handle elemento sconosciuto")
        if record.get("fingerprint") != fingerprint:
            raise ValidationError("Fingerprint handle elemento non valido")
        if _utc(now) > _parse_time(record.get("expires_at"), "expires_at"):
            raise ValidationError("Handle elemento scaduto")
        snapshot = _snapshot_from_payload(record.get("snapshot"))
        if snapshot.workstation_id != self.workstation_id:
            raise ValidationError("Handle appartenente a un'altra workstation")
        return dict(record)

    def register_ownership(
        self,
        snapshot: TimelineElementSnapshot,
        action: str,
        native_reference: str,
        now: datetime | None = None,
    ) -> dict[str, object]:
        if snapshot.workstation_id != self.workstation_id:
            raise ValidationError("Ownership appartenente a un'altra workstation")
        if not action.strip() or not native_reference.strip():
            raise ValidationError("Provenienza ownership incompleta")
        selected = _utc(now)
        ownership_id = _opaque_id("ownership")
        identity = _ownership_identity(snapshot)
        record: dict[str, object] = {
            "ownership_id": ownership_id,
            "identity": identity,
            "identity_fingerprint": _canonical_digest(identity),
            "action": _safe_display_name(action),
            "native_reference": _safe_display_name(native_reference),
            "active": True,
            "created_at": _time_text(selected),
        }
        with self._lock:
            data = self._load()
            data["ownership"][ownership_id] = record
            self._save(data)
        return dict(record)

    def matching_ownership(self, snapshot: TimelineElementSnapshot) -> dict[str, object] | None:
        if snapshot.workstation_id != self.workstation_id:
            return None
        identity = _ownership_identity(snapshot)
        fingerprint = _canonical_digest(identity)
        with self._lock:
            records = self._load()["ownership"].values()
            matches = [
                dict(record) for record in records
                if isinstance(record, dict)
                and record.get("active") is True
                and record.get("identity_fingerprint") == fingerprint
                and record.get("identity") == identity
            ]
        return matches[0] if len(matches) == 1 else None

    def prepare_removal(
        self,
        handle: dict[str, object],
        ownership: dict[str, object],
        now: datetime,
    ) -> dict[str, object]:
        selected = _utc(now)
        snapshot = _snapshot_from_payload(handle.get("snapshot"))
        if snapshot.workstation_id != self.workstation_id:
            raise ValidationError("Handle appartenente a un'altra workstation")
        if ownership.get("active") is not True:
            raise ValidationError("Ownership non attiva")
        identity = _ownership_identity(snapshot)
        if ownership.get("identity") != identity:
            raise ValidationError("Ownership non corrispondente all'elemento")
        removal_id = _opaque_id("removal")
        proposal_basis = {
            "removal_id": removal_id,
            "element_id": handle.get("element_id"),
            "element_fingerprint": handle.get("fingerprint"),
            "ownership_id": ownership.get("ownership_id"),
            "expires_at": _time_text(selected + timedelta(seconds=self.removal_ttl_seconds)),
        }
        record: dict[str, object] = {
            **proposal_basis,
            "proposal_fingerprint": _canonical_digest(proposal_basis),
            "state": "PREPARED",
            "prepared_at": _time_text(selected),
            "intent_at": None,
            "operator_role": None,
            "receipt": None,
        }
        with self._lock:
            data = self._load()
            if data["handles"].get(handle.get("element_id")) != handle:
                raise ValidationError("Handle non più valido nello store")
            if data["ownership"].get(ownership.get("ownership_id")) != ownership:
                raise ValidationError("Ownership non più valida nello store")
            data["removals"][removal_id] = record
            self._save(data)
        return dict(record)

    def begin_removal(
        self,
        removal_id: str,
        proposal_fingerprint: str,
        operator_role: str,
        now: datetime,
    ) -> dict[str, object]:
        selected = _utc(now)
        role = str(operator_role).strip().upper()
        if role not in ALLOWED_OPERATOR_ROLES:
            raise ValidationError("operator_role non autorizzato")
        with self._lock:
            data = self._load()
            record = data["removals"].get(removal_id)
            if not isinstance(record, dict):
                raise ValidationError("Proposta rimozione sconosciuta")
            if record.get("proposal_fingerprint") != proposal_fingerprint:
                raise ValidationError("Fingerprint proposta rimozione non valido")
            if record.get("state") != "PREPARED":
                raise ValidationError("Proposta rimozione già usata o in stato non valido")
            if selected > _parse_time(record.get("expires_at"), "expires_at"):
                raise ValidationError("Proposta rimozione scaduta")
            record["state"] = "INTENT"
            record["intent_at"] = _time_text(selected)
            record["operator_role"] = role
            self._save(data)
            return dict(record)

    def complete_removal(
        self,
        removal_id: str,
        receipt: dict[str, object],
        now: datetime,
    ) -> dict[str, object]:
        selected = _utc(now)
        with self._lock:
            data = self._load()
            record = data["removals"].get(removal_id)
            if not isinstance(record, dict):
                raise ValidationError("Rimozione sconosciuta")
            if record.get("state") == "COMPLETED":
                if record.get("receipt") != receipt:
                    raise ValidationError("Ricevuta rimozione già finalizzata con dati diversi")
                return dict(record)
            if record.get("state") != "INTENT":
                raise ValidationError("Intento rimozione non persistito")
            ownership = data["ownership"].get(record.get("ownership_id"))
            if not isinstance(ownership, dict) or ownership.get("active") is not True:
                raise ValidationError("Ownership rimozione non più attiva")
            ownership["active"] = False
            ownership["retired_at"] = _time_text(selected)
            record["state"] = "COMPLETED"
            record["completed_at"] = _time_text(selected)
            record["receipt"] = dict(receipt)
            self._save(data)
            return dict(record)


def store_for_config(config: object) -> TimelineElementStore:
    path = getattr(config, "timeline_element_control_path", None)
    workstation_id = getattr(config, "workstation_id", None)
    if not isinstance(path, Path) or not isinstance(workstation_id, str):
        raise ValidationError("Config timeline element control incompleta")
    return TimelineElementStore(
        path,
        workstation_id,
        int(getattr(config, "timeline_element_handle_ttl_seconds", 300)),
        int(getattr(config, "timeline_element_removal_ttl_seconds", 600)),
    )
