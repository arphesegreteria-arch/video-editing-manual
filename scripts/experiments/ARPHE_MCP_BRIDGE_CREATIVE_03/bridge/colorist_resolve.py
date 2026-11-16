from __future__ import annotations

from pathlib import Path
from typing import Any

from .colorist_jobs import ColoristJob, after_version_names
from .safety import ValidationError


CLIP_METHODS = (
    "GetUniqueId", "GetName", "GetCurrentVersion", "GetVersionNameList",
    "AddVersion", "LoadVersionByName", "SetCDL", "GetNodeGraph", "CopyGrades",
)


def _call(obj: Any, name: str, *args: Any) -> Any:
    method = getattr(obj, name, None)
    if not callable(method):
        return None
    return method(*args)


def _clips(timeline: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}
    duplicates: set[str] = set()
    count = _call(timeline, "GetTrackCount", "video") or 0
    for track_index in range(1, int(count) + 1):
        for clip in _call(timeline, "GetItemListInTrack", "video", track_index) or []:
            clip_id = str(_call(clip, "GetUniqueId") or "")
            if not clip_id:
                continue
            if clip_id in found:
                duplicates.add(clip_id)
            found[clip_id] = clip
    if duplicates:
        raise ValidationError(f"clip_id duplicati nella timeline: {sorted(duplicates)}")
    return found


def _current_version(clip: Any) -> dict[str, object]:
    raw = _call(clip, "GetCurrentVersion")
    if not isinstance(raw, dict):
        raise ValidationError("Versione colore corrente non leggibile")
    name = raw.get("versionName")
    kind = raw.get("versionType")
    if not isinstance(name, str) or not name or kind != 0:
        raise ValidationError("È richiesta una versione colore locale attiva")
    return {"versionName": name, "versionType": 0}


def _validate_context(project: Any, timeline: Any, job: ColoristJob) -> dict[str, Any]:
    if job.state not in {"APPROVED", "APPLYING", "FAILED_RECOVERABLE",
                         "APPLIED", "ACCEPTED", "REJECTED"}:
        raise ValidationError("Piano Colorist non approvato")
    if str(_call(project, "GetName") or "") != job.project_name:
        raise ValidationError("Progetto Colorist stale")
    if str(_call(timeline, "GetName") or "") != job.timeline_name:
        raise ValidationError("Timeline Colorist stale")
    if str(_call(timeline, "GetUniqueId") or "") != job.timeline_identity:
        raise ValidationError("Identità timeline Colorist stale")
    clips = _clips(timeline)
    if set(job.clip_ids) - set(clips):
        raise ValidationError("Uno o più clip Colorist non sono più presenti")
    return clips


def inspect_colorist_context(project: Any, timeline: Any) -> dict[str, Any]:
    clips = _clips(timeline)
    items = []
    available = True
    for clip_id, clip in clips.items():
        methods = {name: callable(getattr(clip, name, None)) for name in CLIP_METHODS}
        available = available and all(methods.values())
        version = None
        try:
            version = _current_version(clip)
        except ValidationError:
            available = False
        items.append({
            "clip_id": clip_id,
            "name": str(_call(clip, "GetName") or ""),
            "start_frame": _call(clip, "GetStart"),
            "end_frame": _call(clip, "GetEnd"),
            "current_version": version,
            "api": methods,
        })
    return {
        "ok": True,
        "project_name": str(_call(project, "GetName") or ""),
        "timeline_name": str(_call(timeline, "GetName") or ""),
        "timeline_identity": str(_call(timeline, "GetUniqueId") or ""),
        "technically_available": bool(items and available),
        "clips": items,
    }


def _apply_to_clip(clip: Any, cdl: dict[str, object], drx_path: Path | None) -> None:
    if _call(clip, "SetCDL", dict(cdl)) is not True:
        raise RuntimeError("SetCDL ha restituito false")
    if drx_path is not None:
        graph = _call(clip, "GetNodeGraph")
        if graph is None or _call(graph, "ApplyGradeFromDRX", str(drx_path.resolve()), 0, False) is not True:
            raise RuntimeError("ApplyGradeFromDRX ha restituito false")


def apply_colorist_job(project: Any, timeline: Any, job: ColoristJob,
                       drx_path: Path | None = None) -> dict[str, Any]:
    if job.state != "APPLYING":
        raise ValidationError("Apply Colorist richiede piano APPLYING persistito")
    clips = _validate_context(project, timeline, job)
    if (job.drx_preset_name is None) != (drx_path is None):
        raise ValidationError("Preset DRX e asset risolto non corrispondono")
    if drx_path is not None and (not drx_path.is_file() or drx_path.suffix.lower() != ".drx"):
        raise ValidationError("Asset DRX Colorist non valido")

    after_names = after_version_names(job)
    drx_targets = ([job.reference_clip_id] if job.reference_clip_id is not None else list(job.clip_ids))
    for clip_id in job.clip_ids:
        clip = clips[clip_id]
        if not all(callable(getattr(clip, name, None)) for name in CLIP_METHODS):
            raise ValidationError(f"API Colorist incompleta per {clip_id}")
        if _current_version(clip) != job.before_versions[clip_id]:
            raise ValidationError(f"Versione colore stale per {clip_id}")
        versions = _call(clip, "GetVersionNameList", 0)
        if not isinstance(versions, (list, tuple)) or after_names[clip_id] in versions:
            raise ValidationError(f"Collisione version colore per {clip_id}")
    if drx_path is not None:
        for clip_id in drx_targets:
            graph = _call(clips[clip_id], "GetNodeGraph")
            node_count = _call(graph, "GetNumNodes") if graph is not None else None
            if (graph is None or not callable(getattr(graph, "ApplyGradeFromDRX", None))
                    or isinstance(node_count, bool) or not isinstance(node_count, int)
                    or node_count < 1):
                raise ValidationError(f"API DRX Colorist incompleta per {clip_id}")

    created: list[str] = []
    evidence: list[dict[str, object]] = []
    try:
        for clip_id in job.clip_ids:
            clip = clips[clip_id]
            after_name = after_names[clip_id]
            if _call(clip, "AddVersion", after_name, 0) is not True:
                raise RuntimeError(f"AddVersion fallita per {clip_id}")
            created.append(clip_id)
            if _call(clip, "LoadVersionByName", after_name, 0) is not True:
                raise RuntimeError(f"LoadVersionByName fallita per {clip_id}")

        if job.reference_clip_id is not None:
            reference = clips[job.reference_clip_id]
            _apply_to_clip(reference, job.cdl, drx_path)
            targets = [clips[clip_id] for clip_id in job.clip_ids if clip_id != job.reference_clip_id]
            if targets and _call(reference, "CopyGrades", targets) is not True:
                raise RuntimeError("CopyGrades ha restituito false")
        else:
            for clip_id in job.clip_ids:
                _apply_to_clip(clips[clip_id], job.cdl, drx_path)

        for clip_id in job.clip_ids:
            if _current_version(clips[clip_id])["versionName"] != after_names[clip_id]:
                raise RuntimeError(f"Read-back versione fallito per {clip_id}")
            evidence.append({
                "clip_id": clip_id,
                "before_version": job.before_versions[clip_id]["versionName"],
                "after_version": after_names[clip_id],
                "reference_clip_id": job.reference_clip_id,
                "cdl_applied_directly": job.reference_clip_id is None or clip_id == job.reference_clip_id,
                "drx_preset_name": job.drx_preset_name,
            })
        return {"ok": True, "colorist_job_id": job.colorist_job_id,
                "plan_fingerprint": job.plan_fingerprint, "evidence": evidence}
    except Exception as exc:
        restored: list[str] = []
        for clip_id in job.clip_ids:
            before = job.before_versions[clip_id]
            try:
                if (_call(clips[clip_id], "LoadVersionByName", before["versionName"], 0) is True
                        and _current_version(clips[clip_id])["versionName"] == before["versionName"]):
                    restored.append(clip_id)
            except Exception:
                pass
        fully_restored = set(restored) == set(job.clip_ids)
        return {
            "ok": False,
            "stage": "apply_colorist",
            "recoverable": fully_restored,
            "manual_recovery_required": not fully_restored,
            "error": str(exc),
            "created_versions": [{"clip_id": clip_id, "version": after_names[clip_id]} for clip_id in created],
            "restored_clip_ids": restored,
        }


def _after_from_evidence(job: ColoristJob) -> dict[str, str]:
    return {str(item["clip_id"]): str(item["after_version"]) for item in job.apply_evidence}


def validate_colorist_preview(project: Any, timeline: Any, job: ColoristJob,
                               clip_id: str, side: str) -> dict[str, str]:
    if job.state not in {"APPLIED", "ACCEPTED", "REJECTED"}:
        raise ValidationError("Preview Colorist richiede un apply completato")
    clips = _validate_context(project, timeline, job)
    if clip_id not in job.clip_ids:
        raise ValidationError("Clip fuori dal piano Colorist")
    if side not in {"before", "after"}:
        raise ValidationError("side deve essere before o after")
    after = _after_from_evidence(job)
    version = str(job.before_versions[clip_id]["versionName"]) if side == "before" else after[clip_id]
    if version not in (_call(clips[clip_id], "GetVersionNameList", 0) or []):
        raise ValidationError("Versione preview Colorist non disponibile")
    return {"restore_version": str(_current_version(clips[clip_id])["versionName"]),
            "target_version": version}


def current_colorist_version(project: Any, timeline: Any, job: ColoristJob, clip_id: str) -> str:
    clips = _validate_context(project, timeline, job)
    if clip_id not in job.clip_ids:
        raise ValidationError("Clip fuori dal piano Colorist")
    return str(_current_version(clips[clip_id])["versionName"])


def preview_colorist_version(project: Any, timeline: Any, job: ColoristJob,
                              clip_id: str, side: str) -> dict[str, Any]:
    preview = validate_colorist_preview(project, timeline, job, clip_id, side)
    clips = _validate_context(project, timeline, job)
    version = preview["target_version"]
    if _call(clips[clip_id], "LoadVersionByName", version, 0) is not True:
        raise RuntimeError("LoadVersionByName preview fallita")
    if _current_version(clips[clip_id])["versionName"] != version:
        raise RuntimeError("LoadVersionByName preview read-back fallita")
    return {"ok": True, "clip_id": clip_id, "side": side, "loaded_version": version}


def restore_colorist_preview(project: Any, timeline: Any, job: ColoristJob,
                             clip_id: str, restore_version: str) -> dict[str, Any]:
    if job.state not in {"APPLIED", "ACCEPTED", "REJECTED"}:
        raise ValidationError("Restore preview Colorist richiede un apply completato")
    clips = _validate_context(project, timeline, job)
    if clip_id not in job.preview_restore_versions or job.preview_restore_versions[clip_id] != restore_version:
        raise ValidationError("Tracking preview Colorist non corrispondente")
    if restore_version not in (_call(clips[clip_id], "GetVersionNameList", 0) or []):
        raise ValidationError("Versione di ripristino preview non disponibile")
    if _call(clips[clip_id], "LoadVersionByName", restore_version, 0) is not True:
        raise RuntimeError(f"Ripristino preview fallito per {clip_id}")
    if _current_version(clips[clip_id])["versionName"] != restore_version:
        raise RuntimeError(f"Ripristino preview read-back fallito per {clip_id}")
    return {"ok": True, "clip_id": clip_id, "restored_version": restore_version}

