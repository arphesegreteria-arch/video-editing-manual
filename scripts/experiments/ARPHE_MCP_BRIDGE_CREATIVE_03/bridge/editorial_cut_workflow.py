from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import math
from pathlib import Path
from typing import Any, Iterable

from .audio_provenance import verify_audio_manifest
from .config import CreativeConfig
from .editorial_jobs import EditorialJob, EditorialJobStore
from .editorial_markers import timeline_identity
from .editorial_selection_contract import SelectionContract, load_selection_contract
from .longform_tools import allowed_media, append_media_range, import_media_item
from .resolve_connection import RESOLVE_ACCESS_LOCK, safe_call
from .safety import PlaybackFpsActionRequired, ValidationError


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "editorial_selection_contract.json"


def _timelines(project: object) -> list[object]:
    count = int(safe_call(project, "GetTimelineCount") or 0)
    return [safe_call(project, "GetTimelineByIndex", index) for index in range(1, count + 1)]


def _timeline_by_name(project: object, name: str) -> object | None:
    matches = [timeline for timeline in _timelines(project)
               if timeline is not None and safe_call(timeline, "GetName") == name]
    if len(matches) > 1:
        raise ValidationError(f"Più timeline hanno il nome {name}")
    return matches[0] if matches else None


def _source_timeline(project: object, job: EditorialJob) -> object:
    timeline = _timeline_by_name(project, job.timeline_name)
    if timeline is None or timeline_identity(timeline) != job.timeline_identity:
        raise ValidationError("Timeline sorgente diversa dal job")
    return timeline


def _fraction(value: object, name: str) -> Fraction:
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValidationError(f"{name} non valido") from exc
    if result <= 0:
        raise ValidationError(f"{name} deve essere positivo")
    return result


def _source_format(timeline: object) -> dict[str, object]:
    try:
        width = int(safe_call(timeline, "GetSetting", "timelineResolutionWidth"))
        height = int(safe_call(timeline, "GetSetting", "timelineResolutionHeight"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Risoluzione sorgente non leggibile") from exc
    fps = _fraction(safe_call(timeline, "GetSetting", "timelineFrameRate"), "timelineFrameRate")
    playback = _fraction(safe_call(timeline, "GetSetting", "timelinePlaybackFrameRate"),
                         "timelinePlaybackFrameRate")
    if width <= 0 or height <= 0 or playback != fps:
        raise ValidationError("Formato sorgente o playback FPS non conforme")
    return {"width": width, "height": height, "fps": str(fps), "playback_fps": str(playback)}


def _project_matches_format(project: object, expected: dict[str, object]) -> bool:
    return (
        str(safe_call(project, "GetSetting", "timelineResolutionWidth")) == str(expected["width"])
        and str(safe_call(project, "GetSetting", "timelineResolutionHeight")) == str(expected["height"])
        and _fraction(safe_call(project, "GetSetting", "timelineFrameRate"), "project frame rate")
        == Fraction(str(expected["fps"]))
        and _fraction(safe_call(project, "GetSetting", "timelinePlaybackFrameRate"), "project playback")
        == Fraction(str(expected["playback_fps"]))
    )


def _folder_items(folder: object) -> Iterable[object]:
    for item in safe_call(folder, "GetClipList") or []:
        yield item
    for child in safe_call(folder, "GetSubFolderList") or []:
        yield from _folder_items(child)


def _media_by_name(pool: object, name: str) -> object:
    root = safe_call(pool, "GetRootFolder")
    matches = [item for item in _folder_items(root) if safe_call(item, "GetName") == name]
    if len(matches) != 1:
        raise ValidationError(f"Media pool item {name} mancante o ambiguo")
    return matches[0]


def _source_media(timeline: object, config: CreativeConfig, expected_fingerprint: str) -> object:
    items = safe_call(timeline, "GetItemListInTrack", "video", 1) or []
    media_items = [safe_call(item, "GetMediaPoolItem") for item in items]
    media_items = [item for item in media_items if item is not None]
    unique = {id(item): item for item in media_items}
    if len(unique) != 1:
        raise ValidationError("La timeline sorgente deve riferirsi a un solo media video")
    item = next(iter(unique.values()))
    path = allowed_media(str(safe_call(item, "GetClipProperty", "File Path") or ""), config)
    from .audio_provenance import media_fingerprint
    if media_fingerprint(path) != expected_fingerprint:
        raise ValidationError("Fingerprint media sorgente stale")
    return item


def _floor_frame(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return value.numerator // value.denominator


def _ceil_frame(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return -(-value.numerator // value.denominator)


def _media_fps(item: object, label: str, fallback: Fraction | None = None) -> Fraction:
    value = safe_call(item, "GetClipProperty", "FPS")
    if value in (None, "") and fallback is not None:
        return fallback
    return _fraction(value, f"FPS {label}")


def _set_and_verify_format(timeline: object, expected: dict[str, object]) -> None:
    requested = {
        "timelineResolutionWidth": str(expected["width"]),
        "timelineResolutionHeight": str(expected["height"]),
        "timelineFrameRate": str(expected["fps"]),
    }
    for key, value in requested.items():
        # Resolve may return False when an inherited value is already correct.
        # The API read-back is authoritative; a stale value still fails below.
        safe_call(timeline, "SetSetting", key, value)
    actual = _source_format(timeline)
    if actual != expected:
        raise ValidationError("Read-back formato timeline output non conforme")


def _media_name(item: object) -> str:
    return str(safe_call(item, "GetName") or "")


def _verify_operation(project: object, operation: dict[str, object],
                      expected_format: dict[str, object], contract: SelectionContract) -> None:
    timeline = _timeline_by_name(project, str(operation["timeline_name"]))
    if timeline is None or timeline_identity(timeline) != operation["timeline_identity"]:
        raise ValidationError("tampered_registered_output: timeline identity")
    if _source_format(timeline) != expected_format:
        raise ValidationError("tampered_registered_output: format")
    video = safe_call(timeline, "GetItemListInTrack", "video", 1) or []
    if len(video) != 2:
        raise ValidationError("tampered_registered_output: video item count")
    source_item, cta_item = video
    if _media_name(safe_call(cta_item, "GetMediaPoolItem")) != contract.cta_media_pool_name:
        raise ValidationError("tampered_registered_output: CTA")
    if int(safe_call(source_item, "GetLeftOffset") or 0) != int(operation["source_timeline_in_frame"]):
        raise ValidationError("tampered_registered_output: source in")
    source_duration = (
        int(safe_call(source_item, "GetEnd") or 0)
        - int(safe_call(source_item, "GetStart") or 0)
        + 1
    )
    if source_duration != int(operation["speech_timeline_frames"]):
        raise ValidationError("tampered_registered_output: source duration")
    if int(safe_call(cta_item, "GetStart") or 0) != int(operation["speech_timeline_frames"]):
        raise ValidationError("tampered_registered_output: CTA start")
    cta_duration = (
        int(safe_call(cta_item, "GetEnd") or 0)
        - int(safe_call(cta_item, "GetStart") or 0)
        + 1
    )
    if cta_duration != int(operation["cta_timeline_frames"]):
        raise ValidationError("tampered_registered_output: CTA duration")
    total = (
        int(safe_call(cta_item, "GetEnd") or 0)
        - int(safe_call(source_item, "GetStart") or 0)
        + 1
    )
    if total != int(operation["final_frames"]):
        raise ValidationError("tampered_registered_output: final duration")
    fps = Fraction(str(expected_format["fps"]))
    if Fraction(total, 1) / fps > Fraction(str(contract.max_final_seconds)):
        raise ValidationError("Output oltre 180 secondi")


def verify_editorial_outputs(project: object, job: EditorialJob,
                             contract: SelectionContract) -> dict[str, object]:
    source = _source_timeline(project, job)
    expected_format = _source_format(source)
    verified = 0
    for operation in job.operations:
        if operation.get("status") == "VERIFIED":
            _verify_operation(project, operation, expected_format, contract)
            verified += 1
    expected = sum(1 for decision in job.decisions if decision.get("outcome") != "REJECT")
    if verified != expected:
        raise ValidationError("Numero output verificati diverso dalle decisioni approvate")
    return {"ok": True, "verified_outputs": verified, "rejected": len(job.decisions) - expected}


def _block(store: EditorialJobStore, job: EditorialJob, reason: str) -> EditorialJob:
    return store.save(replace(
        job, state="BLOCKED", resume_state=job.state,
        operations=job.operations + ({"operation": "cut", "status": "BLOCKED", "reason": reason},),
    ), job.revision)


def _recover_blocked(store: EditorialJobStore, job: EditorialJob) -> EditorialJob:
    if job.state != "BLOCKED":
        return job
    if job.resume_state not in {"REVIEWED", "FAILED_RECOVERABLE", "CUT"}:
        raise ValidationError("Job BLOCKED non riprendibile dal cut workflow")
    return store.save(replace(job, state=job.resume_state, resume_state=None), job.revision)


def apply_or_resume_editorial_cuts(resolve: object, manager: object, config: CreativeConfig,
                                   store: EditorialJobStore, job_id: str,
                                   expected_review_fingerprint: str,
                                   *, audio_job_id: str | None = None) -> EditorialJob:
    contract = load_selection_contract(CONTRACT_PATH)
    with RESOLVE_ACCESS_LOCK:
        job = _recover_blocked(store, store.get(job_id, config.workstation_id))
        if job.state == "VERIFIED":
            project = safe_call(manager, "GetCurrentProject")
            verify_editorial_outputs(project, job, contract)
            return job
        if job.state not in {"REVIEWED", "FAILED_RECOVERABLE", "CUT"}:
            raise ValidationError("Il cut workflow richiede REVIEWED, FAILED_RECOVERABLE o CUT")
        if job.review_fingerprint != expected_review_fingerprint:
            raise ValidationError("Review fingerprint stale")
        project = safe_call(manager, "GetCurrentProject")
        if project is None or safe_call(project, "GetName") != job.project_name:
            raise ValidationError("Progetto corrente diverso dal job")
        source_timeline = _source_timeline(project, job)
        expected_format = _source_format(source_timeline)
        required_fps = Fraction(str(contract.required_project_fps))
        if (Fraction(str(expected_format["fps"])) != required_fps
                or Fraction(str(expected_format["playback_fps"])) != required_fps):
            raise PlaybackFpsActionRequired(
                expected_format["playback_fps"], str(contract.required_project_fps).rstrip("0").rstrip("."),
            )
        if not _project_matches_format(project, expected_format):
            raise ValidationError("Formato progetto diverso dalla timeline sorgente")
        source_item = _source_media(source_timeline, config, job.source_fingerprint)
        pool = safe_call(project, "GetMediaPool")
        if pool is None:
            raise ValidationError("Media pool non disponibile")
        cta_item = _media_by_name(pool, contract.cta_media_pool_name)
        fps = Fraction(str(expected_format["fps"]))
        source_fps = _media_fps(source_item, "media sorgente")
        cta_fps = _media_fps(cta_item, "CTA")
        cta_source_frames = math.ceil(float(contract.cta_duration_seconds * cta_fps))
        cta_timeline_frames = math.ceil(float(contract.cta_duration_seconds * fps))
        try:
            cta_available = int(safe_call(cta_item, "GetClipProperty", "Frames") or 0)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Durata CTA non leggibile") from exc
        if cta_available < cta_source_frames:
            raise ValidationError("CTA standard più corta del contratto")
        verified_audio = None
        if audio_job_id is not None:
            verified_audio = verify_audio_manifest(config, audio_job_id, job.source_fingerprint)
        decision_by_id = {str(item["candidate_id"]): item for item in job.decisions}
        if set(decision_by_id) != {str(item["candidate_id"]) for item in job.candidates}:
            raise ValidationError("Decisioni review incomplete")
        for decision in job.decisions:
            if float(decision["final_duration_seconds"]) > contract.max_final_seconds:
                raise ValidationError("Durata finale oltre il limite di 180 secondi")
        registered = {str(op.get("candidate_id")): op for op in job.operations
                      if op.get("status") in {"VERIFIED", "REJECTED"}}
        for decision in job.decisions:
            candidate_id = str(decision["candidate_id"])
            expected_name = f"ARPHE_{job.editorial_job_id[-8:]}_{candidate_id}"
            existing = _timeline_by_name(project, expected_name)
            operation = registered.get(candidate_id)
            if existing is not None:
                if operation is None or operation.get("timeline_identity") != timeline_identity(existing):
                    return _block(store, job, f"foreign_output_name_collision:{expected_name}")
        for operation in registered.values():
            if operation.get("status") == "VERIFIED":
                try:
                    _verify_operation(project, operation, expected_format, contract)
                except ValidationError as exc:
                    return _block(store, job, f"tampered_registered_output:{exc}")
        audio_item = None
        if verified_audio is not None:
            audio_item = import_media_item(resolve, pool, verified_audio.path)
            if audio_item is None:
                raise ValidationError("Import audio verificato fallito")
        audio_fps = None if audio_item is None else _media_fps(audio_item, "audio", fps)
        current = job
        try:
            for decision in job.decisions:
                candidate_id = str(decision["candidate_id"])
                if candidate_id in registered:
                    continue
                if decision["outcome"] == "REJECT":
                    operation = {"candidate_id": candidate_id, "status": "REJECTED",
                                 "reason": str(decision.get("reason", ""))}
                    current = store.save(replace(current, operations=current.operations + (operation,)),
                                         current.revision)
                    continue
                start_seconds = float(decision["source_start_seconds"])
                end_seconds = float(decision["source_end_seconds"])
                timeline_start = _floor_frame(start_seconds, fps)
                timeline_end = _ceil_frame(end_seconds, fps)
                speech_timeline_frames = timeline_end - timeline_start
                source_start = _floor_frame(start_seconds, source_fps)
                source_end = _ceil_frame(end_seconds, source_fps)
                final_frames = speech_timeline_frames + cta_timeline_frames
                if Fraction(final_frames, 1) / fps > Fraction(str(contract.max_final_seconds)):
                    raise ValidationError("Durata frame finale oltre 180 secondi")
                name = f"ARPHE_{job.editorial_job_id[-8:]}_{candidate_id}"
                timeline = safe_call(pool, "CreateEmptyTimeline", name)
                if timeline is None:
                    raise RuntimeError(f"create_timeline_failed:{candidate_id}")
                _set_and_verify_format(timeline, expected_format)
                if not safe_call(project, "SetCurrentTimeline", timeline):
                    raise RuntimeError(f"select_timeline_failed:{candidate_id}")
                if audio_item is None:
                    if not append_media_range(pool, source_item, 0, source_start, source_end):
                        raise RuntimeError(f"append_source_failed:{candidate_id}")
                else:
                    if not append_media_range(pool, source_item, 0, source_start, source_end, 1):
                        raise RuntimeError(f"append_video_failed:{candidate_id}")
                    audio_start = _floor_frame(start_seconds, audio_fps)
                    audio_end = _ceil_frame(end_seconds, audio_fps)
                    if not append_media_range(pool, audio_item, 0, audio_start, audio_end, 2):
                        raise RuntimeError(f"append_audio_failed:{candidate_id}")
                if not append_media_range(pool, cta_item, speech_timeline_frames,
                                          0, cta_source_frames):
                    raise RuntimeError(f"append_cta_failed:{candidate_id}")
                operation = {
                    "candidate_id": candidate_id,
                    "status": "VERIFIED",
                    "timeline_name": name,
                    "timeline_identity": timeline_identity(timeline),
                    "source_in_frame": source_start,
                    "source_out_frame_exclusive": source_end,
                    "source_timeline_in_frame": timeline_start,
                    "speech_timeline_frames": speech_timeline_frames,
                    "cta_frames": cta_timeline_frames,
                    "cta_source_frames": cta_source_frames,
                    "cta_timeline_frames": cta_timeline_frames,
                    "final_frames": final_frames,
                    "format": expected_format,
                    "audio_job_id": None if verified_audio is None else verified_audio.audio_job_id,
                }
                _verify_operation(project, operation, expected_format, contract)
                current = store.save(replace(current, operations=current.operations + (operation,)),
                                     current.revision)
            if current.state != "CUT":
                current = store.save(replace(current, state="CUT", resume_state=None), current.revision)
            verify_editorial_outputs(project, current, contract)
            return store.save(replace(current, state="VERIFIED"), current.revision)
        except ValidationError:
            raise
        except Exception as exc:
            resume = current.resume_state or ("REVIEWED" if current.state == "REVIEWED" else "CUT")
            return store.save(replace(
                current, state="FAILED_RECOVERABLE", resume_state=resume,
                operations=current.operations + ({"operation": "cut", "status": "FAILED",
                                                   "reason": str(exc)},),
            ), current.revision)
