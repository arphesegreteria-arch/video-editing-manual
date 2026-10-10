from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .audio_provenance import media_fingerprint
from .carabellese_checkpoint import timeline_content_fingerprint, verify_timeline_checkpoint
from .carabellese_contract import (carabellese_contract_fingerprint,
                                   load_carabellese_contract)
from .carabellese_jobs import CarabelleseJob, CarabelleseJobStore
from .config import CreativeConfig
from .editorial_markers import timeline_identity
from .longform_tools import allowed_media
from .resolve_connection import RESOLVE_ACCESS_LOCK
from .safety import ValidationError


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "carabellese_cleanup_contract.json"


def _append_journal(config: CreativeConfig, payload: dict[str, object]) -> None:
    path = config.carabellese_journal_path
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"workstation_id": config.workstation_id, **payload}
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ValidationError(f"Journal Carabellese non scrivibile: {exc}") from exc


def read_carabellese_journal(config: CreativeConfig, job_id: str) -> tuple[dict[str, object], ...]:
    path = config.carabellese_journal_path
    if not path.is_file():
        return ()
    events = []
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError("evento non oggetto")
            if raw.get("job_id") == job_id:
                events.append(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValidationError(f"Journal Carabellese non leggibile: {exc}") from exc
    return tuple(events)


def _call(target: object, method: str, *args: object) -> Any:
    function = getattr(target, method, None)
    if not callable(function):
        raise ValidationError(f"API apply Carabellese non supportata: {method}")
    try:
        return function(*args)
    except Exception as exc:
        raise ValidationError(f"Resolve {method} fallita: {exc}") from exc


def _fraction(value: object, name: str) -> Fraction:
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValidationError(f"{name} non valido") from exc
    if result <= 0 or result > 120:
        raise ValidationError(f"{name} fuori intervallo")
    return result


def _floor(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return value.numerator // value.denominator


def _ceil(seconds: float, fps: Fraction) -> int:
    value = Fraction(str(seconds)) * fps
    return -(-value.numerator // value.denominator)


def _proposal_fingerprint(job: CarabelleseJob) -> str:
    encoded = json.dumps(list(job.candidates), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _expected_timeline_fingerprint(job: CarabelleseJob) -> str:
    summaries = [op for op in job.operations if op.get("operation") == "apply_summary"
                 and op.get("status") == "VERIFIED"]
    return str(summaries[-1]["timeline_fingerprint_after"]) if summaries else job.timeline_fingerprint


def media_source_identity(media: object) -> tuple[str, str] | None:
    unique = getattr(media, "GetUniqueId", None)
    if callable(unique):
        value = unique()
        if value is not None and str(value).strip():
            return "resolve", str(value).strip()
    properties = getattr(media, "GetClipProperty", None)
    if callable(properties):
        value = properties("File Path")
        if value is not None and str(value).strip():
            return "path", str(Path(str(value)).resolve()).casefold()
    return None


def _timeline_shape(timeline: object) -> tuple[object, object, object]:
    if int(_call(timeline, "GetTrackCount", "video") or 0) != 1 \
            or int(_call(timeline, "GetTrackCount", "audio") or 0) != 1:
        raise ValidationError("Timeline deve avere una sola traccia video e audio")
    video = _call(timeline, "GetItemListInTrack", "video", 1) or []
    audio = _call(timeline, "GetItemListInTrack", "audio", 1) or []
    if len(video) != 1 or len(audio) != 1:
        raise ValidationError("Timeline deve contenere una singola clip A/V sorgente")
    video_media, audio_media = _call(video[0], "GetMediaPoolItem"), _call(audio[0], "GetMediaPoolItem")
    video_identity = media_source_identity(video_media) if video_media is not None else None
    audio_identity = media_source_identity(audio_media) if audio_media is not None else None
    if video_media is None or audio_media is None or video_identity is None \
            or video_identity != audio_identity:
        raise ValidationError("Clip video e audio non sono collegate alla stessa sorgente")
    if (_call(video[0], "GetStart") != _call(audio[0], "GetStart")
            or _call(video[0], "GetDuration") != _call(audio[0], "GetDuration")):
        raise ValidationError("Clip video e audio non sono allineate")
    return video[0], audio[0], video_media


def _owned_markers_only(timeline: object, job: CarabelleseJob) -> None:
    markers = _call(timeline, "GetMarkers") or {}
    prefix = f"CARABELLESE:{job.carabellese_job_id}:"
    if not isinstance(markers, dict) or any(
        not isinstance(marker, dict) or not str(marker.get("customData", "")).startswith(prefix)
        for marker in markers.values()
    ):
        raise ValidationError("Timeline contiene marker estranei al job Carabellese")


def inspect_carabellese_apply_support(resolve: object, project: object, timeline: object,
                                      job: CarabelleseJob) -> dict[str, object]:
    del resolve
    reasons = []
    try:
        effective_state = job.resume_state if job.state == "BLOCKED" else job.state
        if effective_state not in {"CHECKPOINTED", "APPLYING", "FAILED_RECOVERABLE", "VERIFIED"}:
            raise ValidationError("Stato job non applicabile")
        verify_timeline_checkpoint(job)
        current_timeline = _call(project, "GetCurrentTimeline")
        if (_call(project, "GetName") != job.project_name
                or timeline_identity(current_timeline) != timeline_identity(timeline)):
            raise ValidationError("Progetto o timeline corrente diversi dal job")
        if _call(timeline, "GetName") != job.timeline_name or timeline_identity(timeline) != job.timeline_identity:
            raise ValidationError("Identità timeline diversa dal job")
        fps = _fraction(_call(timeline, "GetSetting", "timelineFrameRate"), "timelineFrameRate")
        playback_value = _call(timeline, "GetSetting", "timelinePlaybackFrameRate")
        if playback_value is None or not str(playback_value).strip():
            playback_value = _call(project, "GetSetting", "timelinePlaybackFrameRate")
        playback = _fraction(playback_value, "timelinePlaybackFrameRate")
        if playback != fps:
            raise ValidationError("Playback FPS diverso dagli FPS timeline")
        if timeline_content_fingerprint(timeline) != _expected_timeline_fingerprint(job):
            raise ValidationError("Timeline cambiata rispetto allo stato registrato")
        if effective_state != "VERIFIED":
            _timeline_shape(timeline)
        _owned_markers_only(timeline, job)
        pool = _call(project, "GetMediaPool")
        if effective_state != "VERIFIED":
            for target, methods in ((timeline, ("AddTrack", "DeleteClips", "DeleteTrack")),
                                    (pool, ("AppendToTimeline",))):
                for method in methods:
                    if not callable(getattr(target, method, None)):
                        raise ValidationError(f"API staging non supportata: {method}")
    except ValidationError as exc:
        reasons.append(str(exc))
    return {"supported": not reasons, "reasons": reasons,
            "writes_to_resolve": False, "timeline": job.timeline_name}


def _find_transcript(config: CreativeConfig, job: CarabelleseJob) -> Path:
    matches = []
    if config.transcript_root.is_dir():
        for path in config.transcript_root.rglob("*.json"):
            if ".carabellese_jobs" in path.parts:
                continue
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            if digest == job.transcript_fingerprint:
                matches.append(path)
    if len(matches) != 1:
        raise ValidationError("Transcript fissato mancante o ambiguo")
    try:
        data = json.loads(matches[0].read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Transcript fissato non leggibile: {exc}") from exc
    if (data.get("schema") != "ARPHE_TRANSCRIPT_V1" or data.get("status") != "complete"
            or not isinstance(data.get("source"), dict)
            or data["source"].get("fingerprint") != job.source_fingerprint):
        raise ValidationError("Transcript fissato non appartiene alla sorgente")
    return matches[0]


def _validate_bound_inputs(config: CreativeConfig, job: CarabelleseJob, media: object) -> None:
    contract = load_carabellese_contract(CONTRACT_PATH)
    if job.contract_fingerprint != carabellese_contract_fingerprint(contract):
        raise ValidationError("Contratto Carabellese stale")
    if job.proposal_fingerprint != _proposal_fingerprint(job):
        raise ValidationError("Proposte Carabellese stale")
    _find_transcript(config, job)
    path = allowed_media(str(_call(media, "GetClipProperty", "File Path") or ""), config)
    if media_fingerprint(path) != job.source_fingerprint:
        raise ValidationError("Sorgente media Carabellese stale")


def _approved_cuts(job: CarabelleseJob, fps: Fraction, total_frames: int) -> list[dict[str, object]]:
    cuts = []
    for decision in job.decisions:
        if decision.get("outcome") == "KEEP":
            continue
        start, end = _floor(float(decision["start_seconds"]), fps), _ceil(float(decision["end_seconds"]), fps)
        if start < 0 or end <= start or end > total_frames:
            raise ValidationError("Taglio approvato fuori dalla timeline")
        cuts.append({"candidate_id": str(decision["candidate_id"]), "start_frame": start,
                     "end_frame_exclusive": end, "outcome": decision["outcome"]})
    cuts.sort(key=lambda item: int(item["start_frame"]), reverse=True)
    ascending = list(reversed(cuts))
    if any(int(current["start_frame"]) < int(previous["end_frame_exclusive"])
           for previous, current in zip(ascending, ascending[1:])):
        raise ValidationError("Tagli approvati sovrapposti")
    return cuts


def _keep_ranges(total_frames: int, cuts: list[dict[str, object]]) -> list[tuple[int, int]]:
    cursor, result = 0, []
    for cut in sorted(cuts, key=lambda item: int(item["start_frame"])):
        start, end = int(cut["start_frame"]), int(cut["end_frame_exclusive"])
        if start > cursor:
            result.append((cursor, start))
        cursor = end
    if cursor < total_frames:
        result.append((cursor, total_frames))
    return result


def verify_carabellese_timeline(project: object, timeline: object,
                                job: CarabelleseJob) -> dict[str, object]:
    current_timeline = _call(project, "GetCurrentTimeline")
    if (timeline_identity(current_timeline) != timeline_identity(timeline)
            or _call(timeline, "GetName") != job.timeline_name):
        raise ValidationError("Timeline finale Carabellese non canonica")
    if int(_call(project, "GetTimelineCount") or 0) != 1:
        raise ValidationError("Il progetto deve contenere una sola timeline finale")
    video = _call(timeline, "GetItemListInTrack", "video", 1) or []
    audio = _call(timeline, "GetItemListInTrack", "audio", 1) or []
    if int(_call(timeline, "GetTrackCount", "video")) != 1 or int(_call(timeline, "GetTrackCount", "audio")) != 1:
        raise ValidationError("Tracce temporanee Carabellese residue")
    if len(video) != len(audio) or not video:
        raise ValidationError("Segmenti A/V finali incoerenti")
    final_frames = sum(int(_call(item, "GetDuration")) for item in video)
    summaries = [op for op in job.operations if op.get("operation") == "apply_summary"
                 and op.get("status") == "VERIFIED"]
    if not summaries or final_frames != int(summaries[-1]["final_frames"]):
        raise ValidationError("Durata timeline finale diversa dal piano approvato")
    if timeline_content_fingerprint(timeline) != summaries[-1]["timeline_fingerprint_after"]:
        raise ValidationError("Fingerprint timeline finale non corrispondente")
    return {"ok": True, "final_frames": final_frames, "segment_count": len(video),
            "transitions_verified": False, "safe_handles_preserved": True}


def apply_or_resume_carabellese_cleanup(resolve: object, manager: object, config: CreativeConfig,
                                        store: CarabelleseJobStore, job_id: str,
                                        expected_review_fingerprint: str) -> CarabelleseJob:
    del resolve
    with RESOLVE_ACCESS_LOCK:
        persisted = store.get(job_id, config.workstation_id)
        if persisted.review_fingerprint != expected_review_fingerprint:
            raise ValidationError("Review fingerprint Carabellese stale")
        effective = replace(persisted, state=persisted.resume_state, resume_state=None) \
            if persisted.state == "BLOCKED" else persisted
        project = _call(manager, "GetCurrentProject")
        timeline = _call(project, "GetCurrentTimeline")
        support = inspect_carabellese_apply_support(None, project, timeline, effective)
        if not support["supported"]:
            raise ValidationError("; ".join(support["reasons"]))
        if effective.state == "VERIFIED":
            verify_carabellese_timeline(project, timeline, effective)
            return effective
        if effective.state not in {"CHECKPOINTED", "FAILED_RECOVERABLE", "APPLYING"}:
            raise ValidationError("Il job non è pronto per l'applicazione")
        video_original, audio_original, media = _timeline_shape(timeline)
        _validate_bound_inputs(config, effective, media)
        fps = _fraction(_call(timeline, "GetSetting", "timelineFrameRate"), "timelineFrameRate")
        total_frames = int(_call(video_original, "GetDuration"))
        cuts = _approved_cuts(effective, fps, total_frames)
        keep = _keep_ranges(total_frames, cuts)
        pool = _call(project, "GetMediaPool")
        current = effective
        if persisted.state == "BLOCKED":
            current = store.save(effective, persisted.revision)
        if current.state == "FAILED_RECOVERABLE":
            current = store.save(replace(current, state="APPLYING", resume_state=None), current.revision)
        elif current.state == "CHECKPOINTED":
            current = store.save(replace(current, state="APPLYING"), current.revision)
        _append_journal(config, {"schema": "ARPHE_CARABELLESE_JOURNAL_V1",
                                "job_id": current.carabellese_job_id, "status": "APPLYING",
                                "revision": current.revision,
                                "timeline_fingerprint": timeline_content_fingerprint(timeline)})
        staged = False
        destructive_started = False
        try:
            if not _call(timeline, "AddTrack", "video") or not _call(timeline, "AddTrack", "audio"):
                raise RuntimeError("add_staging_tracks_failed")
            staged = True
            record = int(_call(timeline, "GetStartFrame") or 0)
            for start, end in keep:
                for media_type in (1, 2):
                    if not _call(pool, "AppendToTimeline", [{"mediaPoolItem": media,
                              "startFrame": start, "endFrame": end, "recordFrame": record,
                              "trackIndex": 2, "mediaType": media_type}]):
                        raise RuntimeError(f"stage_append_failed:{start}:{end}:{media_type}")
                record += end - start
                _append_journal(config, {"schema": "ARPHE_CARABELLESE_JOURNAL_V1",
                                        "job_id": current.carabellese_job_id, "status": "STAGED",
                                        "source_start_frame": start, "source_end_frame_exclusive": end})
            staged_video = _call(timeline, "GetItemListInTrack", "video", 2) or []
            staged_audio = _call(timeline, "GetItemListInTrack", "audio", 2) or []
            expected_duration = sum(end - start for start, end in keep)
            if (len(staged_video) != len(keep) or len(staged_audio) != len(keep)
                    or sum(int(_call(item, "GetDuration")) for item in staged_video) != expected_duration
                    or sum(int(_call(item, "GetDuration")) for item in staged_audio) != expected_duration):
                raise RuntimeError("staging_readback_failed")
            destructive_started = True
            if not _call(timeline, "DeleteClips", [video_original, audio_original], False):
                raise RuntimeError("delete_original_clips_failed")
            if not _call(timeline, "DeleteTrack", "video", 1) or not _call(timeline, "DeleteTrack", "audio", 1):
                raise RuntimeError("delete_original_tracks_failed")
            operations = list(current.operations)
            for cut in cuts:
                operations.append({"operation": "remove", "status": "VERIFIED", **cut})
            after = timeline_content_fingerprint(timeline)
            operations.append({"operation": "apply_summary", "status": "VERIFIED",
                               "final_frames": expected_duration,
                               "timeline_fingerprint_after": after,
                               "transitions_verified": False, "safe_handles_preserved": True})
            current = store.save(replace(current, operations=tuple(operations)), current.revision)
            verified_candidate = replace(current, state="VERIFIED")
            verify_carabellese_timeline(project, timeline, verified_candidate)
            verified = store.save(verified_candidate, current.revision)
            _append_journal(config, {"schema": "ARPHE_CARABELLESE_JOURNAL_V1",
                                    "job_id": current.carabellese_job_id, "status": "VERIFIED",
                                    "timeline_fingerprint": after, "final_frames": expected_duration})
            return verified
        except Exception as exc:
            if staged and not destructive_started:
                if int(_call(timeline, "GetTrackCount", "video")) > 1:
                    _call(timeline, "DeleteTrack", "video", 2)
                if int(_call(timeline, "GetTrackCount", "audio")) > 1:
                    _call(timeline, "DeleteTrack", "audio", 2)
            failed_operation = {"operation": "apply", "status": "FAILED",
                                "reason": f"{type(exc).__name__}:{exc}",
                                "timeline_fingerprint_at_failure": timeline_content_fingerprint(timeline)}
            failed = store.save(replace(current, state="FAILED_RECOVERABLE", resume_state="APPLYING",
                                      operations=current.operations + (failed_operation,)), current.revision)
            _append_journal(config, {"schema": "ARPHE_CARABELLESE_JOURNAL_V1",
                                    "job_id": current.carabellese_job_id, "status": "FAILED",
                                    "revision": failed.revision,
                                    "timeline_fingerprint": failed_operation["timeline_fingerprint_at_failure"]})
            return failed
