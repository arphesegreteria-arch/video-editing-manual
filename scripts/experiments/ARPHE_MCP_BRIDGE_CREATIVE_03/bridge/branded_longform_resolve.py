from __future__ import annotations

from typing import Any

from .branded_longform_jobs import BrandedLongformJob
from .resolve_connection import safe_call
from .safety import ValidationError


def _timelines(project: object) -> list[object]:
    return [item for index in range(1, int(safe_call(project, "GetTimelineCount") or 0) + 1)
            if (item := safe_call(project, "GetTimelineByIndex", index)) is not None]


def _find(project: object, name: str) -> object | None:
    matches = [item for item in _timelines(project) if str(safe_call(item, "GetName") or "") == name]
    if len(matches) > 1:
        raise ValidationError(f"Più timeline con nome {name}")
    return matches[0] if matches else None


def find_owned_timeline(project: object, job: BrandedLongformJob, name: str) -> object:
    _check_project(project, job)
    if name not in {job.original_timeline, job.cleanup_timeline, job.editorial_timeline}:
        raise ValidationError("Timeline non posseduta dal job")
    result = _find(project, name)
    if result is None:
        raise ValidationError(f"Timeline job non trovata: {name}")
    return result


def _check_project(project: object, job: BrandedLongformJob) -> None:
    if str(safe_call(project, "GetName") or "") != job.project_name:
        raise ValidationError("Progetto corrente diverso dal job branded longform")


def _duplicate(project: object, job: BrandedLongformJob, source_name: str, target_name: str) -> dict[str, Any]:
    _check_project(project, job)
    original = safe_call(project, "GetCurrentTimeline")
    if original is None:
        raise ValidationError("Serve una timeline corrente")
    source = _find(project, source_name)
    if source is None:
        raise ValidationError(f"Timeline sorgente non trovata: {source_name}")
    existing = _find(project, target_name)
    if existing is not None:
        return {"ok": True, "created_timeline": target_name, "existing": True, "returned_to_original": True}
    try:
        if not safe_call(project, "SetCurrentTimeline", source):
            raise ValidationError("Selezione timeline sorgente fallita")
        duplicated = safe_call(source, "DuplicateTimeline", target_name)
        if duplicated is None or str(safe_call(duplicated, "GetName") or "") != target_name:
            raise ValidationError("Duplicazione timeline fallita")
        return {"ok": True, "created_timeline": target_name, "existing": False, "returned_to_original": True}
    finally:
        if not safe_call(project, "SetCurrentTimeline", original):
            raise ValidationError("Ripristino timeline originale fallito")


def create_cleanup_timeline(project: object, job: BrandedLongformJob) -> dict[str, Any]:
    return _duplicate(project, job, job.original_timeline, job.cleanup_timeline)


def create_editorial_timeline(project: object, job: BrandedLongformJob) -> dict[str, Any]:
    return _duplicate(project, job, job.cleanup_timeline, job.editorial_timeline)


def add_proposal_markers(project: object, job: BrandedLongformJob,
                         proposals: list[dict[str, Any]]) -> dict[str, Any]:
    _check_project(project, job)
    timeline = _find(project, job.cleanup_timeline)
    if timeline is None:
        raise ValidationError("Timeline CLEANUP non trovata")
    existing = safe_call(timeline, "GetMarkers") or {}
    added = 0
    for proposal in proposals:
        proposal_id = str(proposal.get("proposal_id", ""))
        frame = int(proposal.get("start_frame", -1))
        if not proposal_id or frame < 0:
            raise ValidationError("Proposta marker non valida")
        custom = f"BRANDED_LONGFORM:{job.job_id}:{proposal_id}"
        actual = existing.get(frame) or existing.get(str(frame))
        if actual is not None:
            if actual.get("customData") == custom:
                continue
            raise ValidationError(f"Collisione marker al frame {frame}")
        if not safe_call(timeline, "AddMarker", frame, "Blue", f"BL_{proposal_id}",
                         f"{proposal.get('kind')}: {proposal.get('rationale')}", 1, custom):
            raise ValidationError(f"AddMarker fallita al frame {frame}")
        added += 1
        existing = safe_call(timeline, "GetMarkers") or {}
    return {"ok": True, "timeline": job.cleanup_timeline, "added": added,
            "proposal_count": len(proposals)}


def verify_branded_longform_timelines(project: object, job: BrandedLongformJob) -> dict[str, Any]:
    _check_project(project, job)
    names = {str(safe_call(item, "GetName") or "") for item in _timelines(project)}
    missing = [name for name in (job.original_timeline, job.cleanup_timeline, job.editorial_timeline)
               if name not in names]
    if missing:
        raise ValidationError(f"Timeline branded longform mancanti: {missing}")
    return {"ok": True, "original": job.original_timeline, "cleanup": job.cleanup_timeline,
            "editorial": job.editorial_timeline}
