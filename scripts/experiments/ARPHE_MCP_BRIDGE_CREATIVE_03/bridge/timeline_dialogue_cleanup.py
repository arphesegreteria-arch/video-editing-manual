"""Non-destructive cleanup of the exact dialogue heard on a Resolve timeline."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import wave
from typing import Any

from .audio_worker import DEREVERB_NATURAL_PRESET, PRESETS
from .artifact_producers import register_completed_audio_job
from .config import CreativeConfig
from .feature_flags import require_capability
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name
from .timeline_tools import duplicate_timeline, find_timeline, timeline_names
from .transcription_worker import _atomic_json
from .vertical_social_captions import timeline_edit_fingerprint


JOB_SCHEMA = "ARPHE_TIMELINE_DIALOGUE_CLEANUP_JOB_V1"
JOB_ID = re.compile(r"^dialogue_cleanup_[0-9a-f]{16}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _job_ids(project: Any) -> tuple[str, ...]:
    jobs = safe_call(project, "GetRenderJobList") or []
    values = tuple(str(job.get("JobId") or job.get("JobID") or "")
                   for job in jobs if isinstance(job, dict))
    if any(not value for value in values) or len(values) != len(set(values)):
        raise ValidationError("La coda Resolve contiene job senza ID o duplicati")
    return values


def _allowed(config: CreativeConfig, registry: Any,
             project_name: str, timeline_name: str) -> bool:
    return bool(
        (project_name in config.allowed_projects and timeline_name in config.allowed_timelines)
        or registry.timeline_allowed(project_name, timeline_name)
    )


def _manifest_path(config: CreativeConfig, job_id: str) -> Path:
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValidationError("job_id pulizia dialogo timeline non valido")
    return (config.audio_jobs_root / "timeline-dialogue-cleanup" /
            config.workstation_id / f"{job_id}.json").resolve()


def _public(payload: dict[str, Any]) -> dict[str, object]:
    source = payload["timeline_source"]
    result: dict[str, object] = {
        "ok": payload["status"] != "INTERRUPTED",
        "action": "get_timeline_dialogue_cleanup_job",
        "job_id": payload["job_id"],
        "status": payload["status"],
        "source_project": source["project_name"],
        "source_timeline": source["timeline_name"],
        "target_timeline": payload["target_timeline"],
        "duration_frames": source["duration_frames"],
        "fps": source["fps"],
        "preset": payload["preset"],
        "saved": False,
    }
    if payload["status"] == "COMPLETED":
        result.update(payload.get("readback") or {})
    if payload.get("error"):
        result["error"] = payload["error"]
    return result


def _load_manifest(config: CreativeConfig, job_id: str) -> tuple[Path, dict[str, Any]]:
    path = _manifest_path(config, job_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Job pulizia dialogo non leggibile: {exc}") from exc
    if (not isinstance(payload, dict) or payload.get("schema") != JOB_SCHEMA
            or payload.get("job_id") != job_id
            or payload.get("workstation_id") != config.workstation_id
            or not isinstance(payload.get("timeline_source"), dict)):
        raise ValidationError("Manifest pulizia dialogo non valido")
    managed_root = (config.audio_root / "timeline-dialogue-cleanup" /
                    config.workstation_id / job_id).resolve()
    source_path = Path(str(payload.get("source_path") or "")).resolve()
    processed_path = Path(str(payload.get("processed_path") or "")).resolve()
    worker_value = payload.get("audio_worker_manifest")
    worker_path = Path(str(worker_value)).resolve() if worker_value else None
    expected_worker = path.with_name(f"{job_id}.audio.json")
    if (source_path.parent != managed_root or processed_path.parent != managed_root
            or source_path.suffix.lower() != ".wav"
            or processed_path.suffix.lower() != ".wav"
            or source_path == processed_path
            or (worker_path is not None and worker_path != expected_worker)):
        raise ValidationError("Manifest pulizia dialogo con percorsi gestiti non validi")
    return path, payload


def _strict_wav_evidence(path: Path, expected_seconds: float, fps: float) -> tuple[str, float]:
    try:
        resolved = path.resolve(strict=True)
        with wave.open(str(resolved), "rb") as handle:
            rate = handle.getframerate()
            width = handle.getsampwidth()
            channels = handle.getnchannels()
            frames = handle.getnframes()
            compression = handle.getcomptype()
    except (OSError, wave.Error) as exc:
        raise ValidationError(f"WAV dialogo non leggibile: {exc}") from exc
    if compression != "NONE" or width not in {2, 3}:
        raise ValidationError("Il WAV dialogo deve essere PCM s16 o s24")
    if channels != 2:
        raise ValidationError("Il WAV dialogo deve essere stereo")
    if rate != 48000 or frames <= 0:
        raise ValidationError("Il WAV dialogo deve essere stereo PCM a 48 kHz")
    duration = frames / rate
    if abs(duration - expected_seconds) > (1.0 / fps):
        raise ValidationError("Durata WAV dialogo non coincide con la timeline")
    return hashlib.sha256(resolved.read_bytes()).hexdigest(), round(duration, 6)


def _launch_audio_worker(source: Path, output: Path, worker_manifest: Path,
                         preset: str) -> int:
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    process = subprocess.Popen(
        [sys.executable, "-m", "bridge.audio_worker", "--source", str(source),
         "--output", str(output), "--job", str(worker_manifest), "--preset", preset],
        cwd=str(Path(__file__).resolve().parents[1]), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
    )
    return int(process.pid)


def _single_clip_structure(timeline: Any) -> dict[str, Any]:
    if (safe_call(timeline, "GetTrackCount", "video") != 1
            or safe_call(timeline, "GetTrackCount", "audio") != 1):
        raise ValidationError("Il test dialogo richiede esattamente una traccia V1 e una A1")
    video_items = safe_call(timeline, "GetItemListInTrack", "video", 1) or []
    audio_items = safe_call(timeline, "GetItemListInTrack", "audio", 1) or []
    if len(video_items) != 1 or len(audio_items) != 1:
        raise ValidationError("Il test dialogo richiede esattamente una clip su V1 e una su A1")
    video, audio = video_items[0], audio_items[0]
    video_range = (safe_call(video, "GetStart"), safe_call(video, "GetEnd"))
    audio_range = (safe_call(audio, "GetStart"), safe_call(audio, "GetEnd"))
    if (not all(isinstance(value, int) and not isinstance(value, bool)
                for value in (*video_range, *audio_range))
            or video_range != audio_range or video_range[1] <= video_range[0]):
        raise ValidationError("Le clip V1 e A1 devono avere lo stesso range valido")
    video_media = safe_call(video, "GetMediaPoolItem")
    audio_media = safe_call(audio, "GetMediaPoolItem")
    if video_media is None or audio_media is None:
        raise ValidationError("Media V1/A1 non leggibili")
    audio_source_start = int(safe_call(audio, "GetSourceStartFrame") or 0)
    return {
        "record_start": video_range[0],
        "record_end": video_range[1],
        "video_media_id": str(safe_call(video_media, "GetUniqueId") or ""),
        "audio_media_id": str(safe_call(audio_media, "GetUniqueId") or ""),
        "audio_source_start": audio_source_start,
        # AppendToTimeline takes an inclusive endFrame while every bridge range
        # is half-open. Derive the exclusive source end from the verified clip
        # duration instead of trusting Resolve's ambiguous source-end read-back.
        "audio_source_end": audio_source_start + video_range[1] - video_range[0],
    }


def _matching_audio(timeline: Any, media: Any, start: int, end: int) -> list[Any]:
    return [
        item for item in (safe_call(timeline, "GetItemListInTrack", "audio", 1) or [])
        if safe_call(item, "GetMediaPoolItem") is media
        and safe_call(item, "GetStart") == start
        and safe_call(item, "GetEnd") == end
    ]


def _append_audio(pool: Any, timeline: Any, media: Any, source_start: int,
                  source_end: int, record_start: int, record_end: int,
                  *, require_return: bool) -> Any:
    appended = safe_call(pool, "AppendToTimeline", [{
        "mediaPoolItem": media,
        "startFrame": source_start,
        "endFrame": source_end - 1,
        "recordFrame": record_start,
        "mediaType": 2,
        "trackIndex": 1,
    }]) or []
    if require_return and len(appended) != 1:
        raise RuntimeError("Inserimento WAV dialogo fallito")
    matches = _matching_audio(timeline, media, record_start, record_end)
    if len(matches) != 1:
        raise ValidationError("Read-back WAV dialogo non corrispondente")
    return matches[0]


def _remove_matching_audio(timeline: Any, media: Any, start: int, end: int) -> None:
    matches = _matching_audio(timeline, media, start, end)
    if matches:
        safe_call(timeline, "DeleteClips", matches, False)
    if _matching_audio(timeline, media, start, end):
        raise ValidationError("Rollback WAV dialogo fallito")


def _apply_processed_audio(project: Any, config: CreativeConfig, registry: Any,
                           payload: dict[str, Any]) -> dict[str, object]:
    source_info = payload["timeline_source"]
    expected_seconds = float(source_info["duration_frames"]) / float(source_info["fps"])
    output_digest, _ = _strict_wav_evidence(
        Path(payload["processed_path"]), expected_seconds, float(source_info["fps"])
    )
    if output_digest != payload.get("output_fingerprint"):
        raise ValidationError("Fingerprint WAV dialogo non corrispondente prima dell'applicazione")
    source = find_timeline(project, str(source_info["timeline_name"]))
    if (source is None or str(safe_call(source, "GetUniqueId") or "") != source_info["timeline_id"]
            or timeline_edit_fingerprint(source) != source_info["timeline_edit_fingerprint"]):
        raise ValidationError("La timeline sorgente è cambiata prima dell'applicazione")
    source_structure = _single_clip_structure(source)
    structure_keys = (
        "record_start", "record_end", "video_media_id", "audio_media_id",
        "audio_source_start", "audio_source_end",
    )
    if any(source_structure[key] != source_info[key] for key in structure_keys):
        raise ValidationError("La timeline sorgente è cambiata prima dell'applicazione")
    duplicated = duplicate_timeline(
        project, config, registry, str(source_info["timeline_name"]), None,
        str(payload["target_timeline"]),
    )
    if not duplicated.get("ok"):
        raise RuntimeError("Duplicazione timeline per pulizia dialogo fallita")
    timeline = safe_call(project, "GetCurrentTimeline")
    if timeline is None or safe_call(timeline, "GetName") != payload["target_timeline"]:
        raise RuntimeError("Timeline duplicata non selezionata")
    structure = _single_clip_structure(timeline)
    if any(structure[key] != source_info[key] for key in structure_keys):
        raise ValidationError("La copia timeline non corrisponde alla sorgente verificata")
    original = (safe_call(timeline, "GetItemListInTrack", "audio", 1) or [None])[0]
    original_media = safe_call(original, "GetMediaPoolItem") if original else None
    if original is None or original_media is None:
        raise ValidationError("A1 originale della copia non disponibile")
    pool = safe_call(project, "GetMediaPool")
    import_digest, _ = _strict_wav_evidence(
        Path(payload["processed_path"]), expected_seconds, float(source_info["fps"])
    )
    if import_digest != payload.get("output_fingerprint"):
        raise ValidationError("Fingerprint WAV dialogo non corrispondente prima dell'import")
    imported = safe_call(pool, "ImportMedia", [str(Path(payload["processed_path"]).resolve())]) or []
    if len(imported) != 1:
        raise RuntimeError("Import WAV dialogo fallito")
    processed_media = imported[0]
    record_start = int(source_info["record_start"])
    record_end = int(source_info["record_end"])
    original_source_start = int(source_info["audio_source_start"])
    original_source_end = int(source_info["audio_source_end"])
    try:
        if not safe_call(timeline, "DeleteClips", [original], False):
            raise RuntimeError("Rimozione A1 originale dalla copia fallita")
        if _matching_audio(timeline, original_media, record_start, record_end):
            raise RuntimeError("Rimozione A1 originale dalla copia non confermata")
        replacement = _append_audio(
            pool, timeline, processed_media, 0, record_end - record_start,
            record_start, record_end, require_return=True,
        )
        verified = _single_clip_structure(timeline)
        if (verified["record_start"] != record_start or verified["record_end"] != record_end
                or verified["video_media_id"] != source_info["video_media_id"]
                or safe_call(replacement, "GetMediaPoolItem") is not processed_media):
            raise ValidationError("Read-back timeline dialogo non conforme")
        processed_path = Path(str(safe_call(
            processed_media, "GetClipProperty", "File Path") or "")).resolve()
        if processed_path != Path(payload["processed_path"]).resolve():
            raise ValidationError("Provenienza WAV applicato non corrispondente")
        if timeline_edit_fingerprint(source) != source_info["timeline_edit_fingerprint"]:
            raise ValidationError("La timeline sorgente è cambiata durante l'applicazione")
    except Exception:
        _remove_matching_audio(timeline, processed_media, record_start, record_end)
        if not _matching_audio(timeline, original_media, record_start, record_end):
            _append_audio(
                pool, timeline, original_media, original_source_start, original_source_end,
                record_start, record_end, require_return=False,
            )
        if len(_matching_audio(timeline, original_media, record_start, record_end)) != 1:
            raise RuntimeError("Rollback A1 originale non confermato")
        raise
    return {
        "source_preserved": True,
        "created_timeline": str(payload["target_timeline"]),
        "video_clip_count": 1,
        "audio_clip_count": 1,
        "video_range": [record_start, record_end],
        "audio_range": [record_start, record_end],
        "audio_path": str(Path(payload["processed_path"]).resolve()),
        "output_fingerprint": str(payload["output_fingerprint"]),
    }


def start_timeline_dialogue_cleanup_test(
    project: Any,
    config: CreativeConfig,
    registry: Any,
    source_timeline: str,
    target_name: str,
    preset: str = DEREVERB_NATURAL_PRESET,
) -> dict[str, object]:
    """Queue an owned exact-timeline audio render; never save the project."""
    if config.workstation_id != "PC_PERSONALE":
        raise ValidationError("Questa funzione e' abilitata solo su PC_PERSONALE")
    if preset not in PRESETS or preset != DEREVERB_NATURAL_PRESET:
        raise ValidationError("Preset pulizia dialogo non consentito")
    if safe_call(project, "IsRenderingInProgress"):
        raise ValidationError("Resolve ha già un render attivo")
    project_name = str(safe_call(project, "GetName") or "")
    timeline = find_timeline(project, source_timeline)
    if timeline is None or not _allowed(config, registry, project_name, source_timeline):
        raise ValidationError("Timeline sorgente non disponibile o non autorizzata")
    target = arphe_name(target_name, "DIALOGUE_CLEANUP_TEST")
    if target in timeline_names(project):
        raise ValidationError("Timeline target già esistente")
    require_capability("CAP_RENDER", config, None, project, timeline)
    structure = _single_clip_structure(timeline)
    start = safe_call(timeline, "GetStartFrame")
    end = safe_call(timeline, "GetEndFrame")
    try:
        fps = float(safe_call(timeline, "GetSetting", "timelineFrameRate"))
    except (TypeError, ValueError):
        raise ValidationError("FPS timeline non leggibile") from None
    if (not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(end, int) or isinstance(end, bool)
            or end <= start or fps <= 0
            or (start, end) != (structure["record_start"], structure["record_end"])):
        raise ValidationError("Range timeline e clip V1/A1 non corrispondente")

    original_timeline = safe_call(project, "GetCurrentTimeline")
    before = _job_ids(project)
    job_id = "dialogue_cleanup_" + uuid.uuid4().hex[:16]
    restore_preset = "ARPHE_TMP_DIALOGUE_AUDIO_" + uuid.uuid4().hex[:16]
    output_dir = (config.audio_root / "timeline-dialogue-cleanup" /
                  config.workstation_id / job_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    output_name = arphe_name(f"{project_name}_{source_timeline}_{job_id[-8:]}",
                             "DIALOGUE_SOURCE")
    wav_path = (output_dir / f"{output_name}.wav").resolve()
    processed_path = (output_dir / f"{output_name}_NATURAL_V5.wav").resolve()
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
            "TargetDir": str(output_dir),
            "CustomName": output_name,
            "SelectAllFrames": True,
            "ExportVideo": False,
            "ExportAudio": True,
            "AudioCodec": "lpcm",
            "AudioSampleRate": 48000,
            "AudioBitDepth": 16,
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
        restored_timeline = bool(
            original_timeline and safe_call(project, "SetCurrentTimeline", original_timeline)
        )
        if not (restored_settings and deleted_restore_preset and restored_timeline):
            if queued_id:
                safe_call(project, "DeleteRenderJob", queued_id)
            raise RuntimeError("Ripristino contesto render dopo pulizia dialogo non confermato")

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
        **structure,
    }
    created = _now()
    payload: dict[str, Any] = {
        "schema": JOB_SCHEMA,
        "job_id": job_id,
        "workstation_id": config.workstation_id,
        "status": "RENDERING",
        "progress_percent": 0.0,
        "preset": preset,
        "target_timeline": target,
        "source_path": str(wav_path),
        "processed_path": str(processed_path),
        "source_fingerprint": None,
        "output_fingerprint": None,
        "render_job_id": queued_id,
        "render_queue_before": list(before),
        "timeline_source": timeline_source,
        "created_at": created,
        "updated_at": created,
        "error": None,
    }
    manifest = _manifest_path(config, job_id)
    try:
        _atomic_json(manifest, payload)
        if not safe_call(project, "StartRendering", [queued_id], False):
            raise RuntimeError("Avvio render audio timeline fallito")
    except Exception:
        safe_call(project, "DeleteRenderJob", queued_id)
        raise
    return _public(payload)


def get_timeline_dialogue_cleanup_job(
    project: Any,
    config: CreativeConfig,
    registry: Any,
    job_id: str,
) -> dict[str, object]:
    manifest_path, payload = _load_manifest(config, job_id)
    source = payload["timeline_source"]
    if (config.workstation_id != "PC_PERSONALE"
            or str(safe_call(project, "GetName") or "") != source.get("project_name")):
        raise ValidationError("Il job pulizia dialogo appartiene a un altro contesto")
    status = str(payload.get("status"))
    if status == "RENDERING":
        render_id = str(payload.get("render_job_id") or "")
        current_ids = set(_job_ids(project))
        if render_id not in current_ids:
            payload.update(status="INTERRUPTED", updated_at=_now(), error="RENDER_JOB_MISSING")
            _atomic_json(manifest_path, payload)
            raise ValidationError("Job render dialogo non più presente")
        render_status_raw = safe_call(project, "GetRenderJobStatus", render_id)
        render_status = (str(render_status_raw.get("JobStatus") or "")
                         if isinstance(render_status_raw, dict) else str(render_status_raw or ""))
        normalized = render_status.casefold()
        if normalized not in {"complete", "completed"}:
            if normalized in {"failed", "cancelled", "canceled"}:
                payload.update(status="INTERRUPTED", updated_at=_now(),
                               error=f"RENDER_{render_status.upper()}")
                _atomic_json(manifest_path, payload)
            return _public(payload)
        expected_seconds = float(source["duration_frames"]) / float(source["fps"])
        try:
            digest, duration = _strict_wav_evidence(
                Path(payload["source_path"]), expected_seconds, float(source["fps"])
            )
        except Exception as exc:
            payload.update(status="INTERRUPTED", updated_at=_now(), error=type(exc).__name__)
            _atomic_json(manifest_path, payload)
            raise
        if not safe_call(project, "DeleteRenderJob", render_id) or render_id in set(_job_ids(project)):
            raise RuntimeError("Rimozione job render dialogo non confermata")
        output = Path(payload["processed_path"]).resolve()
        worker_manifest = manifest_path.with_name(f"{job_id}.audio.json")
        worker_payload = {
            "schema": "ARPHE_AUDIO_JOB_V2",
            "job_id": "audio_" + job_id[-16:],
            "status": "QUEUED",
            "progress_percent": 0,
            "preset": payload["preset"],
            "source_name": Path(payload["source_path"]).name,
            "source_fingerprint": digest,
            "output_path": str(output),
            "workstation_id": config.workstation_id,
            "creative_config_path": str(config.path.resolve()),
        }
        _atomic_json(worker_manifest, worker_payload)
        payload.update(
            status="PROCESSING", progress_percent=0.0, source_fingerprint=digest,
            source_duration_seconds=duration, audio_worker_manifest=str(worker_manifest),
            updated_at=_now(), error=None,
        )
        _atomic_json(manifest_path, payload)
        try:
            payload["audio_worker_pid"] = _launch_audio_worker(
                Path(payload["source_path"]), output, worker_manifest, str(payload["preset"])
            )
            _atomic_json(manifest_path, payload)
        except OSError as exc:
            payload.update(status="INTERRUPTED", updated_at=_now(), error=type(exc).__name__)
            _atomic_json(manifest_path, payload)
            raise RuntimeError("Avvio worker pulizia dialogo fallito") from exc
        return _public(payload)
    if status == "PROCESSING":
        worker_path = Path(str(payload.get("audio_worker_manifest") or ""))
        try:
            worker = json.loads(worker_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Manifest worker audio non leggibile: {exc}") from exc
        worker_status = str(worker.get("status") or "")
        if worker_status in {"QUEUED", "RUNNING"}:
            payload["progress_percent"] = worker.get("progress_percent", 0.0)
            _atomic_json(manifest_path, payload)
            return _public(payload)
        if worker_status != "COMPLETED":
            payload.update(status="INTERRUPTED", updated_at=_now(), error="AUDIO_WORKER_FAILED")
            _atomic_json(manifest_path, payload)
            return _public(payload)
        try:
            if (worker.get("schema") != "ARPHE_AUDIO_JOB_V2"
                    or worker.get("preset") != payload["preset"]
                    or worker.get("source_fingerprint") != payload["source_fingerprint"]
                    or Path(str(worker.get("output_path") or "")).resolve()
                    != Path(payload["processed_path"]).resolve()):
                raise ValidationError("Manifest worker audio non corrispondente")
            output_digest, output_duration = _strict_wav_evidence(
                Path(payload["processed_path"]),
                float(source["duration_frames"]) / float(source["fps"]),
                float(source["fps"]),
            )
            if worker.get("output_sha256") != output_digest:
                raise ValidationError("Fingerprint WAV dialogo non corrispondente")
        except Exception as exc:
            payload.update(status="INTERRUPTED", updated_at=_now(), error=type(exc).__name__)
            _atomic_json(manifest_path, payload)
            raise
        payload.update(status="APPLYING", progress_percent=100.0,
                       output_fingerprint=output_digest,
                       output_duration_seconds=output_duration,
                       updated_at=_now(), error=None)
        _atomic_json(manifest_path, payload)
        return _public(payload)
    if status == "APPLYING":
        try:
            readback = _apply_processed_audio(project, config, registry, payload)
        except Exception as exc:
            payload.update(status="INTERRUPTED", updated_at=_now(), error=type(exc).__name__)
            _atomic_json(manifest_path, payload)
            raise
        payload.update(status="COMPLETED", updated_at=_now(), error=None, readback=readback)
        _atomic_json(manifest_path, payload)
        register_completed_audio_job(config, manifest_path)
        return _public(payload)
    return _public(payload)
