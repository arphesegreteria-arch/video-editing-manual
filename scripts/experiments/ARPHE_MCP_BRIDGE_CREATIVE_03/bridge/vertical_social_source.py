from __future__ import annotations

from fractions import Fraction
from typing import Any

from .config import CreativeConfig
from .format_contract import SUPPORTED_RATES, ResolvedFormat, _rate_label, apply_project_format, verify_timeline_format
from .longform_tools import allowed_media, import_media_item
from .project_tools import create_project
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name, ensure_no_collision


def _nominal_rate(value: object) -> Fraction:
    try:
        actual = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise ValidationError("Frame rate sorgente verticale non leggibile") from None
    selected = min(SUPPORTED_RATES, key=lambda rate: abs(float(rate) - actual))
    if abs(float(selected) - actual) > 0.1:
        raise ValidationError("Frame rate sorgente verticale non supportato")
    return selected


def _same_media(left: object, right: object) -> bool:
    if left is right:
        return True
    left_id = safe_call(left, "GetUniqueId")
    right_id = safe_call(right, "GetUniqueId")
    return bool(left_id and left_id == right_id)


def create_vertical_social_source(resolve: Any, manager: Any, config: CreativeConfig,
                                  registry: Registry, media_path: str,
                                  project_name: str, timeline_name: str) -> dict[str, Any]:
    media = allowed_media(media_path, config)
    requested_project = arphe_name(project_name, "VERTICAL_SOCIAL")
    requested_timeline = arphe_name(timeline_name, "VERTICAL_SOCIAL_SOURCE")
    ensure_no_collision(requested_project,
                        [str(value) for value in (safe_call(manager, "GetProjectListInCurrentFolder") or [])],
                        "Progetto")
    created = create_project(manager, config, registry, requested_project)
    if not created.get("ok"):
        raise ValidationError("Creazione progetto sorgente Vertical Social fallita")
    project = safe_call(manager, "GetCurrentProject")
    if project is None or safe_call(project, "GetName") != requested_project:
        raise ValidationError("Progetto sorgente Vertical Social non selezionato")
    pool = safe_call(project, "GetMediaPool")
    media_item = import_media_item(resolve, pool, media) if pool else None
    if media_item is None:
        raise ValidationError("Import sorgente Vertical Social fallito")
    rate = _nominal_rate(safe_call(media_item, "GetClipProperty", "FPS"))
    frames = int(float(safe_call(media_item, "GetClipProperty", "Frames") or 0))
    if frames <= 0:
        raise ValidationError("Durata sorgente Vertical Social non valida")
    contract = ResolvedFormat(1080, 1920, rate, rate)
    applied = apply_project_format(project, contract)
    timeline = safe_call(pool, "CreateEmptyTimeline", requested_timeline)
    if timeline is None or safe_call(timeline, "GetName") != requested_timeline:
        raise ValidationError("Creazione timeline sorgente Vertical Social fallita")
    if not safe_call(project, "SetCurrentTimeline", timeline):
        raise ValidationError("Selezione timeline sorgente Vertical Social fallita")
    verify_timeline_format(project, timeline, contract)
    timeline_start = int(safe_call(timeline, "GetStartFrame") or 0)
    record = timeline_start
    for media_type in (1, 2):
        appended = safe_call(pool, "AppendToTimeline", [{
            "mediaPoolItem": media_item,
            "startFrame": 0,
            "endFrame": frames,
            "recordFrame": record,
            "mediaType": media_type,
            "trackIndex": 1,
        }])
        if not appended:
            raise ValidationError("Inserimento sorgente A/V Vertical Social fallito")
    video = safe_call(timeline, "GetItemListInTrack", "video", 1) or []
    audio = safe_call(timeline, "GetItemListInTrack", "audio", 1) or []
    linked = (len(video) == len(audio) == 1
              and safe_call(video[0], "GetStart") == safe_call(audio[0], "GetStart") == record
              and safe_call(video[0], "GetDuration") == safe_call(audio[0], "GetDuration") == frames
              and _same_media(safe_call(video[0], "GetMediaPoolItem"),
                              safe_call(audio[0], "GetMediaPoolItem")))
    if not linked:
        raise ValidationError("Read-back sorgente A/V Vertical Social non conforme")
    registry.add_timeline(requested_project, requested_timeline)
    return {
        "ok": True,
        "action": "create_vertical_social_source",
        "project": requested_project,
        "timeline": requested_timeline,
        "resolution": {"width": 1080, "height": 1920},
        "source_rate": str(safe_call(media_item, "GetClipProperty", "FPS") or ""),
        "timeline_rate": _rate_label(rate),
        "duration_frames": frames,
        "linked_av": True,
        "source_preserved": True,
        "overwrite": False,
        "settings": applied,
    }


def create_vertical_social_sequence(resolve: Any, manager: Any, config: CreativeConfig,
                                    registry: Registry, media_paths: list[str],
                                    project_name: str, timeline_name: str,
                                    trim_ranges: list[tuple[int, int]] | None = None) -> dict[str, Any]:
    """Create one linked vertical A/V sequence from 2-20 ordered sources."""
    if not isinstance(media_paths, list) or not 2 <= len(media_paths) <= 20:
        raise ValidationError("La sequenza verticale richiede da 2 a 20 sorgenti")
    if any(not isinstance(value, str) or not value for value in media_paths):
        raise ValidationError("Percorso sorgente verticale non valido")
    media_files = [allowed_media(value, config) for value in media_paths]
    if len({str(value.resolve()).casefold() for value in media_files}) != len(media_files):
        raise ValidationError("Sorgente verticale duplicata")
    requested_project = arphe_name(project_name, "VERTICAL_SOCIAL")
    requested_timeline = arphe_name(timeline_name, "VERTICAL_SOCIAL_SOURCE")
    ensure_no_collision(requested_project,
                        [str(value) for value in (safe_call(manager, "GetProjectListInCurrentFolder") or [])],
                        "Progetto")
    created = create_project(manager, config, registry, requested_project)
    if not created.get("ok"):
        raise ValidationError("Creazione progetto sorgente Vertical Social fallita")
    project = safe_call(manager, "GetCurrentProject")
    if project is None or safe_call(project, "GetName") != requested_project:
        raise ValidationError("Progetto sorgente Vertical Social non selezionato")
    pool = safe_call(project, "GetMediaPool")
    media_items = [import_media_item(resolve, pool, path) for path in media_files] if pool else []
    if len(media_items) != len(media_files) or any(item is None for item in media_items):
        raise ValidationError("Import sequenza sorgente Vertical Social fallito")
    rates = [_nominal_rate(safe_call(item, "GetClipProperty", "FPS")) for item in media_items]
    if any(rate != rates[0] for rate in rates[1:]):
        raise ValidationError("Le sorgenti Vertical Social hanno frame rate differenti")
    frames = [int(float(safe_call(item, "GetClipProperty", "Frames") or 0)) for item in media_items]
    if any(value <= 0 for value in frames):
        raise ValidationError("Durata sorgente Vertical Social non valida")
    selected_ranges = trim_ranges or [(0, value) for value in frames]
    if len(selected_ranges) != len(frames):
        raise ValidationError("Serve un intervallo di trim per ogni sorgente verticale")
    for (start, end), frame_count in zip(selected_ranges, frames):
        if (not isinstance(start, int) or not isinstance(end, int)
                or start < 0 or end <= start or end > frame_count):
            raise ValidationError("Intervallo di trim Vertical Social non valido")
    contract = ResolvedFormat(1080, 1920, rates[0], rates[0])
    applied = apply_project_format(project, contract)
    timeline = safe_call(pool, "CreateEmptyTimeline", requested_timeline)
    if timeline is None or safe_call(timeline, "GetName") != requested_timeline:
        raise ValidationError("Creazione timeline sorgente Vertical Social fallita")
    if not safe_call(project, "SetCurrentTimeline", timeline):
        raise ValidationError("Selezione timeline sorgente Vertical Social fallita")
    verify_timeline_format(project, timeline, contract)
    timeline_start = int(safe_call(timeline, "GetStartFrame") or 0)
    record = timeline_start
    sources: list[dict[str, Any]] = []
    for index, (media_item, source_range) in enumerate(zip(media_items, selected_ranges), start=1):
        source_start, source_end = source_range
        frame_count = source_end - source_start
        for media_type in (1, 2):
            appended = safe_call(pool, "AppendToTimeline", [{
                "mediaPoolItem": media_item, "startFrame": source_start, "endFrame": source_end,
                "recordFrame": record, "mediaType": media_type, "trackIndex": 1,
            }])
            if not appended:
                raise ValidationError("Inserimento sequenza A/V Vertical Social fallito")
        sources.append({"index": index, "source_start": source_start, "source_end": source_end,
                        "record_start": record,
                        "record_end": record + frame_count, "duration_frames": frame_count})
        record += frame_count
    video = safe_call(timeline, "GetItemListInTrack", "video", 1) or []
    audio = safe_call(timeline, "GetItemListInTrack", "audio", 1) or []
    linked = len(video) == len(audio) == len(media_items)
    for video_clip, audio_clip, media_item, source in zip(video, audio, media_items, sources):
        linked = linked and (
            safe_call(video_clip, "GetStart") == safe_call(audio_clip, "GetStart") == source["record_start"]
            and safe_call(video_clip, "GetDuration") == safe_call(audio_clip, "GetDuration") == source["duration_frames"]
            and _same_media(safe_call(video_clip, "GetMediaPoolItem"), media_item)
            and _same_media(safe_call(audio_clip, "GetMediaPoolItem"), media_item))
    if not linked:
        raise ValidationError("Read-back sequenza A/V Vertical Social non conforme")
    registry.add_timeline(requested_project, requested_timeline)
    return {
        "ok": True, "action": "create_vertical_social_sequence",
        "project": requested_project, "timeline": requested_timeline,
        "resolution": {"width": 1080, "height": 1920},
        "timeline_rate": _rate_label(rates[0]), "duration_frames": record - timeline_start,
        "source_count": len(media_items), "sources": sources,
        "linked_av": True, "source_preserved": True, "overwrite": False,
        "settings": applied,
    }
