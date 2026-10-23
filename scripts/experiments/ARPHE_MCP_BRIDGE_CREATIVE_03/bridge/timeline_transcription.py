"""Managed transcription of the exact audio heard on a Resolve timeline."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid
import wave
from typing import Any

from .config import CreativeConfig
from .feature_flags import require_capability
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name
from .timeline_tools import find_timeline
from .transcription_worker import ALLOWED_LANGUAGES, ALLOWED_MODELS, JOB_SCHEMA, _atomic_json
from .vertical_social_captions import timeline_edit_fingerprint
from .carabellese_transcription import _launch


JOB_ID = re.compile(r"^timeline_tx_[0-9a-f]{16}$")


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
    raw_status = str(payload["status"])
    status = "TRANSCRIBING" if raw_status in {"QUEUED", "RUNNING"} else raw_status
    result: dict[str, object] = {
        "ok": payload["status"] != "INTERRUPTED",
        "action": "get_timeline_audio_transcription_job",
        "job_id": payload["job_id"],
        "status": status,
        "source_project": source["project_name"],
        "source_timeline": source["timeline_name"],
        "duration_frames": source["duration_frames"],
        "fps": source["fps"],
        "saved": False,
    }
    if raw_status == "COMPLETED":
        result["transcript_file"] = Path(payload["output_path"]).name
        result["transcript_fingerprint"] = payload.get("transcript_fingerprint")
    return result


def _manifest_path(config: CreativeConfig, job_id: str) -> Path:
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValidationError("job_id trascrizione timeline non valido")
    return (config.transcript_root / ".timeline_jobs" / config.workstation_id /
            f"{job_id}.json").resolve()


def _load_manifest(config: CreativeConfig, job_id: str) -> tuple[Path, dict[str, Any]]:
    path = _manifest_path(config, job_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Job trascrizione timeline non leggibile: {exc}") from exc
    if (not isinstance(payload, dict) or payload.get("schema") != JOB_SCHEMA
            or payload.get("job_id") != job_id
            or payload.get("workstation_id") != config.workstation_id
            or not isinstance(payload.get("timeline_source"), dict)):
        raise ValidationError("Manifest trascrizione timeline non valido")
    return path, payload


def _wav_evidence(path: Path, expected_seconds: float, fps: float) -> tuple[str, float]:
    try:
        with wave.open(str(path.resolve(strict=True)), "rb") as handle:
            rate = handle.getframerate()
            width = handle.getsampwidth()
            channels = handle.getnchannels()
            frames = handle.getnframes()
    except (OSError, wave.Error) as exc:
        raise ValidationError(f"WAV timeline non leggibile: {exc}") from exc
    if rate != 48000 or width != 2 or channels not in {1, 2} or frames <= 0:
        raise ValidationError("Formato WAV timeline non conforme")
    duration = frames / rate
    if abs(duration - expected_seconds) > (1.0 / fps):
        raise ValidationError("Durata WAV timeline non coincide con la timeline")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest, round(duration, 6)


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
    before = _job_ids(project)
    config.audio_root.mkdir(parents=True, exist_ok=True)
    config.transcript_root.mkdir(parents=True, exist_ok=True)
    job_id = "timeline_tx_" + uuid.uuid4().hex[:16]
    restore_preset = "ARPHE_TMP_TIMELINE_AUDIO_" + uuid.uuid4().hex[:16]
    output_dir = (config.audio_root / "timeline-transcriptions" / config.workstation_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = arphe_name(f"{project_name}_{source_timeline}_{job_id[-8:]}", "TIMELINE_AUDIO")
    wav_path = (output_dir / f"{output_name}.wav").resolve()
    transcript_path = (config.transcript_root / config.workstation_id /
                       f"{output_name}.ARPHE_TRANSCRIPT_V1.json").resolve()
    created_ids: list[str] = []
    queued_id = ""
    if not safe_call(project, "SaveAsNewRenderPreset", restore_preset):
        raise ValidationError("Salvataggio temporaneo impostazioni Deliver fallito")
    try:
        if not safe_call(project, "SetCurrentTimeline", timeline):
            raise ValidationError("Selezione timeline per audio temporaneo fallita")
        if not safe_call(project, "LoadRenderPreset", "Audio Only"):
            raise ValidationError("Preset Resolve Audio Only non disponibile")
        settings = {
            "TargetDir": str(output_dir), "CustomName": output_name, "SelectAllFrames": True,
            "ExportVideo": False, "ExportAudio": True, "AudioCodec": "lpcm",
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
        restored_settings = bool(safe_call(project, "LoadRenderPreset", restore_preset))
        deleted_restore_preset = bool(safe_call(project, "DeleteRenderPreset", restore_preset))
        restored_timeline = bool(original_timeline and safe_call(project, "SetCurrentTimeline", original_timeline))
        if not (restored_settings and deleted_restore_preset and restored_timeline):
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


def get_timeline_audio_transcription_job(
    project: Any,
    config: CreativeConfig,
    registry: Any,
    job_id: str,
) -> dict[str, object]:
    """Advance or read one owned timeline-audio transcription job."""
    manifest_path, payload = _load_manifest(config, job_id)
    status = str(payload.get("status"))
    if status == "RENDERING":
        render_id = str(payload.get("render_job_id") or "")
        current_ids = set(_job_ids(project))
        if render_id not in current_ids:
            raise ValidationError("Job render audio timeline non più presente")
        render_status_raw = safe_call(project, "GetRenderJobStatus", render_id)
        render_status = (str(render_status_raw.get("JobStatus") or "")
                         if isinstance(render_status_raw, dict) else str(render_status_raw or ""))
        normalized = render_status.casefold()
        if normalized not in {"complete", "completed"}:
            if normalized in {"failed", "cancelled", "canceled"}:
                payload.update(status="INTERRUPTED", updated_at=_now(), error=f"RENDER_{render_status.upper()}")
                _atomic_json(manifest_path, payload)
            return _public(payload)
        source = payload["timeline_source"]
        expected_seconds = float(source["duration_frames"]) / float(source["fps"])
        try:
            digest, duration = _wav_evidence(Path(payload["source_path"]), expected_seconds,
                                             float(source["fps"]))
        except Exception as exc:
            payload.update(status="INTERRUPTED", updated_at=_now(), error=type(exc).__name__)
            _atomic_json(manifest_path, payload)
            raise
        if not safe_call(project, "DeleteRenderJob", render_id) or render_id in set(_job_ids(project)):
            raise RuntimeError("Rimozione job render audio timeline non confermata")
        source.update(audio_fingerprint=digest, audio_duration_seconds=duration)
        payload.update(status="QUEUED", progress_percent=0.0, source_fingerprint=digest,
                       updated_at=_now(), error=None)
        _atomic_json(manifest_path, payload)
        try:
            payload["pid"] = _launch(manifest_path)
            _atomic_json(manifest_path, payload)
        except OSError as exc:
            payload.update(status="INTERRUPTED", updated_at=_now(), error=type(exc).__name__)
            _atomic_json(manifest_path, payload)
            raise RuntimeError("Avvio worker trascrizione timeline fallito") from exc
        return _public(payload)
    if status == "COMPLETED":
        output = Path(payload["output_path"])
        try:
            transcript = json.loads(output.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Trascrizione timeline completata non leggibile: {exc}") from exc
        if transcript.get("timeline_source") != payload["timeline_source"]:
            raise ValidationError("Provenienza trascrizione timeline non corrispondente")
    return _public(payload)
