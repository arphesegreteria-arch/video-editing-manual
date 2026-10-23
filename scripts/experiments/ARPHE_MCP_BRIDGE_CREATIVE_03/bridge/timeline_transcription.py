"""Managed transcription of the exact audio heard on a Resolve timeline."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name
from .timeline_tools import find_timeline
from .transcription_worker import ALLOWED_LANGUAGES, ALLOWED_MODELS, JOB_SCHEMA, _atomic_json
from .vertical_social_captions import timeline_edit_fingerprint


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _job_ids(project: Any) -> tuple[str, ...]:
    jobs = safe_call(project, "GetRenderJobList") or []
    values = tuple(str(job.get("JobId") or job.get("JobID") or "")
                   for job in jobs if isinstance(job, dict))
    if any(not value for value in values) or len(values) != len(set(values)):
        raise ValidationError("La coda Resolve contiene job senza ID o duplicati")
    return values


def _render_format(value: object) -> tuple[str, str]:
    if isinstance(value, dict):
        fmt = value.get("format") or value.get("Format")
        codec = value.get("codec") or value.get("Codec")
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        fmt, codec = value
    else:
        fmt = codec = None
    if not isinstance(fmt, str) or not fmt or not isinstance(codec, str) or not codec:
        raise ValidationError("Formato render corrente non leggibile")
    return fmt, codec


def _allowed(config: CreativeConfig, registry: Any, project_name: str, timeline_name: str) -> bool:
    return bool(
        (project_name in config.allowed_projects and timeline_name in config.allowed_timelines)
        or registry.timeline_allowed(project_name, timeline_name)
    )


def _public(payload: dict[str, Any]) -> dict[str, object]:
    source = payload["timeline_source"]
    return {
        "ok": payload["status"] != "INTERRUPTED",
        "action": "get_timeline_audio_transcription_job",
        "job_id": payload["job_id"],
        "status": payload["status"],
        "source_project": source["project_name"],
        "source_timeline": source["timeline_name"],
        "duration_frames": source["duration_frames"],
        "fps": source["fps"],
        "saved": False,
    }


def start_timeline_audio_transcription(
    project: Any,
    config: CreativeConfig,
    registry: Any,
    source_timeline: str,
    model: str = "small",
    language: str = "it",
) -> dict[str, object]:
    """Render one allowlisted timeline to an owned WAV job; never save the project."""
    if model not in ALLOWED_MODELS or language not in ALLOWED_LANGUAGES:
        raise ValidationError("Opzioni trascrizione timeline non consentite")
    if safe_call(project, "IsRenderingInProgress"):
        raise ValidationError("Resolve ha già un render attivo")
    project_name = str(safe_call(project, "GetName") or "")
    timeline = find_timeline(project, source_timeline)
    if timeline is None or not _allowed(config, registry, project_name, source_timeline):
        raise ValidationError("Timeline sorgente non disponibile o non autorizzata")
    require_capability("CAP_RENDER", config, None, project, timeline)
    start = safe_call(timeline, "GetStartFrame")
    end = safe_call(timeline, "GetEndFrame")
    try:
        fps = float(safe_call(timeline, "GetSetting", "timelineFrameRate"))
    except (TypeError, ValueError):
        raise ValidationError("FPS timeline non leggibile") from None
    if not isinstance(start, int) or not isinstance(end, int) or end <= start or fps <= 0:
        raise ValidationError("Range timeline non leggibile")

    original_timeline = safe_call(project, "GetCurrentTimeline")
    original_format = _render_format(safe_call(project, "GetCurrentRenderFormatAndCodec"))
    original_settings = safe_call(project, "GetRenderSettings")
    if not isinstance(original_settings, dict) or not original_settings:
        raise ValidationError("Impostazioni render correnti non leggibili")
    before = _job_ids(project)
    config.audio_root.mkdir(parents=True, exist_ok=True)
    config.transcript_root.mkdir(parents=True, exist_ok=True)
    job_id = "timeline_tx_" + uuid.uuid4().hex[:16]
    output_dir = (config.audio_root / "timeline-transcriptions" / config.workstation_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = arphe_name(f"{project_name}_{source_timeline}_{job_id[-8:]}", "TIMELINE_AUDIO")
    wav_path = (output_dir / f"{output_name}.wav").resolve()
    transcript_path = (config.transcript_root / config.workstation_id /
                       f"{output_name}.ARPHE_TRANSCRIPT_V1.json").resolve()
    created_ids: list[str] = []
    queued_id = ""
    try:
        if not safe_call(project, "SetCurrentTimeline", timeline):
            raise ValidationError("Selezione timeline per audio temporaneo fallita")
        if not safe_call(project, "SetCurrentRenderFormatAndCodec", "wav", "LinearPCM"):
            raise ValidationError("Formato WAV PCM rifiutato da Resolve")
        settings = {
            "TargetDir": str(output_dir), "CustomName": output_name, "SelectAllFrames": True,
            "ExportVideo": False, "ExportAudio": True, "AudioCodec": "LinearPCM",
            "AudioSampleRate": 48000,
        }
        if not safe_call(project, "SetRenderSettings", settings):
            raise ValidationError("Impostazioni audio timeline rifiutate da Resolve")
        returned = str(safe_call(project, "AddRenderJob") or "")
        after = _job_ids(project)
        created_ids = [value for value in after if value not in before]
        if len(created_ids) != 1 or returned != created_ids[0]:
            raise ValidationError("Job audio timeline non identificato in modo univoco")
        queued_id = returned
    except Exception:
        for render_id in created_ids:
            safe_call(project, "DeleteRenderJob", render_id)
        raise
    finally:
        restored_format = bool(safe_call(project, "SetCurrentRenderFormatAndCodec", *original_format))
        restored_settings = bool(safe_call(project, "SetRenderSettings", original_settings))
        restored_timeline = bool(original_timeline and safe_call(project, "SetCurrentTimeline", original_timeline))
        if not (restored_format and restored_settings and restored_timeline):
            if queued_id:
                safe_call(project, "DeleteRenderJob", queued_id)
            raise RuntimeError("Ripristino contesto render dopo audio timeline non confermato")

    timeline_source = {
        "workstation_id": config.workstation_id,
        "project_name": project_name,
        "timeline_name": source_timeline,
        "timeline_id": str(safe_call(timeline, "GetUniqueId") or ""),
        "timeline_edit_fingerprint": timeline_edit_fingerprint(timeline),
        "start_frame": start,
        "end_frame": end,
        "duration_frames": end - start,
        "fps": fps,
    }
    created = _now()
    payload: dict[str, Any] = {
        "schema": JOB_SCHEMA, "job_id": job_id, "workstation_id": config.workstation_id,
        "status": "RENDERING", "progress_percent": 0.0,
        "source_path": str(wav_path), "source_name": wav_path.name,
        "source_fingerprint": None, "media_root": str(config.audio_root.resolve()),
        "output_path": str(transcript_path), "transcript_root": str(config.transcript_root.resolve()),
        "model": model, "language": language, "created_at": created, "updated_at": created,
        "error": None, "render_job_id": queued_id, "render_queue_before": list(before),
        "timeline_source": timeline_source,
    }
    manifest = (config.transcript_root / ".timeline_jobs" / config.workstation_id /
                f"{job_id}.json").resolve()
    try:
        _atomic_json(manifest, payload)
        if not safe_call(project, "StartRendering", [queued_id], False):
            raise RuntimeError("Avvio render audio timeline fallito")
    except Exception:
        safe_call(project, "DeleteRenderJob", queued_id)
        raise
    return _public(payload)
