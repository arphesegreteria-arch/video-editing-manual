from __future__ import annotations

from typing import Any

from .resolve_connection import safe_call
from .safety import ValidationError
from .timeline_tools import duplicate_timeline


_CROSS_FADE_0DB = {
    "type": "Cross Fade 0 dB",
    "category": "audio",
    "position": "start",
    "alignment": "center",
}


def apply_audio_seam_transitions(timeline: Any, cut_frames: list[int], duration_frames: int) -> dict[str, Any]:
    """Add native audio cross-fades only at verified A1 cut boundaries."""
    if not isinstance(duration_frames, int) or not 1 <= duration_frames <= 60:
        raise ValidationError("La durata della transizione deve essere compresa tra 1 e 60 frame")
    if not cut_frames or any(not isinstance(frame, int) for frame in cut_frames):
        raise ValidationError("Servono frame di taglio audio espliciti")

    audio_items = sorted(
        safe_call(timeline, "GetItemListInTrack", "audio", 1) or [],
        key=lambda item: int(safe_call(item, "GetStart") or 0),
    )
    transitions: list[tuple[int, Any]] = []
    for frame in cut_frames:
        outgoing = next((item for item in audio_items if int(safe_call(item, "GetEnd") or -1) == frame), None)
        incoming = next((item for item in audio_items if int(safe_call(item, "GetStart") or -1) == frame), None)
        if not outgoing or not incoming:
            raise ValidationError(f"Nessun taglio A1 al frame {frame}")
        if int(safe_call(outgoing, "GetEnd") or -1) != int(safe_call(incoming, "GetStart") or -2):
            raise ValidationError(f"I clip audio al frame {frame} non sono contigui")
        if not callable(getattr(incoming, "AddTransition", None)):
            raise RuntimeError("Resolve non espone AddTransition sulla clip audio")
        transitions.append((frame, incoming))

    options = {**_CROSS_FADE_0DB, "duration": duration_frames}
    applied: list[int] = []
    for frame, incoming in transitions:
        created = safe_call(incoming, "AddTransition", options)
        if not created:
            raise RuntimeError(f"Resolve ha rifiutato la transizione audio al frame {frame}")
        if safe_call(created, "GetType") != "transition":
            raise RuntimeError(f"Il read-back della transizione audio al frame {frame} non e' verificabile")
        applied.append(frame)
    return {"cut_frames": applied, "duration_frames": duration_frames, "transition": "Cross Fade 0 dB"}


def create_audio_seam_test(project: Any, config: Any, registry: Any, source_timeline: str,
                           target_name: str, cut_frames: list[int], duration_frames: int = 2) -> dict[str, Any]:
    """Duplicate a timeline and add verified native audio transitions to the duplicate only."""
    original_timeline = safe_call(project, "GetCurrentTimeline")
    duplicated = duplicate_timeline(project, config, registry, source_timeline, None, target_name)
    if not duplicated.get("ok"):
        return {**duplicated, "action": "create_audio_seam_test"}
    timeline = safe_call(project, "GetCurrentTimeline")
    try:
        result = apply_audio_seam_transitions(timeline, cut_frames, duration_frames)
    except Exception as error:
        restored = bool(original_timeline and safe_call(project, "SetCurrentTimeline", original_timeline))
        media_pool = safe_call(project, "GetMediaPool")
        removed = bool(media_pool and safe_call(media_pool, "DeleteTimelines", [timeline]))
        if not restored or not removed:
            raise RuntimeError(
                "La prova audio non e' riuscita e Resolve non ha confermato il ripristino sicuro"
            ) from error
        raise
    return {
        "ok": True,
        "action": "create_audio_seam_test",
        "source_timeline": source_timeline,
        "created_timeline": safe_call(timeline, "GetName"),
        "source_preserved": True,
        "saved": False,
        **result,
    }
