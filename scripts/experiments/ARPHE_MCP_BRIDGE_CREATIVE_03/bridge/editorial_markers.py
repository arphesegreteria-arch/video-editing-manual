from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from typing import Any

from .editorial_jobs import EditorialJob, EditorialJobStore
from .editorial_selection_contract import SelectionContract
from .safety import ValidationError


def _call(target: object, method: str, *args: object) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise ValidationError(f"Timeline Resolve priva di {method}")
    try:
        return function(*args)
    except Exception as exc:
        raise ValidationError(f"Resolve {method} fallita: {exc}") from exc


def timeline_identity(timeline: object) -> str:
    unique = getattr(timeline, "GetUniqueId", None)
    if callable(unique):
        value = unique()
        if value is not None and str(value).strip():
            return "resolve:" + str(value).strip()
    payload: dict[str, object] = {}
    for method in ("GetName", "GetStartFrame", "GetEndFrame"):
        function = getattr(timeline, method, None)
        payload[method] = function() if callable(function) else None
    setting = getattr(timeline, "GetSetting", None)
    if callable(setting):
        for key in ("timelineResolutionWidth", "timelineResolutionHeight",
                    "timelineFrameRate", "timelinePlaybackFrameRate"):
            payload[key] = setting(key)
    if not payload.get("GetName"):
        raise ValidationError("Impossibile identificare la timeline Resolve")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "derived:" + hashlib.sha256(encoded).hexdigest()


def marker_specs(job: EditorialJob, contract: SelectionContract) -> tuple[dict[str, object], ...]:
    specs: list[dict[str, object]] = []
    for candidate in job.candidates:
        try:
            candidate_id = str(candidate["candidate_id"])
            start = int(candidate["source_in_frame"])
            end = int(candidate["source_out_frame_exclusive"])
            thesis = str(candidate["thesis"]).strip()
            context = str(candidate["indispensable_context"]).strip()
            final_seconds = float(candidate["final_duration_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"Candidate job incompleto per i marker: {exc}") from exc
        if not thesis or not context or end <= start:
            raise ValidationError("Candidate job non valido per i marker")
        specs.extend((
            {
                "candidate_id": candidate_id,
                "endpoint": "IN",
                "frame": start,
                "color": contract.marker_color,
                "name": f"ARPHE_{candidate_id}_IN",
                "note": (
                    f"{thesis}\nDurata finale stimata: {final_seconds:.2f}s\n"
                    f"Contesto indispensabile: {context}"
                ),
                "duration": 1,
                "customData": f"ARPHE_EDITORIAL:{job.editorial_job_id}:{candidate_id}:IN",
            },
            {
                "candidate_id": candidate_id,
                "endpoint": "OUT",
                "frame": end,
                "color": contract.marker_color,
                "name": f"ARPHE_{candidate_id}_OUT",
                "note": f"Fine proposta {candidate_id}",
                "duration": 1,
                "customData": f"ARPHE_EDITORIAL:{job.editorial_job_id}:{candidate_id}:OUT",
            },
        ))
    frames = [int(spec["frame"]) for spec in specs]
    if len(frames) != len(set(frames)):
        raise ValidationError("Due boundary editoriali richiedono lo stesso frame marker")
    return tuple(specs)


def _markers(timeline: object) -> dict[int, dict[str, object]]:
    raw = _call(timeline, "GetMarkers") or {}
    if not isinstance(raw, dict):
        raise ValidationError("GetMarkers non ha restituito un oggetto")
    result: dict[int, dict[str, object]] = {}
    for frame, marker in raw.items():
        if not isinstance(marker, dict):
            raise ValidationError("Marker Resolve malformato")
        result[int(frame)] = dict(marker)
    return result


def _marker_matches(actual: dict[str, object] | None, expected: dict[str, object]) -> bool:
    if actual is None:
        return False
    return all(actual.get(key) == expected[key]
               for key in ("color", "name", "note", "duration", "customData"))


def _identity_matches(timeline: object, job: EditorialJob) -> bool:
    return (_call(timeline, "GetName") == job.timeline_name
            and timeline_identity(timeline) == job.timeline_identity)


def _blocked(store: EditorialJobStore, job: EditorialJob, reason: str,
             *, frame: int | None = None) -> EditorialJob:
    operation: dict[str, object] = {"operation": "mark", "status": "BLOCKED", "reason": reason}
    if frame is not None:
        operation["frame"] = frame
    return store.save(
        replace(job, state="BLOCKED", resume_state=job.state,
                operations=job.operations + (operation,)),
        job.revision,
    )


def _rollback_added(timeline: object, added: list[dict[str, object]]) -> None:
    current = _markers(timeline)
    for spec in reversed(added):
        frame = int(spec["frame"])
        actual = current.get(frame)
        if actual is not None and actual.get("customData") == spec["customData"]:
            _call(timeline, "DeleteMarkerAtFrame", frame)


def verify_job_markers(timeline: object, job: EditorialJob) -> dict[str, object]:
    if not _identity_matches(timeline, job):
        raise ValidationError("Timeline corrente diversa dal job editoriale")
    actual = _markers(timeline)
    mismatches = [
        {"frame": int(spec["frame"]), "name": spec["name"]}
        for spec in job.markers
        if not _marker_matches(actual.get(int(spec["frame"])), spec)
    ]
    if mismatches:
        raise ValidationError(f"Marker job mancanti o modificati: {mismatches}")
    return {"ok": True, "marker_count": len(job.markers), "timeline": job.timeline_name}


def mark_candidates(timeline: object, store: EditorialJobStore, job: EditorialJob,
                    contract: SelectionContract) -> EditorialJob:
    if job.state == "MARKED":
        verify_job_markers(timeline, job)
        return job
    if job.state == "BLOCKED" and job.resume_state == "ANALYZED":
        job = store.save(replace(job, state="ANALYZED", resume_state=None), job.revision)
    if job.state != "ANALYZED":
        raise ValidationError("Il marking richiede un job ANALYZED")
    if not _identity_matches(timeline, job):
        return _blocked(store, job, "timeline_identity_mismatch")
    owner = store.active_for_timeline(job.timeline_identity)
    if owner is not None and owner.editorial_job_id != job.editorial_job_id:
        return _blocked(store, job, "timeline_markers_owned_by_another_job")
    specs = marker_specs(job, contract)
    before = _markers(timeline)
    for spec in specs:
        frame = int(spec["frame"])
        if frame in before:
            return _blocked(store, job, "marker_collision", frame=frame)
    added: list[dict[str, object]] = []
    try:
        for spec in specs:
            success = _call(
                timeline, "AddMarker", int(spec["frame"]), spec["color"], spec["name"],
                spec["note"], int(spec["duration"]), spec["customData"],
            )
            if not success:
                raise ValidationError(f"AddMarker rifiutata al frame {spec['frame']}")
            added.append(spec)
        after = _markers(timeline)
        for spec in specs:
            if not _marker_matches(after.get(int(spec["frame"])), spec):
                raise ValidationError(f"Read-back marker fallita al frame {spec['frame']}")
        for frame, marker in before.items():
            if after.get(frame) != marker:
                raise ValidationError(f"Marker preesistente modificato al frame {frame}")
        return store.save(replace(job, state="MARKED", markers=specs), job.revision)
    except Exception as exc:
        _rollback_added(timeline, added)
        restored = _markers(timeline)
        if restored != before:
            reason = f"marker_attempt_failed_and_rollback_incomplete:{type(exc).__name__}"
        else:
            reason = f"marker_attempt_failed:{type(exc).__name__}:{exc}"
        return _blocked(store, job, reason)


def cleanup_verified_markers(timeline: object, store: EditorialJobStore,
                             job: EditorialJob) -> EditorialJob:
    if job.state != "VERIFIED":
        raise ValidationError("La pulizia marker richiede un job VERIFIED")
    verify_job_markers(timeline, job)
    before = _markers(timeline)
    owned_frames = {int(spec["frame"]) for spec in job.markers}
    foreign = {frame: marker for frame, marker in before.items() if frame not in owned_frames}
    deleted: list[dict[str, object]] = []
    try:
        for spec in job.markers:
            frame = int(spec["frame"])
            current = _markers(timeline).get(frame)
            if not _marker_matches(current, spec):
                raise ValidationError(f"Marker job cambiato prima della pulizia: {frame}")
            if not _call(timeline, "DeleteMarkerAtFrame", frame):
                raise ValidationError(f"DeleteMarkerAtFrame rifiutata: {frame}")
            deleted.append(spec)
        if _markers(timeline) != foreign:
            raise ValidationError("La pulizia ha alterato marker estranei")
        return store.save(replace(job, state="CLOSED"), job.revision)
    except Exception as exc:
        current = _markers(timeline)
        for spec in deleted:
            frame = int(spec["frame"])
            if frame not in current:
                _call(timeline, "AddMarker", frame, spec["color"], spec["name"], spec["note"],
                      int(spec["duration"]), spec["customData"])
        return store.save(
            replace(job, state="BLOCKED", resume_state="VERIFIED",
                    operations=job.operations + ({"operation": "cleanup", "status": "BLOCKED",
                                                   "reason": str(exc)},)),
            job.revision,
        )
