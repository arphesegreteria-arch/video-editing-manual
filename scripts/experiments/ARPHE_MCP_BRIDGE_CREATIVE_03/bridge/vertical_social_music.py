from __future__ import annotations

from typing import Any

from .resolve_connection import safe_call
from .safety import ValidationError


def validate_music_duck(action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    if action.get("type") != "MUSIC_DUCK" or action.get("state") != "APPROVED":
        raise ValidationError("MUSIC_DUCK non approvato")
    raw = action.get("range")
    if not isinstance(raw, dict):
        raise ValidationError("range MUSIC_DUCK mancante")
    start, end = raw.get("start_frame"), raw.get("end_frame")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= total_frames:
        raise ValidationError("range MUSIC_DUCK non valido")
    track = action.get("audio_track")
    gain = action.get("gain_db")
    if not isinstance(track, int) or isinstance(track, bool) or track < 1:
        raise ValidationError("audio_track MUSIC_DUCK non valido")
    if not isinstance(gain, (int, float)) or isinstance(gain, bool) or not -30.0 <= float(gain) <= 0.0:
        raise ValidationError("gain_db MUSIC_DUCK fuori limite")
    if not str(action.get("reason", "")).strip():
        raise ValidationError("reason MUSIC_DUCK mancante")
    return {"range": (start, end), "audio_track": track, "gain_db": float(gain)}


def apply_music_duck(timeline: object, action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    plan = validate_music_duck(action, total_frames)
    start, end = plan["range"]
    items = safe_call(timeline, "GetItemListInTrack", "audio", plan["audio_track"]) or []
    matches = [item for item in items
               if safe_call(item, "GetStart") == start
               and safe_call(item, "GetEnd") == end]
    if len(matches) != 1:
        raise ValidationError("MUSIC_DUCK deve coincidere con i confini di una clip musicale")
    item = matches[0]
    if not safe_call(item, "SetProperty", "AudioVolume", plan["gain_db"]):
        raise ValidationError("Applicazione AudioVolume MUSIC_DUCK fallita")
    readback = safe_call(item, "GetProperty", "AudioVolume")
    try:
        verified = abs(float(readback) - plan["gain_db"]) < 0.001
    except (TypeError, ValueError):
        verified = False
    if not verified:
        raise ValidationError("Read-back AudioVolume MUSIC_DUCK non corrispondente")
    return {"ok": True, "action_id": str(action.get("action_id", "")),
            "audio_track": plan["audio_track"], "range": [start, end],
            "gain_db": plan["gain_db"]}
