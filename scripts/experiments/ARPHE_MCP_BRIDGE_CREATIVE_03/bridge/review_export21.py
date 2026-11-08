"""Resolve 21.2 in-memory review-frame exports."""
from __future__ import annotations

import base64
import math
from typing import Any

from mcp.server.mcpserver import Image

from .diagnostic_tools import MAX_FRAME_BATCH, frame_to_timecode
from .resolve_connection import safe_call
from .safety import ValidationError, require_arphe_name


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError(f"{name} deve essere compreso tra {minimum} e {maximum}")
    return value


def validate_review_target(project: Any, timeline: Any, config: Any, registry: Any) -> None:
    project_name = str(safe_call(project, "GetName") or "")
    timeline_name = str(safe_call(timeline, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    require_arphe_name(timeline_name, "timeline")
    configured = (project_name in config.allowed_projects
                  and timeline_name in config.allowed_timelines)
    if not (configured or registry.timeline_allowed(project_name, timeline_name)):
        raise ValidationError("Anteprima consentita solo su timeline creata o allowlisted dal bridge")


def _offsets(timeline: Any, values: list[int]) -> tuple[int, int, list[int]]:
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_FRAME_BATCH:
        raise ValidationError(f"frame_offsets deve contenere da 1 a {MAX_FRAME_BATCH} frame")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValidationError("Ogni frame offset deve essere un intero")
    offsets = list(dict.fromkeys(values))
    start = safe_call(timeline, "GetStartFrame")
    end = safe_call(timeline, "GetEndFrame")
    try:
        fps = int(round(float(safe_call(timeline, "GetSetting", "timelineFrameRate"))))
    except (TypeError, ValueError):
        raise ValidationError("FPS timeline non leggibile") from None
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValidationError("Range timeline non leggibile")
    if any(value < 0 or value >= end - start for value in offsets):
        raise ValidationError(f"Frame offset fuori range: consentito 0-{end - start - 1}")
    return start, fps, offsets


def _roi(value: dict[str, float] | None) -> dict[str, float]:
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) != {"x", "y", "width", "height"}:
        raise ValidationError("ROI deve contenere x, y, width e height")
    try:
        x, y, width, height = (float(value[key]) for key in ("x", "y", "width", "height"))
    except (TypeError, ValueError):
        raise ValidationError("ROI non numerica") from None
    if (not all(math.isfinite(item) for item in (x, y, width, height))
            or x < 0 or y < 0 or width <= 0 or height <= 0
            or x + width > 1 or y + height > 1):
        raise ValidationError("ROI fuori dal frame normalizzato")
    return {"roiX": x, "roiY": y, "roiWidth": width, "roiHeight": height}


def _image(result: object) -> tuple[Image, dict[str, Any]]:
    if not isinstance(result, dict) or result.get("success") is not True:
        error = result.get("error") if isinstance(result, dict) else None
        raise RuntimeError(f"Export frame Resolve 21.2 fallito{': ' + str(error) if error else ''}")
    encoded = result.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError("Resolve non ha restituito i dati immagine")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError("Dati immagine Resolve non validi") from exc
    public = {key: result[key] for key in ("width", "height", "columns", "rows")
              if isinstance(result.get(key), int)}
    return Image(data=data, format="jpeg"), public


def export_review_frames21(
    timeline: Any,
    frame_offsets: list[int],
    mode: str = "frames",
    roi: dict[str, float] | None = None,
    max_dimension: int = 1600,
    quality: int = 90,
) -> list[Any]:
    """Return native in-memory JPEG reviews without moving the playhead."""
    if mode not in {"frames", "grid"}:
        raise ValidationError("mode deve essere frames o grid")
    start, fps, offsets = _offsets(timeline, frame_offsets)
    dimension = _integer(max_dimension, "max_dimension", 320, 4096)
    jpeg_quality = _integer(quality, "quality", 40, 100)
    crop = _roi(roi)
    if mode == "grid" and crop:
        raise ValidationError("La ROI è consentita solo in modalità frames")
    method_name = "ExportFrame" if mode == "frames" else "ExportThumbnails"
    if not callable(getattr(timeline, method_name, None)):
        raise ValidationError(f"Resolve non espone {method_name}; serve Resolve 21.2")
    options = {
        "outputType": "encodedString", "encodedImageFormat": "jpg",
        "maxDimension": dimension, "quality": jpeg_quality, **crop,
    }
    images: list[Image] = []
    details: list[dict[str, Any]] = []
    if mode == "frames":
        for offset in offsets:
            image, public = _image(safe_call(timeline, "ExportFrame", offset, options))
            images.append(image)
            details.append({"frame_offset": offset,
                            "timecode": frame_to_timecode(start + offset, fps), **public})
    else:
        frames = [{"frameOffset": offset, "label": frame_to_timecode(start + offset, fps)}
                  for offset in offsets]
        image, public = _image(safe_call(timeline, "ExportThumbnails", frames, options))
        images.append(image)
        details.append(public)
    return [{
        "ok": True,
        "action": "export_review_frames21",
        "mode": mode,
        "capture_count": len(offsets),
        "captures": details,
        "playhead_moved": False,
        "files_created": False,
    }, *images]
