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


def _resolve_unique_id(value: object) -> str:
    candidate = safe_call(value, "GetUniqueId")
    return "" if candidate in (None, "") else str(candidate)


def _same_resolve_object(left: object, right: object) -> bool:
    left_id, right_id = _resolve_unique_id(left), _resolve_unique_id(right)
    if left_id and right_id:
        return left_id == right_id
    return left is right


def _resolve_item_key(item: object) -> tuple[str, str | int]:
    unique_id = _resolve_unique_id(item)
    return ("uid", unique_id) if unique_id else ("proxy", id(item))


def _media_identity(
    project: object,
    timeline: object,
    item: object,
    media_pool_item: object,
    fallback: dict[str, object],
) -> str:
    project_id = _resolve_unique_id(project)
    timeline_id = _resolve_unique_id(timeline)
    item_id = _resolve_unique_id(item)
    media_id = str(
        safe_call(media_pool_item, "GetMediaId")
        or safe_call(media_pool_item, "GetUniqueId")
        or ""
    )
    if project_id and timeline_id and item_id:
        return "stable:" + _canonical_digest({
            "project_id": project_id,
            "timeline_id": timeline_id,
            "item_id": item_id,
            "media_id": media_id,
        })
    properties = safe_call(media_pool_item, "GetClipProperty")
    safe_properties: dict[str, str] = {}
    if isinstance(properties, dict):
        for key in ("Media ID", "Clip Name", "Reel Name", "Type", "Date Created"):
            value = properties.get(key)
            if value not in (None, ""):
                safe_properties[key] = _safe_display_name(value)
    return "derived:" + _canonical_digest({
        "project_id": project_id,
        "timeline_id": timeline_id,
        "item_id": item_id,
        "media_id": media_id,
        "metadata": safe_properties,
        **fallback,
    })


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
    media_identity = _media_identity(project, timeline, item, media_pool_item, {
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
        if not snapshot.media_identity.startswith("stable:"):
            raise ValidationError(
                "Ownership richiede ID stabili di progetto, timeline e TimelineItem"
            )
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
            existing = [
                dict(value) for value in data["ownership"].values()
                if isinstance(value, dict)
                and value.get("active") is True
                and value.get("identity") == identity
                and value.get("action") == record["action"]
                and value.get("native_reference") == record["native_reference"]
            ]
            if len(existing) == 1:
                return existing[0]
            if len(existing) > 1:
                raise ValidationError("Ownership duplicata nello store")
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
        intent_context: dict[str, object] | None = None,
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
            record["intent_context"] = dict(intent_context or {})
            self._save(data)
            return dict(record)

    def require_removal(
        self,
        removal_id: str,
        proposal_fingerprint: str,
        now: datetime,
    ) -> dict[str, object]:
        selected = _utc(now)
        with self._lock:
            record = self._load()["removals"].get(removal_id)
        if not isinstance(record, dict):
            raise ValidationError("Proposta rimozione sconosciuta")
        if record.get("proposal_fingerprint") != proposal_fingerprint:
            raise ValidationError("Fingerprint proposta rimozione non valido")
        if record.get("state") == "PREPARED" and selected > _parse_time(
            record.get("expires_at"), "expires_at"
        ):
            raise ValidationError("Proposta rimozione scaduta")
        return dict(record)

    def removal_handle(self, removal: dict[str, object]) -> dict[str, object]:
        with self._lock:
            record = self._load()["handles"].get(removal.get("element_id"))
        if not isinstance(record, dict):
            raise ValidationError("Handle della rimozione non disponibile")
        if record.get("fingerprint") != removal.get("element_fingerprint"):
            raise ValidationError("Handle della rimozione non corrispondente")
        return dict(record)

    def reset_removal(
        self, removal_id: str, proposal_fingerprint: str, reason: str
    ) -> dict[str, object]:
        with self._lock:
            data = self._load()
            record = data["removals"].get(removal_id)
            if not isinstance(record, dict) or record.get("proposal_fingerprint") != proposal_fingerprint:
                raise ValidationError("Proposta rimozione non valida")
            if record.get("state") != "INTENT":
                raise ValidationError("Intento rimozione non resettabile")
            record["state"] = "PREPARED"
            record["intent_at"] = None
            record["operator_role"] = None
            record["intent_context"] = None
            record["last_error"] = _safe_display_name(reason)
            self._save(data)
            return dict(record)

    def block_removal(
        self, removal_id: str, proposal_fingerprint: str, reason: str
    ) -> dict[str, object]:
        with self._lock:
            data = self._load()
            record = data["removals"].get(removal_id)
            if not isinstance(record, dict) or record.get("proposal_fingerprint") != proposal_fingerprint:
                raise ValidationError("Proposta rimozione non valida")
            if record.get("state") not in {"INTENT", "BLOCKED"}:
                raise ValidationError("Rimozione non bloccabile nello stato corrente")
            record["state"] = "BLOCKED"
            record["last_error"] = _safe_display_name(reason)
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


def timeline_item_track_index(
    timeline: object, media_type: str, item: object
) -> int:
    if media_type not in {"video", "audio"}:
        raise ValidationError("media_type deve essere video o audio")
    matches: list[int] = []
    raw_count = safe_call(timeline, "GetTrackCount", media_type)
    if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
        raise ValidationError("Read-back conteggio tracce non disponibile")
    count = raw_count
    item_key = _resolve_item_key(item)
    for track in range(1, count + 1):
        items = safe_call(timeline, "GetItemListInTrack", media_type, track)
        if items is None:
            raise ValidationError("Read-back traccia elemento creato non disponibile")
        if any(_resolve_item_key(candidate) == item_key for candidate in list(items)):
            matches.append(track)
    if len(matches) != 1:
        raise ValidationError("Elemento creato non presente su una sola traccia")
    return matches[0]


def register_created_item(
    config: object,
    project: object,
    timeline: object,
    media_type: str,
    track_index: int,
    item: object,
    action: str,
    native_reference: str,
) -> dict[str, object]:
    """Persist ownership only after a caller has completed its Resolve read-back.

    Older tests and pre-migration callers may provide a config without the Task 5
    store path.  That transitional shape cannot claim ownership and is reported
    explicitly as unregistered; once Task 5 lands, every loaded config has a path.
    """
    if not isinstance(getattr(config, "timeline_element_control_path", None), Path):
        return {"registered": False, "ownership_id": None}
    store = store_for_config(config)
    snapshot = capture_item_snapshot(
        store.workstation_id, project, timeline, media_type, track_index, item
    )
    ownership = store.register_ownership(snapshot, action, native_reference)
    return {
        "registered": True,
        "ownership_id": ownership["ownership_id"],
        "identity_fingerprint": ownership["identity_fingerprint"],
    }


def _require_allowed_target(
    project: object, timeline: object, config: object, registry: object
) -> tuple[str, str]:
    project_name = str(safe_call(project, "GetName") or "")
    timeline_name = str(safe_call(timeline, "GetName") or "")
    project_allowed = bool(safe_call(registry, "project_allowed", project_name)) or (
        project_name in getattr(config, "allowed_projects", frozenset())
    )
    timeline_allowed = bool(
        safe_call(registry, "timeline_allowed", project_name, timeline_name)
    ) or timeline_name in getattr(config, "allowed_timelines", frozenset())
    if not project_allowed or not timeline_allowed:
        raise ValidationError("Progetto o timeline corrente non allowlisted")
    current_timeline = safe_call(project, "GetCurrentTimeline")
    if current_timeline is None or not _same_resolve_object(current_timeline, timeline):
        raise ValidationError("La timeline indicata non è la timeline corrente")
    return project_name, timeline_name


def _validated_filters(
    media_type: str | None,
    track_index: int | None,
    start_frame: int | None,
    end_frame: int | None,
) -> tuple[tuple[str, ...], int | None, int | None, int | None]:
    if media_type is not None and media_type not in {"video", "audio"}:
        raise ValidationError("media_type deve essere video o audio")
    track = None if track_index is None else _required_int(track_index, "track_index", 1)
    start = None if start_frame is None else _required_int(start_frame, "start_frame")
    end = None if end_frame is None else _required_int(end_frame, "end_frame")
    if start is not None and end is not None and end <= start:
        raise ValidationError("Intervallo di ispezione non valido")
    return ((media_type,) if media_type else ("video", "audio")), track, start, end


def _enumerate_snapshots(
    project: object,
    timeline: object,
    workstation_id: str,
    media_types: tuple[str, ...],
    track_index: int | None = None,
) -> list[tuple[object, TimelineElementSnapshot]]:
    found: list[tuple[object, TimelineElementSnapshot]] = []
    for kind in media_types:
        raw_count = safe_call(timeline, "GetTrackCount", kind)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int) or raw_count < 0:
            raise ValidationError("Lettura conteggio tracce timeline non disponibile")
        count = raw_count
        tracks = (track_index,) if track_index is not None else range(1, count + 1)
        for track in tracks:
            if track > count:
                raise ValidationError("Traccia elemento bound non più disponibile")
            items = safe_call(timeline, "GetItemListInTrack", kind, track)
            if items is None:
                raise ValidationError("Lettura elementi timeline non disponibile")
            for item in list(items):
                found.append((
                    item,
                    capture_item_snapshot(
                        workstation_id, project, timeline, kind, track, item
                    ),
                ))
    return found


def inspect_elements(
    project: object,
    timeline: object,
    config: object,
    registry: object,
    store: TimelineElementStore,
    media_type: str | None = None,
    track_index: int | None = None,
    start_frame: int | None = None,
    end_frame: int | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    project_name, timeline_name = _require_allowed_target(
        project, timeline, config, registry
    )
    media_types, track, range_start, range_end = _validated_filters(
        media_type, track_index, start_frame, end_frame
    )
    workstation_id = str(getattr(config, "workstation_id", ""))
    if store.workstation_id != workstation_id:
        raise ValidationError("Store timeline element control di un'altra workstation")
    all_items = _enumerate_snapshots(
        project, timeline, workstation_id, ("video", "audio"), None
    )
    filtered = [
        pair for pair in all_items
        if pair[1].media_type in media_types
        and (track is None or pair[1].track_index == track)
        if (range_start is None or pair[1].end_frame > range_start)
        and (range_end is None or pair[1].start_frame < range_end)
    ]
    by_object = {_resolve_item_key(item): snap for item, snap in all_items}
    result: list[dict[str, object]] = []
    for item, snap in filtered:
        linked = safe_call(timeline, "GetLinkedItems", item)
        if linked is None:
            linked = safe_call(item, "GetLinkedItems") or []
        related_fingerprints = tuple(
            snapshot_fingerprint(by_object[_resolve_item_key(peer)])
            for peer in list(linked or [])
            if _resolve_item_key(peer) in by_object
            and _resolve_item_key(peer) != _resolve_item_key(item)
        )
        handle = store.issue_handle(snap, related_fingerprints, now=now)
        result.append({
            "element_id": handle["element_id"],
            "fingerprint": handle["fingerprint"],
            "media_type": snap.media_type,
            "track_index": snap.track_index,
            "start_frame": snap.start_frame,
            "end_frame": snap.end_frame,
            "duration_frames": snap.duration_frames,
            "display_name": snap.display_name,
            "enabled": snap.enabled,
            "related_fingerprints": list(related_fingerprints),
            "remove_allowed": store.matching_ownership(snap) is not None,
            "expires_at": handle["expires_at"],
        })
    return {
        "ok": True,
        "action": "inspect_timeline_elements",
        "workstation_id": workstation_id,
        "project": project_name,
        "timeline": timeline_name,
        "write_capability_enabled": bool(
            getattr(config, "flags", {}).get("CAP_TIMELINE_ELEMENT_CONTROL", False)
        ),
        "elements": result,
    }


def _bound_track_snapshots(
    project: object, timeline: object, handle: dict[str, object]
) -> tuple[TimelineElementSnapshot, list[tuple[object, TimelineElementSnapshot]]]:
    expected = _snapshot_from_payload(handle.get("snapshot"))
    if str(safe_call(project, "GetName") or "") != expected.project_name:
        raise ValidationError("Target elemento stale: progetto cambiato")
    if str(safe_call(timeline, "GetName") or "") != expected.timeline_name:
        raise ValidationError("Target elemento stale: timeline cambiata")
    candidates = _enumerate_snapshots(
        project, timeline, expected.workstation_id,
        (expected.media_type,), expected.track_index,
    )
    return expected, candidates


def rematch_live_item(
    project: object, timeline: object, handle: dict[str, object]
) -> tuple[object, TimelineElementSnapshot]:
    expected, candidates = _bound_track_snapshots(project, timeline, handle)
    if not expected.media_identity.startswith("stable:"):
        raise ValidationError("Mutazione rifiutata: ID stabili Resolve non disponibili")
    expected_fingerprint = str(handle.get("fingerprint") or "")
    matches = [
        (item, snap) for item, snap in candidates
        if snapshot_fingerprint(snap) == expected_fingerprint and snap == expected
    ]
    if len(matches) > 1:
        raise ValidationError("Rematch elemento ambiguo: target non univoco")
    if not matches:
        raise ValidationError("Target elemento stale o non più presente")
    return matches[0]


def timeline_is_picture_locked(
    config: object, project_name: str, timeline_name: str
) -> bool:
    plans_path = getattr(config, "vertical_social_plans_path", None)
    if not isinstance(plans_path, Path) or not plans_path.exists():
        return False
    meta_path = plans_path.with_name(plans_path.stem + "_workflow.json")
    if not meta_path.exists():
        return False
    try:
        plans_raw = json.loads(plans_path.read_text(encoding="utf-8-sig"))
        meta_raw = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("Stato picture lock non leggibile") from exc
    if plans_raw.get("workstation_id") != getattr(config, "workstation_id", None):
        raise ValidationError("Registro picture lock di un'altra workstation")
    plans = plans_raw.get("plans")
    if not isinstance(plans, dict) or not isinstance(meta_raw, dict):
        raise ValidationError("Stato picture lock non valido")
    for plan_id, raw in plans.items():
        metadata = meta_raw.get(plan_id, {})
        if not isinstance(raw, dict) or not isinstance(metadata, dict):
            raise ValidationError("Record picture lock non valido")
        if metadata.get("picture_locked") is not True:
            continue
        target = raw.get("target", {})
        if not isinstance(target, dict) or str(target.get("project") or "") != project_name:
            continue
        target_timeline = str(target.get("timeline") or "")
        suffix = str(plan_id).removeprefix("vertical_").upper()
        provisional = (
            f"__ARPHE_VERTICAL_VERTICAL_{suffix}"
            if len(suffix) == 32 and suffix.isalnum() else ""
        )
        if timeline_name in {target_timeline, provisional}:
            return True
    return False


def _same_except_enabled(
    expected: TimelineElementSnapshot, current: TimelineElementSnapshot
) -> bool:
    left = _snapshot_payload(expected)
    right = _snapshot_payload(current)
    left.pop("enabled")
    right.pop("enabled")
    return left == right


def set_element_enabled(
    project: object,
    timeline: object,
    config: object,
    registry: object,
    store: TimelineElementStore,
    element_id: str,
    fingerprint: str,
    enabled: bool,
    now: datetime | None = None,
) -> dict[str, object]:
    if not isinstance(enabled, bool):
        raise ValidationError("enabled deve essere booleano")
    selected = _utc(now)
    handle = store.require_handle(element_id, fingerprint, selected)
    if not bool(getattr(config, "flags", {}).get("CAP_TIMELINE_ELEMENT_CONTROL", False)):
        raise ValidationError("CAP_TIMELINE_ELEMENT_CONTROL disabilitata")
    project_name, timeline_name = _require_allowed_target(
        project, timeline, config, registry
    )
    if timeline_is_picture_locked(config, project_name, timeline_name):
        raise ValidationError("Scrittura rifiutata: workflow in picture lock")
    expected, candidates = _bound_track_snapshots(project, timeline, handle)
    if not expected.media_identity.startswith("stable:"):
        raise ValidationError("Mutazione rifiutata: ID stabili Resolve non disponibili")
    exact = [
        (item, snap) for item, snap in candidates
        if snap == expected and snapshot_fingerprint(snap) == fingerprint
    ]
    if len(exact) > 1:
        raise ValidationError("Rematch elemento ambiguo: target non univoco")
    if len(exact) == 1:
        item, live = exact[0]
        if live.enabled == enabled:
            return {
                "ok": True, "action": "set_timeline_element_enabled",
                "workstation_id": store.workstation_id,
                "element_id": element_id, "enabled": enabled,
                "idempotent": True, "fingerprint": fingerprint,
            }
    else:
        drift = [
            (item, snap) for item, snap in candidates
            if _same_except_enabled(expected, snap)
        ]
        if len(drift) > 1:
            raise ValidationError("Rematch elemento ambiguo: target non univoco")
        if len(drift) == 1 and drift[0][1].enabled == enabled:
            return {
                "ok": True, "action": "set_timeline_element_enabled",
                "workstation_id": store.workstation_id,
                "element_id": element_id, "enabled": enabled,
                "idempotent": True,
                "fingerprint": snapshot_fingerprint(drift[0][1]),
            }
        raise ValidationError("Target elemento stale: identità o stato cambiati")
    if safe_call(item, "SetClipEnabled", enabled) is not True:
        raise ValidationError("SetClipEnabled non supportato o fallito")
    readback = safe_call(item, "GetClipEnabled")
    if not isinstance(readback, bool) or readback is not enabled:
        raise ValidationError("Read-back SetClipEnabled non corrispondente")
    current = capture_item_snapshot(
        store.workstation_id, project, timeline,
        live.media_type, live.track_index, item,
    )
    if not _same_except_enabled(expected, current):
        raise ValidationError("Elemento cambiato durante SetClipEnabled")
    return {
        "ok": True,
        "action": "set_timeline_element_enabled",
        "workstation_id": store.workstation_id,
        "element_id": element_id,
        "enabled": enabled,
        "idempotent": False,
        "fingerprint": snapshot_fingerprint(current),
    }


def prepare_element_removal(
    project: object,
    timeline: object,
    config: object,
    registry: object,
    store: TimelineElementStore,
    element_id: str,
    fingerprint: str,
    now: datetime | None = None,
) -> dict[str, object]:
    selected = _utc(now)
    handle = store.require_handle(element_id, fingerprint, selected)
    if not bool(getattr(config, "flags", {}).get("CAP_TIMELINE_ELEMENT_CONTROL", False)):
        raise ValidationError("CAP_TIMELINE_ELEMENT_CONTROL disabilitata")
    project_name, timeline_name = _require_allowed_target(
        project, timeline, config, registry
    )
    if timeline_is_picture_locked(config, project_name, timeline_name):
        raise ValidationError("Preparazione rifiutata: workflow in picture lock")
    _, live = rematch_live_item(project, timeline, handle)
    ownership = store.matching_ownership(live)
    if ownership is None:
        raise ValidationError("Rimozione vietata: ownership bridge esatta non disponibile")
    proposal = store.prepare_removal(handle, ownership, selected)
    return {
        "ok": True,
        "action": "prepare_timeline_element_removal",
        "workstation_id": store.workstation_id,
        "element_id": element_id,
        "fingerprint": fingerprint,
        "removal_id": proposal["removal_id"],
        "proposal_fingerprint": proposal["proposal_fingerprint"],
        "expires_at": proposal["expires_at"],
        "preview": {
            "media_type": live.media_type,
            "track_index": live.track_index,
            "start_frame": live.start_frame,
            "end_frame": live.end_frame,
            "display_name": live.display_name,
        },
    }


def _ordered_fingerprints(
    pairs: list[tuple[object, TimelineElementSnapshot]],
) -> list[str]:
    ordered = sorted(
        (snapshot for _, snapshot in pairs),
        key=lambda value: (
            value.start_frame, value.end_frame, value.media_identity,
            value.display_name, value.enabled,
        ),
    )
    return [snapshot_fingerprint(value) for value in ordered]


def _neighbour_ranges(
    pairs: list[tuple[object, TimelineElementSnapshot]],
) -> list[list[int]]:
    return [
        [snapshot.start_frame, snapshot.end_frame]
        for _, snapshot in sorted(
            pairs, key=lambda pair: (pair[1].start_frame, pair[1].end_frame)
        )
    ]


def _removal_live_state(
    project: object,
    timeline: object,
    handle: dict[str, object],
) -> tuple[
    TimelineElementSnapshot,
    list[tuple[object, TimelineElementSnapshot]],
    list[tuple[object, TimelineElementSnapshot]],
]:
    expected, candidates = _bound_track_snapshots(project, timeline, handle)
    target = [
        pair for pair in candidates
        if pair[1] == expected
        and snapshot_fingerprint(pair[1]) == handle.get("fingerprint")
    ]
    return expected, target, candidates


def _completed_removal_result(
    record: dict[str, object], workstation_id: str
) -> dict[str, object]:
    receipt = record.get("receipt")
    if not isinstance(receipt, dict):
        raise ValidationError("Ricevuta rimozione completata non valida")
    return {
        "ok": True,
        "action": "execute_timeline_element_removal",
        "workstation_id": workstation_id,
        "element_id": record["element_id"],
        "fingerprint": record["element_fingerprint"],
        "removal_id": record["removal_id"],
        "proposal_fingerprint": record["proposal_fingerprint"],
        "state": "COMPLETED",
        **receipt,
    }


def execute_element_removal(
    project: object,
    timeline: object,
    config: object,
    registry: object,
    store: TimelineElementStore,
    removal_id: str,
    proposal_fingerprint: str,
    operator_role: str,
    now: datetime | None = None,
) -> dict[str, object]:
    selected = _utc(now)
    removal = store.require_removal(removal_id, proposal_fingerprint, selected)
    if removal.get("state") == "COMPLETED":
        return _completed_removal_result(removal, store.workstation_id)
    if removal.get("state") == "BLOCKED":
        raise ValidationError("Rimozione bloccata: intervento tecnico richiesto")
    if not bool(getattr(config, "flags", {}).get("CAP_TIMELINE_ELEMENT_CONTROL", False)):
        raise ValidationError("CAP_TIMELINE_ELEMENT_CONTROL disabilitata")
    project_name, timeline_name = _require_allowed_target(
        project, timeline, config, registry
    )
    if timeline_is_picture_locked(config, project_name, timeline_name):
        raise ValidationError("Rimozione rifiutata: workflow in picture lock")
    handle = store.removal_handle(removal)

    if removal.get("state") == "PREPARED":
        item, live = rematch_live_item(project, timeline, handle)
        ownership = store.matching_ownership(live)
        if ownership is None or ownership.get("ownership_id") != removal.get("ownership_id"):
            raise ValidationError("Ownership rimozione non più valida")
        expected, targets, candidates = _removal_live_state(project, timeline, handle)
        if len(targets) != 1 or not _same_resolve_object(targets[0][0], item):
            raise ValidationError("Target rimozione non univoco")
        item_key = _resolve_item_key(item)
        neighbours = [
            pair for pair in candidates if _resolve_item_key(pair[0]) != item_key
        ]
        context = {
            "target_fingerprint": snapshot_fingerprint(expected),
            "neighbour_fingerprints": _ordered_fingerprints(neighbours),
            "neighbour_ranges": _neighbour_ranges(neighbours),
        }
        removal = store.begin_removal(
            removal_id, proposal_fingerprint, operator_role, selected, context
        )
        deleted = safe_call(timeline, "DeleteClips", [item], False)
        _, after_targets, after_candidates = _removal_live_state(
            project, timeline, handle
        )
        after_neighbours = after_candidates if not after_targets else [
            pair for pair in after_candidates if pair not in after_targets
        ]
        after_neighbours_unchanged = (
            _ordered_fingerprints(after_neighbours)
            == context["neighbour_fingerprints"]
        )
        if not after_targets and after_neighbours_unchanged:
            removal = store.require_removal(
                removal_id, proposal_fingerprint, selected
            )
        elif deleted is not True and len(after_targets) == 1 and after_neighbours_unchanged:
            store.reset_removal(
                removal_id, proposal_fingerprint, "DeleteClips non riuscito"
            )
            raise ValidationError("DeleteClips non riuscito; target invariato")
        else:
            store.block_removal(
                removal_id, proposal_fingerprint,
                "DeleteClips con stato timeline ambiguo",
            )
            raise ValidationError("Rimozione bloccata: stato timeline ambiguo")
    elif removal.get("state") != "INTENT":
        raise ValidationError("Stato rimozione non eseguibile")

    intent_context = removal.get("intent_context")
    if not isinstance(intent_context, dict):
        store.block_removal(
            removal_id, proposal_fingerprint, "Contesto recovery mancante"
        )
        raise ValidationError("Rimozione bloccata: contesto recovery mancante")
    _, targets, candidates = _removal_live_state(project, timeline, handle)
    current_neighbours = candidates if not targets else [
        pair for pair in candidates if pair not in targets
    ]
    neighbours_unchanged = (
        _ordered_fingerprints(current_neighbours)
        == intent_context.get("neighbour_fingerprints")
    )
    if targets or not neighbours_unchanged:
        store.block_removal(
            removal_id, proposal_fingerprint,
            "Recovery non verificabile: target presente o invarianti vicini cambiati",
        )
        raise ValidationError(
            "Rimozione bloccata: recovery o invarianti timeline non verificabili"
        )
    receipt: dict[str, object] = {
        "target_absent": True,
        "ripple": False,
        "neighbour_ranges": list(intent_context.get("neighbour_ranges", [])),
        "verified_at": _time_text(selected),
    }
    completed = store.complete_removal(removal_id, receipt, selected)
    return _completed_removal_result(completed, store.workstation_id)
