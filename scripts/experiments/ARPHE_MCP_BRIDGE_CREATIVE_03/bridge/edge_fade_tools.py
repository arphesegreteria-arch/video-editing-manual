from __future__ import annotations

from pathlib import Path
import wave
from typing import Any

import numpy as np

from .config import CreativeConfig
from .feature_flags import require_capability
from .fusion_tools import _media_out, _new_tool, _set, connect_input
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, arphe_name
from .timeline_tools import duplicate_timeline


def apply_audio_edge_fades(samples: np.ndarray, fade_in: int, fade_out: int) -> np.ndarray:
    """Return a copy with linear edge fades; samples are frames x channels."""
    result = samples.astype(np.float32, copy=True)
    if fade_in:
        result[:fade_in] *= np.linspace(0.0, 1.0, fade_in, endpoint=True)[:, None]
    if fade_out:
        result[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, endpoint=True)[:, None]
    return result


def _render_audio_excerpt(source: Path, output: Path, start_seconds: float, duration_seconds: float,
                          fade_in_seconds: float, fade_out_seconds: float) -> None:
    with wave.open(str(source), "rb") as handle:
        channels, width, rate = handle.getnchannels(), handle.getsampwidth(), handle.getframerate()
        if width != 2:
            raise ValidationError("Il preset edge fade supporta WAV PCM 16 bit")
        first = max(0, round(start_seconds * rate))
        count = max(1, round(duration_seconds * rate))
        handle.setpos(first)
        raw = handle.readframes(count)
    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
    fade_in = min(len(samples), round(fade_in_seconds * rate))
    fade_out = min(len(samples), round(fade_out_seconds * rate))
    faded = apply_audio_edge_fades(samples, fade_in, fade_out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(np.clip(faded, -32768, 32767).astype("<i2").tobytes())


def _add_video_fade(item: Any, fade_in: int, fade_out: int) -> dict[str, Any]:
    duration = int(safe_call(item, "GetDuration") or 0)
    if duration <= fade_in + fade_out:
        raise ValidationError("Clip troppo corta per i fade richiesti")
    comp = safe_call(item, "AddFusionComp")
    if not comp:
        raise RuntimeError("Impossibile aggiungere la composizione Fusion alla clip video")
    tools = list((safe_call(comp, "GetToolList", False) or {}).values())
    media_in = next((tool for tool in tools if (safe_call(tool, "GetAttrs") or {}).get("TOOLS_RegID") == "MediaIn"), None)
    media_out = _media_out(comp)
    if not media_in or not media_out:
        raise RuntimeError("MediaIn/MediaOut non trovati nella clip Fusion")
    background = _new_tool(comp, "Background", "ARPHE_EDGE_BLACK")
    for name in ("TopLeftRed", "TopLeftGreen", "TopLeftBlue"):
        _set(background, name, 0.0)
    _set(background, "TopLeftAlpha", 1.0)
    merge = _new_tool(comp, "Merge", "ARPHE_EDGE_FADE")
    if not connect_input(merge, "Background", background):
        raise RuntimeError("Collegamento sfondo edge fade fallito")
    if not connect_input(merge, "Foreground", media_in):
        raise RuntimeError("Collegamento video edge fade fallito")
    if not connect_input(media_out, "Input", merge):
        raise RuntimeError("Collegamento MediaOut edge fade fallito")
    attrs = safe_call(comp, "GetAttrs") or {}
    # Clip Fusion compositions render in their local RenderStart/RenderEnd
    # domain. GlobalStart may include the source-media offset and is not the
    # time used when Resolve evaluates this clip on the timeline.
    first = int(attrs.get("COMPN_RenderStart", 0))
    last = int(attrs.get("COMPN_RenderEnd", first + duration - 1))
    try:
        merge.Blend = comp.BezierSpline()
        merge.Blend[first] = 0.0
        merge.Blend[first + fade_in] = 1.0
        merge.Blend[last - fade_out] = 1.0
        merge.Blend[last] = 0.0
    except Exception as exc:
        raise RuntimeError("Keyframe video edge fade falliti") from exc
    return {"duration_frames": duration, "fusion_start": first, "fusion_end": last}


def create_edge_fade_test(project: Any, config: CreativeConfig, registry: Registry,
                          source_timeline: str, target_name: str,
                          video_in_frames: int = 6, video_out_frames: int = 8,
                          audio_in_frames: int = 4, audio_out_frames: int = 10) -> dict[str, Any]:
    current = safe_call(project, "GetCurrentTimeline")
    require_capability("CAP_TIMELINE", config, None, project, current)
    values = (video_in_frames, video_out_frames, audio_in_frames, audio_out_frames)
    if any(not isinstance(value, int) or value < 1 or value > 60 for value in values):
        raise ValidationError("I fade devono essere compresi tra 1 e 60 frame")
    duplicated = duplicate_timeline(project, config, registry, source_timeline, None, target_name)
    if not duplicated.get("ok"):
        return {**duplicated, "action": "create_edge_fade_test"}
    timeline = safe_call(project, "GetCurrentTimeline")
    video_items = safe_call(timeline, "GetItemListInTrack", "video", 1) or []
    audio_items = safe_call(timeline, "GetItemListInTrack", "audio", 1) or []
    if len(video_items) != 1 or len(audio_items) != 1:
        raise ValidationError("Il primo test richiede esattamente una clip su V1 e una su A1")
    fps = float(safe_call(timeline, "GetSetting", "timelineFrameRate") or 0)
    if fps <= 0:
        raise RuntimeError("Frame rate timeline non disponibile")
    video_result = _add_video_fade(video_items[0], video_in_frames, video_out_frames)

    audio_item = audio_items[0]
    media_item = safe_call(audio_item, "GetMediaPoolItem")
    source_path = Path(str(safe_call(media_item, "GetClipProperty", "File Path") or ""))
    if not source_path.is_file() or source_path.suffix.lower() != ".wav":
        raise ValidationError("La clip audio deve provenire da un WAV locale")
    source_start = float(safe_call(audio_item, "GetSourceStartFrame") or 0) / fps
    duration_frames = int(safe_call(audio_item, "GetDuration") or 0)
    output = config.audio_root / f"{arphe_name(target_name, 'EDGE_FADE')}_AUDIO.wav"
    _render_audio_excerpt(source_path, output, source_start, duration_frames / fps,
                          audio_in_frames / fps, audio_out_frames / fps)
    pool = safe_call(project, "GetMediaPool")
    imported = safe_call(pool, "ImportMedia", [str(output)]) or []
    if not imported:
        raise RuntimeError("Import del WAV edge fade fallito")
    record_frame = int(safe_call(audio_item, "GetStart") or 0)
    if not safe_call(timeline, "DeleteClips", [audio_item], False):
        raise RuntimeError("Sostituzione audio edge fade fallita")
    appended = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": imported[0], "mediaType": 2,
                                                       "trackIndex": 1, "recordFrame": record_frame}])
    if not appended:
        raise RuntimeError("Inserimento WAV edge fade fallito")
    return {"ok": True, "action": "create_edge_fade_test", "source_timeline": source_timeline,
            "created_timeline": safe_call(timeline, "GetName"), "video_fade": video_result,
            "video_in_frames": video_in_frames, "video_out_frames": video_out_frames,
            "audio_in_frames": audio_in_frames, "audio_out_frames": audio_out_frames,
            "audio_path": str(output), "saved": False, "source_preserved": True}
