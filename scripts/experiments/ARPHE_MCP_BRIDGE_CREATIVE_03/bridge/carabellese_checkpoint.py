from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .carabellese_jobs import CarabelleseJob, CarabelleseJobStore
from .editorial_markers import timeline_identity
from .safety import ValidationError


def _call(target: object, method: str, *args: object) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise ValidationError(f"API checkpoint non supportata: {method}")
    try:
        return function(*args)
    except Exception as exc:
        raise ValidationError(f"Resolve {method} fallita: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ValidationError(f"Checkpoint non leggibile: {exc}") from exc
    return digest.hexdigest()


def timeline_content_fingerprint(timeline: object) -> str:
    payload: dict[str, object] = {
        "start": _call(timeline, "GetStartFrame"), "end": _call(timeline, "GetEndFrame"),
        "settings": {key: _call(timeline, "GetSetting", key) for key in (
            "timelineResolutionWidth", "timelineResolutionHeight", "timelineFrameRate",
            "timelinePlaybackFrameRate")},
    }
    tracks = []
    for kind in ("video", "audio"):
        count = int(_call(timeline, "GetTrackCount", kind) or 0)
        for index in range(1, count + 1):
            items = _call(timeline, "GetItemListInTrack", kind, index) or []
            tracks.append({"kind": kind, "index": index, "items": [{
                "start": _call(item, "GetStart"), "end": _call(item, "GetEnd"),
                "duration": _call(item, "GetDuration"),
            } for item in items]})
    payload["tracks"] = tracks
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _project_timelines(project: object) -> list[object]:
    count = int(_call(project, "GetTimelineCount") or 0)
    return [_call(project, "GetTimelineByIndex", index) for index in range(1, count + 1)]


def verify_timeline_checkpoint(job: CarabelleseJob) -> dict[str, object]:
    manifest = job.checkpoint_manifest
    if not isinstance(manifest, dict) or job.checkpoint_fingerprint is None:
        raise ValidationError("Checkpoint Carabellese assente")
    required = {"path", "sha256", "size_bytes", "timeline_fingerprint", "source_fingerprint",
                "review_fingerprint", "exported_at"}
    if required - set(manifest):
        raise ValidationError("Manifest checkpoint Carabellese incompleto")
    path = Path(str(manifest["path"]))
    if path.suffix.lower() != ".drt" or not path.is_file():
        raise ValidationError("File checkpoint .drt mancante")
    size = path.stat().st_size
    if size <= 0 or size != manifest["size_bytes"]:
        raise ValidationError("Dimensione checkpoint non corrispondente")
    current_hash = _sha256(path)
    if current_hash != manifest["sha256"] or current_hash != job.checkpoint_fingerprint:
        raise ValidationError("Checkpoint hash non corrispondente")
    if (manifest["timeline_fingerprint"] != job.timeline_fingerprint
            or manifest["source_fingerprint"] != job.source_fingerprint
            or manifest["review_fingerprint"] != job.review_fingerprint):
        raise ValidationError("Checkpoint associato a evidenze diverse dal job")
    return {"ok": True, "sha256": current_hash, "size_bytes": size,
            "timeline_fingerprint": job.timeline_fingerprint}


def export_timeline_checkpoint(resolve: object, project: object, timeline: object,
                               store: CarabelleseJobStore, job: CarabelleseJob,
                               root: Path) -> CarabelleseJob:
    if job.state == "CHECKPOINTED":
        verify_timeline_checkpoint(job)
        return job
    if job.state != "REVIEWED":
        raise ValidationError("Il checkpoint richiede un job REVIEWED")
    export_type = getattr(resolve, "EXPORT_DRT", None)
    if export_type is None or not callable(getattr(timeline, "Export", None)):
        raise ValidationError("Export DRT non supportato dalla versione Resolve")
    if _call(project, "GetName") != job.project_name or _call(timeline, "GetName") != job.timeline_name:
        raise ValidationError("Target progetto/timeline diverso dal job")
    if timeline_identity(timeline) != job.timeline_identity:
        raise ValidationError("Identità timeline diversa dal job")
    if timeline_content_fingerprint(timeline) != job.timeline_fingerprint:
        raise ValidationError("Contenuto timeline cambiato prima del checkpoint")
    selected_root = root.expanduser().resolve()
    selected_root.mkdir(parents=True, exist_ok=True)
    path = selected_root / f"{job.carabellese_job_id}.drt"
    if path.exists():
        raise ValidationError("Collisione file checkpoint Carabellese")
    try:
        if not timeline.Export(str(path), export_type):
            raise ValidationError("Export DRT rifiutato da Resolve")
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValidationError("Export DRT mancante o vuoto")
        size = path.stat().st_size
        digest = _sha256(path)
        if path.stat().st_size != size or _sha256(path) != digest:
            raise ValidationError("Export DRT cambiato durante la verifica")
        manifest = {"path": str(path), "sha256": digest, "size_bytes": size,
                    "timeline_fingerprint": job.timeline_fingerprint,
                    "source_fingerprint": job.source_fingerprint,
                    "review_fingerprint": job.review_fingerprint,
                    "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        return store.save(replace(job, state="CHECKPOINTED", checkpoint_fingerprint=digest,
                                  checkpoint_manifest=manifest), job.revision)
    except Exception:
        if path.exists():
            path.unlink()
        raise


def restore_timeline_checkpoint(resolve: object, project: object, store: CarabelleseJobStore,
                                job: CarabelleseJob) -> CarabelleseJob:
    del resolve
    verify_timeline_checkpoint(job)
    manifest = job.checkpoint_manifest
    assert manifest is not None
    pool = _call(project, "GetMediaPool")
    for method in ("ImportTimelineFromFile", "DeleteTimelines"):
        if not callable(getattr(pool, method, None)):
            raise ValidationError(f"Restore DRT non supportato: {method}")
    failed = _call(project, "GetCurrentTimeline")
    if failed is None or _call(failed, "GetName") != job.timeline_name:
        raise ValidationError("Timeline canonica da ripristinare non trovata")
    if not callable(getattr(failed, "SetName", None)):
        raise ValidationError("Restore DRT non supportato: SetName")
    temp_name = f"__CARABELLESE_RESTORE_{job.carabellese_job_id[-8:]}"
    if any(_call(item, "GetName") == temp_name for item in _project_timelines(project)):
        raise ValidationError("Timeline temporanea restore già presente")
    imported = _call(pool, "ImportTimelineFromFile", str(manifest["path"]), {"timelineName": temp_name})
    if imported is None:
        raise ValidationError("Import checkpoint DRT fallito")
    try:
        if _call(imported, "GetName") != temp_name:
            raise ValidationError("Import checkpoint non possiede il nome temporaneo atteso")
        if timeline_content_fingerprint(imported) != job.timeline_fingerprint:
            raise ValidationError("Timeline importata con contenuto diverso dal checkpoint")
    except Exception:
        _call(pool, "DeleteTimelines", [imported])
        raise
    failed_temp = f"__CARABELLESE_FAILED_{job.carabellese_job_id[-8:]}"
    if not _call(failed, "SetName", failed_temp):
        _call(pool, "DeleteTimelines", [imported])
        raise ValidationError("Impossibile isolare timeline guasta")
    try:
        if not _call(imported, "SetName", job.timeline_name):
            raise ValidationError("Impossibile promuovere timeline ripristinata")
        if not _call(project, "SetCurrentTimeline", imported):
            raise ValidationError("Impossibile selezionare timeline ripristinata")
        if not _call(pool, "DeleteTimelines", [failed]):
            raise ValidationError("Impossibile rimuovere timeline guasta")
    except Exception:
        _call(failed, "SetName", job.timeline_name)
        raise
    canonical = [item for item in _project_timelines(project) if _call(item, "GetName") == job.timeline_name]
    if canonical != [imported]:
        raise ValidationError("Restore non ha prodotto una sola timeline canonica")
    operation = {"operation": "restore_checkpoint", "status": "VERIFIED",
                 "checkpoint_sha256": job.checkpoint_fingerprint}
    return store.save(replace(job, operations=job.operations + (operation,)), job.revision)
