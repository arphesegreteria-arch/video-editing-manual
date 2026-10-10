from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import Any

from .carabellese_contract import CarabelleseContract
from .carabellese_jobs import CarabelleseJob, CarabelleseJobStore
from .editorial_markers import timeline_identity
from .safety import ValidationError


def _call(target: object, method: str, *args: object) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise ValidationError(f"Timeline Resolve priva di {method}")
    try:
        return function(*args)
    except Exception as exc:
        raise ValidationError(f"Resolve {method} fallita: {exc}") from exc


def carabellese_marker_specs(job: CarabelleseJob,
                             contract: CarabelleseContract) -> tuple[dict[str, object], ...]:
    specs = []
    for candidate in job.candidates:
        try:
            candidate_id = str(candidate["candidate_id"])
            kind = str(candidate["kind"])
            start = float(candidate["start_seconds"])
            end = float(candidate["end_seconds"])
            reason = str(candidate["reason"]).strip()
            review = candidate["review_required"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(f"Candidate Carabellese incompleto per marker: {exc}") from exc
        individual = kind in {"BOUNDARY_START", "BOUNDARY_END", "EDITORIAL_CUE", "MANUAL"} or review is True
        if not individual:
            continue
        if not candidate_id or not reason or end <= start or not isinstance(review, bool):
            raise ValidationError("Candidate Carabellese non valido per marker")
        for endpoint, seconds in (("IN", start), ("OUT", end)):
            specs.append({
                "candidate_id": candidate_id, "kind": kind, "endpoint": endpoint,
                "seconds": seconds, "color": contract.marker_color,
                "name": f"CAR_{candidate_id}_{endpoint}",
                "note": reason if endpoint == "IN" else f"Fine {candidate_id}", "duration": 1,
                "customData": f"CARABELLESE:{job.carabellese_job_id}:{candidate_id}:{endpoint}",
            })
    return tuple(specs)


def _markers(timeline: object) -> dict[int, dict[str, object]]:
    raw = _call(timeline, "GetMarkers") or {}
    if not isinstance(raw, dict):
        raise ValidationError("GetMarkers Carabellese non ha restituito un oggetto")
    result = {}
    for frame, marker in raw.items():
        if not isinstance(marker, dict):
            raise ValidationError("Marker Resolve malformato")
        result[int(frame)] = dict(marker)
    return result


def _matches(actual: dict[str, object] | None, expected: dict[str, object]) -> bool:
    return actual is not None and all(actual.get(key) == expected[key]
                                      for key in ("color", "name", "note", "duration", "customData"))


def _identity_matches(timeline: object, job: CarabelleseJob) -> bool:
    return _call(timeline, "GetName") == job.timeline_name and timeline_identity(timeline) == job.timeline_identity


def _timeline_fps(timeline: object) -> Fraction:
    raw = _call(timeline, "GetSetting", "timelineFrameRate")
    try:
        fps = Fraction(str(raw))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValidationError("FPS timeline Carabellese non leggibile") from exc
    if fps <= 0 or fps > 120:
        raise ValidationError("FPS timeline Carabellese fuori intervallo")
    return fps


def _floor_frame(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return value.numerator // value.denominator


def _ceil_frame(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return -(-value.numerator // value.denominator)


def _blocked(store: CarabelleseJobStore, job: CarabelleseJob, reason: str,
             frame: int | None = None) -> CarabelleseJob:
    operation: dict[str, object] = {"operation": "mark", "status": "BLOCKED", "reason": reason}
    if frame is not None:
        operation["frame"] = frame
    return store.save(replace(job, state="BLOCKED", resume_state=job.state,
                              operations=job.operations + (operation,)), job.revision)


def _rollback_added(timeline: object, added: list[dict[str, object]]) -> None:
    current = _markers(timeline)
    for spec in reversed(added):
        frame = int(spec["frame"])
        if current.get(frame, {}).get("customData") == spec["customData"]:
            _call(timeline, "DeleteMarkerAtFrame", frame)


def verify_carabellese_markers(timeline: object, job: CarabelleseJob) -> dict[str, object]:
    if not _identity_matches(timeline, job):
        raise ValidationError("Timeline corrente diversa dal job Carabellese")
    actual = _markers(timeline)
    missing = [int(spec["frame"]) for spec in job.markers
               if not _matches(actual.get(int(spec["frame"])), spec)]
    if missing:
        raise ValidationError(f"Marker Carabellese mancanti o modificati: {missing}")
    return {"ok": True, "marker_count": len(job.markers), "timeline": job.timeline_name}


def mark_carabellese_review(timeline: object, store: CarabelleseJobStore,
                            job: CarabelleseJob, contract: CarabelleseContract) -> CarabelleseJob:
    if job.state == "MARKED":
        verify_carabellese_markers(timeline, job)
        return job
    if job.state == "BLOCKED" and job.resume_state == "ANALYZED":
        job = store.save(replace(job, state="ANALYZED", resume_state=None), job.revision)
    if job.state != "ANALYZED":
        raise ValidationError("Il marking Carabellese richiede un job ANALYZED")
    if not _identity_matches(timeline, job):
        return _blocked(store, job, "timeline_identity_mismatch")
    try:
        fps = _timeline_fps(timeline)
        raw_specs = carabellese_marker_specs(job, contract)
        specs = tuple(dict(spec, frame=(_floor_frame(float(spec["seconds"]), fps)
                                        if spec["endpoint"] == "IN"
                                        else _ceil_frame(float(spec["seconds"]), fps)),
                           fps=str(fps)) for spec in raw_specs)
    except ValidationError as exc:
        return _blocked(store, job, f"marker_preflight:{exc}")
    frames = [int(spec["frame"]) for spec in specs]
    if len(frames) != len(set(frames)):
        return _blocked(store, job, "planned_marker_collision")
    before = _markers(timeline)
    for frame in frames:
        if frame in before:
            return _blocked(store, job, "marker_collision", frame)
    added = []
    try:
        for spec in specs:
            if not _call(timeline, "AddMarker", int(spec["frame"]), spec["color"], spec["name"],
                         spec["note"], int(spec["duration"]), spec["customData"]):
                raise ValidationError(f"AddMarker rifiutata al frame {spec['frame']}")
            added.append(spec)
        after = _markers(timeline)
        if any(not _matches(after.get(int(spec["frame"])), spec) for spec in specs):
            raise ValidationError("Read-back marker Carabellese fallita")
        if any(after.get(frame) != marker for frame, marker in before.items()):
            raise ValidationError("Marker estraneo modificato durante il marking")
        return store.save(replace(job, state="MARKED", markers=specs), job.revision)
    except Exception as exc:
        _rollback_added(timeline, added)
        reason = (f"marker_attempt_failed:{type(exc).__name__}:{exc}"
                  if _markers(timeline) == before else "marker_attempt_failed_and_rollback_incomplete")
        return _blocked(store, job, reason)


def cleanup_carabellese_markers(timeline: object, job: CarabelleseJob) -> dict[str, object]:
    verify_carabellese_markers(timeline, job)
    before = _markers(timeline)
    owned = {int(spec["frame"]) for spec in job.markers}
    foreign = {frame: marker for frame, marker in before.items() if frame not in owned}
    deleted = []
    try:
        for spec in job.markers:
            frame = int(spec["frame"])
            if not _matches(_markers(timeline).get(frame), spec):
                raise ValidationError(f"Marker Carabellese cambiato: {frame}")
            if not _call(timeline, "DeleteMarkerAtFrame", frame):
                raise ValidationError(f"DeleteMarkerAtFrame rifiutata: {frame}")
            deleted.append(spec)
        if _markers(timeline) != foreign:
            raise ValidationError("Pulizia Carabellese ha alterato marker estranei")
        return {"ok": True, "removed": len(deleted), "foreign_preserved": len(foreign)}
    except Exception:
        current = _markers(timeline)
        for spec in deleted:
            frame = int(spec["frame"])
            if frame not in current:
                _call(timeline, "AddMarker", frame, spec["color"], spec["name"], spec["note"],
                      int(spec["duration"]), spec["customData"])
        raise
