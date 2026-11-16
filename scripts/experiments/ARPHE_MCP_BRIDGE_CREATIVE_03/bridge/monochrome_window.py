from __future__ import annotations

from typing import Any

from .fusion_tools import _media_out, _new_tool, connect_input
from .resolve_connection import safe_call


def validate_monochrome_window(clip_start: int, clip_end: int,
                               window_start: int, window_end: int) -> dict[str, int]:
    """Validate an exclusive timeline-frame window and map it to clip-local frames."""
    if any(isinstance(value, bool) or not isinstance(value, int)
           for value in (clip_start, clip_end, window_start, window_end)):
        raise ValueError("I frame devono essere interi")
    if clip_end <= clip_start:
        raise ValueError("Range clip non valido")
    if window_end <= window_start:
        raise ValueError("Finestra monocromatica non valida")
    if window_start < clip_start or window_end > clip_end:
        raise ValueError("Finestra monocromatica fuori dalla clip")
    return {
        "local_start": window_start - clip_start,
        "local_end": window_end - clip_start,
        "duration": window_end - window_start,
    }


def saturation_keyframes(local_start: int, local_end: int) -> dict[int, float]:
    """Return hard-cut saturation keys for an exclusive clip-local window."""
    if local_start < 0 or local_end <= local_start:
        raise ValueError("Finestra locale monocromatica non valida")
    keys: dict[int, float] = {}
    if local_start:
        keys[local_start - 1] = 1.0
    keys[local_start] = 0.0
    keys[local_end - 1] = 0.0
    keys[local_end] = 1.0
    return keys


def prepare_monochrome_window(clip_start: int, clip_end: int,
                              window_start: int, window_end: int) -> dict[str, object]:
    """Build the validated local animation plan before touching a Fusion graph."""
    local = validate_monochrome_window(clip_start, clip_end, window_start, window_end)
    return {**local, "saturation_keys": saturation_keyframes(local["local_start"], local["local_end"])}


def _media_in(comp: Any) -> Any:
    tools = safe_call(comp, "GetToolList", False) or {}
    return next((tool for tool in tools.values()
                 if (safe_call(tool, "GetAttrs") or {}).get("TOOLS_RegID") == "MediaIn"), None)


def apply_monochrome_window(item: Any, window_start: int, window_end: int) -> dict[str, int]:
    """Attach a Fusion ColorCorrector and hard-key its saturation for one time window."""
    clip_start = safe_call(item, "GetStart")
    clip_end = safe_call(item, "GetEnd")
    plan = prepare_monochrome_window(clip_start, clip_end, window_start, window_end)
    comp = safe_call(item, "AddFusionComp") or safe_call(item, "GetFusionCompByIndex", 1)
    if comp is None:
        raise RuntimeError("Composizione Fusion della clip non disponibile")
    source = _media_in(comp)
    output = _media_out(comp)
    if source is None or output is None:
        raise RuntimeError("MediaIn/MediaOut non trovati nella clip Fusion")
    corrector = _new_tool(comp, "ColorCorrector", "ARPHE_MONOCHROME_WINDOW")
    if not connect_input(corrector, "Input", source) or not connect_input(output, "Input", corrector):
        raise RuntimeError("Collegamento Fusion monocromatico fallito")
    try:
        # Resolve's numeric inputs own their animation.  Writing keys directly
        # to the Saturation input avoids a detached modifier being ignored.
        curve = corrector.Saturation
        if curve is None:
            raise RuntimeError("Binding saturazione monocromatica fallito")
        for frame, value in plan["saturation_keys"].items():
            curve[frame] = value
    except Exception as exc:
        raise RuntimeError(f"Keyframe saturazione monocromatica falliti: {exc}") from exc
    return {"window_start": window_start, "window_end": window_end, "duration": plan["duration"]}
