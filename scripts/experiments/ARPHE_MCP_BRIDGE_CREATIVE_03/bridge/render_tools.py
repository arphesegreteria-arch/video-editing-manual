from __future__ import annotations

from typing import Any
from pathlib import Path

from .artifact_records import artifact_store_for
from .config import CreativeConfig
from .feature_flags import require_capability
from .format_contract import require_project_playback
from fractions import Fraction
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name, ensure_no_collision, require_arphe_name
from .render_batches import batch_fingerprint, transition_batch


INSTAGRAM_REEL_RENDER_SETTINGS = {
    # Keep the master at a materially higher bitrate than the previous manual MOV
    # (about 2.5 Mb/s). Instagram will recompress the upload, so this leaves it a
    # clean source instead of asking a second encoder to recover thin typography.
    "FormatWidth": 1080,
    "FormatHeight": 1920,
    "FrameRate": 30.0,
    "ExportVideo": True,
    "ExportAudio": True,
}


def _render_job_ids(project: Any) -> tuple[str, ...]:
    jobs = safe_call(project, "GetRenderJobList") or []
    ids = tuple(str(job.get("JobId") or job.get("JobID") or "") for job in jobs if isinstance(job, dict))
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValidationError("La coda Resolve contiene job senza ID o duplicati")
    return ids


def _job_map(project: Any) -> dict[str, dict[str, Any]]:
    jobs = safe_call(project, "GetRenderJobList") or []
    return {str(job.get("JobId") or job.get("JobID")): dict(job) for job in jobs if isinstance(job, dict)}


def render_job_status(project: Any, job_id: str) -> str:
    """Read status from Resolve's dedicated API; queue listings may omit it."""
    value = safe_call(project, "GetRenderJobStatus", job_id)
    if isinstance(value, dict) and value.get("JobStatus"):
        return str(value["JobStatus"])
    return str(_job_map(project).get(job_id, {}).get("JobStatus") or "unknown")


def _register_render_staging(config: CreativeConfig, staging: Path, batch_id: str) -> None:
    artifact_store_for(config).register_path(
        staging,
        kind="directory",
        category="RENDER_STAGING",
        producer="prepare_render_batch",
        managed_root_id="render_root",
        batch_id=batch_id,
    )


def prepare_render_batch(project: Any, config: CreativeConfig, registry: Registry, batch_id: str) -> dict[str, Any]:
    batch = registry.render_batch(batch_id)
    if batch is None or batch.status != "CONFIRMED":
        raise ValidationError("Serve un render batch CONFIRMED")
    if str(safe_call(project, "GetName") or "") != batch.project_name:
        raise ValidationError("Il progetto corrente non corrisponde al batch")
    require_project_playback(project, Fraction(batch.playback_rate))
    require_capability("CAP_RENDER", config, None, project, safe_call(project, "GetCurrentTimeline"))
    before = _render_job_ids(project)
    timelines = _timeline_map(project)
    original = safe_call(project, "GetCurrentTimeline")
    staging = (config.render_root / "staging" / batch.batch_id).resolve()
    staging.mkdir(parents=True, exist_ok=False)
    created: list[str] = []
    expected: list[str] = []
    expected_durations: dict[str, str] = {}
    try:
        for timeline_name, output_name in zip(batch.timeline_names, batch.output_names, strict=True):
            timeline = timelines.get(timeline_name)
            if timeline is None or not safe_call(project, "SetCurrentTimeline", timeline):
                raise ValidationError(f"Timeline non disponibile: {timeline_name}")
            if not safe_call(project, "SetCurrentRenderFormatAndCodec", batch.container, batch.video_codec):
                raise ValidationError("Formato/codec render rifiutati")
            numerator, denominator = (int(v) for v in batch.frame_rate.split("/"))
            settings = {"TargetDir": str(staging), "CustomName": output_name, "SelectAllFrames": True,
                        "FormatWidth": batch.width, "FormatHeight": batch.height,
                        "FrameRate": numerator / denominator, "ExportVideo": True,
                        "ExportAudio": batch.audio_required}
            if batch.audio_codec:
                settings["AudioCodec"] = batch.audio_codec
            if batch.audio_sample_rate:
                settings["AudioSampleRate"] = batch.audio_sample_rate
            if batch.video_profile:
                settings["EncodingProfile"] = batch.video_profile
            if not safe_call(project, "SetRenderSettings", settings):
                raise ValidationError("Impostazioni render rifiutate")
            returned = safe_call(project, "AddRenderJob")
            after = _render_job_ids(project)
            new_ids = [value for value in after if value not in before and value not in created]
            if len(new_ids) != 1 or str(returned) != new_ids[0]:
                raise ValidationError("Impossibile identificare in modo univoco il nuovo job")
            created.append(new_ids[0])
            filename = f"{output_name}.{batch.container}"
            expected.append(filename)
            start = safe_call(timeline, "GetStartFrame")
            end = safe_call(timeline, "GetEndFrame")
            if not isinstance(start, int) or not isinstance(end, int) or end <= start:
                raise ValidationError("Durata timeline non leggibile")
            duration = Fraction(end - start, 1) / Fraction(batch.frame_rate)
            expected_durations[filename] = f"{duration.numerator}/{duration.denominator}"
    except Exception as exc:
        current = set(_render_job_ids(project))
        for job_id in created:
            if job_id in current:
                safe_call(project, "DeleteRenderJob", job_id)
        transition_batch(registry, batch.batch_id, "CONFIRMED", "FAILED_PREPARE",
                         {"error": str(exc), "orphaned_job_ids": [j for j in created if j in set(_render_job_ids(project))],
                          "expected_outputs": expected, "expected_durations": expected_durations,
                          "staging_directory": str(staging)})
        _register_render_staging(config, staging, batch.batch_id)
        raise
    finally:
        if original is not None:
            safe_call(project, "SetCurrentTimeline", original)
    snapshots = {job_id: _job_map(project)[job_id] for job_id in created}
    prepared = transition_batch(registry, batch.batch_id, "CONFIRMED", "PREPARED",
                                {"queue_before": list(before), "created_job_ids": created,
                                 "job_snapshots": snapshots, "expected_outputs": expected,
                                 "expected_durations": expected_durations,
                                 "staging_directory": str(staging)})
    try:
        _register_render_staging(config, staging, batch.batch_id)
    except Exception as exc:
        current = set(_render_job_ids(project))
        for job_id in created:
            if job_id in current:
                safe_call(project, "DeleteRenderJob", job_id)
        transition_batch(registry, batch.batch_id, "PREPARED", "FAILED_PREPARE",
                         {"artifact_registration_error": str(exc),
                          "orphaned_job_ids": [j for j in created if j in set(_render_job_ids(project))]})
        raise
    return {"ok": True, "action": "prepare_render_batch", "batch_id": batch_id,
            "created_job_ids": list(prepared.created_job_ids), "render_started": False,
            "next_action": "approve_render_batch"}


def start_render_batch(project: Any, registry: Registry, batch_id: str,
                       approval_token: str) -> dict[str, Any]:
    batch = registry.render_batch(batch_id)
    if batch is None or batch.status != "APPROVED":
        raise ValidationError("Serve un render batch APPROVED")
    if not approval_token or approval_token != batch.approval_token or approval_token != batch_fingerprint(batch):
        raise ValidationError("Approvazione batch non valida o obsoleta")
    if safe_call(project, "IsRenderingInProgress"):
        raise ValidationError("Resolve ha già un render attivo")
    current = _job_map(project)
    expected_ids = set(batch.queue_before) | set(batch.created_job_ids)
    if set(current) != expected_ids:
        raise ValidationError("La coda Resolve è cambiata dopo l'approvazione")
    snapshots = (batch.evidence or {}).get("job_snapshots", {})
    if any(current.get(job_id) != snapshots.get(job_id) for job_id in batch.created_job_ids):
        raise ValidationError("Le impostazioni della coda sono cambiate dopo l'approvazione")
    registry.acquire_render_lock(batch.project_name, batch.batch_id)
    started = bool(safe_call(project, "StartRendering", list(batch.created_job_ids), False))
    if not started:
        registry.release_render_lock(batch.project_name, batch.batch_id)
        return {"ok": False, "action": "start_render_batch", "batch_id": batch_id, "status": "APPROVED"}
    transition_batch(registry, batch_id, "APPROVED", "RENDERING", {"selective_start": True})
    return {"ok": True, "action": "start_render_batch", "batch_id": batch_id,
            "job_ids": list(batch.created_job_ids), "status": "RENDERING"}


def get_render_batch_status(project: Any, registry: Registry, batch_id: str) -> dict[str, Any]:
    batch = registry.render_batch(batch_id)
    if batch is None:
        raise ValidationError("Render batch non trovato")
    return {"ok": True, "action": "get_render_batch_status", "batch_id": batch_id,
            "status": batch.status,
            "jobs": {job_id: render_job_status(project, job_id)
                     for job_id in batch.created_job_ids}}


def cancel_render_batch(project: Any, registry: Registry, batch_id: str,
                        operator_role: str) -> dict[str, Any]:
    if operator_role not in {"TECNICO", "ALESSIO"}:
        raise ValidationError("La cancellazione richiede un ruolo tecnico")
    batch = registry.render_batch(batch_id)
    if batch is None or batch.status not in {"PREPARED", "APPROVED", "RENDERING"}:
        raise ValidationError("Batch non cancellabile")
    if batch.status == "RENDERING":
        lock = registry.render_lock(batch.project_name)
        if not lock or lock.get("batch_id") != batch.batch_id:
            raise ValidationError("Render attivo non posseduto dal bridge")
        if not safe_call(project, "StopRendering"):
            return {"ok": False, "action": "cancel_render_batch", "status": "RENDERING"}
    else:
        current = set(_render_job_ids(project))
        for job_id in batch.created_job_ids:
            if job_id in current:
                safe_call(project, "DeleteRenderJob", job_id)
    cancelled = transition_batch(registry, batch_id, batch.status, "CANCELLED", {"cancelled_by": operator_role})
    registry.release_render_lock(batch.project_name, batch.batch_id)
    return {"ok": True, "action": "cancel_render_batch", "batch_id": batch_id,
            "status": cancelled.status}


def render_preview(project: Any, timeline: Any, config: CreativeConfig, registry: Registry, output_name: str) -> dict:
    require_capability("CAP_RENDER", config, None, project, timeline)
    project_name = str(safe_call(project, "GetName") or "")
    timeline_name = str(safe_call(timeline, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    require_arphe_name(timeline_name, "timeline")
    if not (registry.timeline_allowed(project_name, timeline_name) or timeline_name in config.allowed_timelines):
        raise ValidationError("Render consentito solo su timeline creata o allowlisted dal bridge")
    config.render_root.mkdir(parents=True, exist_ok=True)
    name = arphe_name(output_name, "PREVIEW")
    existing_outputs = [item.stem for item in config.render_root.iterdir() if item.is_file()]
    ensure_no_collision(name, existing_outputs, "Output render")
    # The H.264 quality controls are not accepted by Resolve 21 on this
    # workstation. H.264 keeps the native YouTube preset; the lossless-ish
    # delivery master uses ProRes 422 HQ and therefore needs no H.264 preset.
    preset_ok = (bool(safe_call(project, "LoadRenderPreset", "YouTube - 1080p"))
                 if config.render_format == "mp4" else True)
    format_ok = bool(safe_call(project, "SetCurrentRenderFormatAndCodec", config.render_format, config.render_codec))
    settings = {
        "TargetDir": str(config.render_root), "CustomName": name, "SelectAllFrames": True,
        **INSTAGRAM_REEL_RENDER_SETTINGS,
    }
    settings_ok = bool(safe_call(project, "SetRenderSettings", settings))
    if not (preset_ok and format_ok and settings_ok):
        return {"ok": False, "action": "render_preview", "stage": "settings", "status": "PENDING"}
    job_id = safe_call(project, "AddRenderJob")
    started = bool(safe_call(project, "StartRendering", job_id)) if job_id else False
    return {"ok": bool(job_id and started), "action": "render_preview", "job_id": job_id,
            "output_name": name, "output_directory_disclosed": False,
            "quality_profile": ("instagram_reel_youtube_preset_vertical"
                                if config.render_format == "mp4"
                                else "instagram_reel_prores422hq_master"),
            "status": "PENDING"}


def _timeline_map(project: Any) -> dict[str, Any]:
    count = int(safe_call(project, "GetTimelineCount") or 0)
    return {str(safe_call(item, "GetName") or ""): item for index in range(1, count + 1)
            if (item := safe_call(project, "GetTimelineByIndex", index))}


def queue_longform_exports(manager: Any, project: Any, config: CreativeConfig, registry: Registry) -> dict:
    require_capability("CAP_LONGFORM", config, manager, project, safe_call(project, "GetCurrentTimeline"))
    project_name = str(safe_call(project, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    batch = registry.longform_batch(project_name)
    if not batch or not batch.get("clip_timelines"):
        raise ValidationError("Nessun batch long-form registrato per il progetto corrente")
    config.render_root.mkdir(parents=True, exist_ok=True)
    timelines = _timeline_map(project)
    existing = [item.stem for item in config.render_root.iterdir() if item.is_file()]
    for name in batch["clip_timelines"]:
        if timelines.get(name) is None or not registry.timeline_allowed(project_name, name):
            raise ValidationError(f"Timeline batch non disponibile: {name}")
        ensure_no_collision(name, existing, "Output render")
    original = safe_call(project, "GetCurrentTimeline")
    jobs = []
    try:
        for name in batch["clip_timelines"]:
            timeline = timelines.get(name)
            if not safe_call(project, "SetCurrentTimeline", timeline):
                raise RuntimeError(f"Impossibile selezionare la timeline {name}")
            format_ok = bool(safe_call(project, "SetCurrentRenderFormatAndCodec",
                                       config.render_format, config.render_codec))
            settings_ok = bool(safe_call(project, "SetRenderSettings", {
                "TargetDir": str(config.render_root), "CustomName": name, "SelectAllFrames": True,
            }))
            if not (format_ok and settings_ok):
                raise RuntimeError(f"Impostazioni render non applicate per {name}")
            job_id = safe_call(project, "AddRenderJob")
            if not job_id:
                raise RuntimeError(f"Job render non creato per {name}")
            jobs.append({"timeline": name, "output_name": name, "job_id": job_id})
    finally:
        if original:
            safe_call(project, "SetCurrentTimeline", original)
    registry.add_element(f"LONGFORM_EXPORTS::{project_name}", {"kind": "longform_exports", "jobs": jobs})
    return {"ok": True, "action": "queue_longform_exports", "project": project_name,
            "job_count": len(jobs), "jobs": jobs, "render_started": False,
            "output_directory_disclosed": False}


def start_longform_exports(project: Any, config: CreativeConfig, registry: Registry) -> dict:
    require_capability("CAP_RENDER", config, None, project, safe_call(project, "GetCurrentTimeline"))
    project_name = str(safe_call(project, "GetName") or "")
    record = registry.element(f"LONGFORM_EXPORTS::{project_name}")
    jobs = record.get("jobs", []) if record else []
    if not jobs:
        raise ValidationError("Prima preparare i job con queue_longform_exports")
    job_ids = [item["job_id"] for item in jobs]
    started = bool(safe_call(project, "StartRendering", job_ids))
    return {"ok": started, "action": "start_longform_exports", "project": project_name,
            "job_count": len(job_ids), "status": "RENDERING" if started else "PENDING"}


def queue_publish_package_exports(manager: Any, project: Any, config: CreativeConfig, registry: Registry,
                                  full_timeline_name: str, clip_timeline_names: list[str],
                                  output_directory: str, start_render: bool = True) -> dict:
    """Queue one full timeline plus publishable clips with a fixed YouTube/AAC preset."""
    current = safe_call(project, "GetCurrentTimeline")
    require_capability("CAP_LONGFORM", config, manager, project, current)
    if start_render:
        require_capability("CAP_RENDER", config, None, project, current)
    project_name = str(safe_call(project, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    names = [full_timeline_name, *clip_timeline_names]
    if len(names) < 2 or len(names) > 33 or len(set(names)) != len(names):
        raise ValidationError("Pacchetto render non valido")
    timelines = _timeline_map(project)
    for name in names:
        require_arphe_name(name, "timeline")
        if name not in timelines or not registry.timeline_allowed(project_name, name):
            raise ValidationError(f"Timeline non disponibile o non consentita: {name}")
    destination = Path(output_directory).expanduser().resolve(strict=True)
    desktop_candidates = {
        (Path.home() / "Desktop").resolve(),
        (Path.home() / "OneDrive" / "Desktop").resolve(),
    }
    if destination not in desktop_candidates or not destination.is_dir():
        raise ValidationError("Output consentito soltanto sul Desktop locale dell'utente")
    if safe_call(project, "GetRenderJobList"):
        raise ValidationError("La coda render deve essere vuota prima del batch pubblicabile")
    existing = {item.stem.casefold() for item in destination.iterdir() if item.is_file()}
    collisions = [name for name in names if name.casefold() in existing]
    if collisions:
        raise ValidationError("Output già presenti sul Desktop: " + ", ".join(collisions))
    original = current
    jobs = []
    try:
        for name in names:
            timeline = timelines[name]
            if not safe_call(project, "SetCurrentTimeline", timeline):
                raise RuntimeError(f"Selezione timeline fallita: {name}")
            if not safe_call(project, "LoadRenderPreset", "YouTube - 1080p"):
                raise RuntimeError("Preset YouTube - 1080p non disponibile")
            setting_groups = [
                {"TargetDir": str(destination), "CustomName": name, "SelectAllFrames": True,
                 "ExportVideo": True, "ExportAudio": True},
                {"FormatWidth": 1920, "FormatHeight": 1080, "FrameRate": 30.0},
                {"AudioCodec": "aac", "AudioSampleRate": 48000},
                {"EncodingProfile": "High"},
            ]
            if not all(bool(safe_call(project, "SetRenderSettings", settings)) for settings in setting_groups):
                raise RuntimeError(f"Impostazioni render rifiutate per {name}")
            job_id = safe_call(project, "AddRenderJob")
            if not job_id:
                raise RuntimeError(f"Creazione job fallita per {name}")
            jobs.append({"timeline": name, "job_id": job_id})
    finally:
        if original:
            safe_call(project, "SetCurrentTimeline", original)
    registry.add_element(f"PUBLISH_EXPORTS::{project_name}", {"kind": "publish_exports", "jobs": jobs})
    started = bool(safe_call(project, "StartRendering", [job["job_id"] for job in jobs], False)) if start_render else False
    return {"ok": bool(jobs) and (started if start_render else True),
            "action": "queue_publish_package_exports", "project": project_name,
            "job_count": len(jobs), "jobs": jobs, "preset": "YouTube - 1080p",
            "audio_codec": "AAC", "output_directory": "Desktop",
            "render_started": started, "status": "RENDERING" if started else "QUEUED"}
