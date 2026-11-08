from __future__ import annotations

import base64
import binascii
from pathlib import Path
import re
import time
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import Image

from .artifact_records import artifact_store_for
from .config import CreativeConfig
from .fusion_tools import find_composition
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, require_arphe_name


MAX_FRAME_BATCH = 8
SAFE_INPUTS = (
    "Size", "Center", "LayoutType", "LayoutWidth", "LayoutHeight",
    "Width", "Height", "CornerRadius", "Blend", "Font", "Style",
    "Red1", "Green1", "Blue1", "Alpha1",
)


def _number(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _number(item) for key, item in value.items()
                if isinstance(item, (bool, int, float, str)) or item is None}
    return None


def _attrs(tool: Any) -> dict[str, Any]:
    attrs = safe_call(tool, "GetAttrs") or {}
    return attrs if isinstance(attrs, dict) else {}


def inspect_fusion_graph(timeline: Any, registry: Registry, composition_id: str) -> dict[str, Any]:
    item, comp = find_composition(timeline, registry, composition_id)
    tools = safe_call(comp, "GetToolList", False) or {}
    values = tools.values() if isinstance(tools, dict) else tools
    nodes = []
    for tool in values:
        attrs = _attrs(tool)
        node = {
            "name": attrs.get("TOOLS_Name"),
            "type": attrs.get("TOOLS_RegID") or attrs.get("TOOLST_RegID"),
            "inputs": {},
        }
        for input_name in SAFE_INPUTS:
            value = _number(safe_call(tool, "GetInput", input_name))
            if value is not None:
                node["inputs"][input_name] = value
        styled_text = safe_call(tool, "GetInput", "StyledText")
        if isinstance(styled_text, str):
            node["text_length"] = len(styled_text)
        nodes.append(node)
    return {
        "ok": True,
        "action": "inspect_fusion_graph",
        "composition_id": composition_id,
        "timeline_item": safe_call(item, "GetName"),
        "node_count": len(nodes),
        "nodes": nodes,
        "text_content_disclosed": False,
    }


def _fps(timeline: Any) -> int:
    try:
        value = int(round(float(safe_call(timeline, "GetSetting", "timelineFrameRate"))))
    except (TypeError, ValueError):
        raise ValidationError("FPS timeline non leggibile")
    if value not in (24, 25, 30):
        raise ValidationError("Cattura diagnostica supportata solo a 24/25/30 fps non-drop")
    return value


def frame_to_timecode(absolute_frame: int, fps: int) -> str:
    if isinstance(absolute_frame, bool) or not isinstance(absolute_frame, int) or absolute_frame < 0:
        raise ValidationError("Frame assoluto non valido")
    hours, remainder = divmod(absolute_frame, fps * 3600)
    minutes, remainder = divmod(remainder, fps * 60)
    seconds, frames = divmod(remainder, fps)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def _validate_offsets(timeline: Any, frame_offsets: list[int]) -> tuple[int, int, list[int]]:
    if not isinstance(frame_offsets, list) or not 1 <= len(frame_offsets) <= MAX_FRAME_BATCH:
        raise ValidationError(f"frame_offsets deve contenere da 1 a {MAX_FRAME_BATCH} frame")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in frame_offsets):
        raise ValidationError("Ogni frame offset deve essere un intero")
    offsets = list(dict.fromkeys(frame_offsets))
    start = safe_call(timeline, "GetStartFrame")
    end = safe_call(timeline, "GetEndFrame")
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValidationError("Range timeline non leggibile")
    duration = end - start
    if any(value < 0 or value >= duration for value in offsets):
        raise ValidationError(f"Frame offset fuori range: consentito 0-{duration - 1}")
    return start, _fps(timeline), offsets


def _diagnostic_root(config: CreativeConfig) -> Path:
    root = (config.render_root / "diagnostics").resolve()
    render_root = config.render_root.resolve()
    if root.parent != render_root:
        raise RuntimeError("Cartella diagnostica non valida")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _timeline_export_frame(timeline: Any, frame_offset: int, path: Path) -> bool | None:
    """Use the Resolve 21.1.2+ frame API when exposed by the live proxy.

    ``None`` means the API is not available and the caller may use the legacy
    playhead-based path. Once the method is exposed, a rejected or malformed
    response fails closed instead of silently switching capture semantics.
    """
    export_frame = getattr(timeline, "ExportFrame", None)
    if not callable(export_frame):
        return None
    try:
        result = export_frame(frame_offset, {
            "outputType": "encodedString",
            "encodedImageFormat": "jpg",
            "quality": 100,
        })
    except Exception as exc:
        raise RuntimeError(f"ExportFrame 21.2 fallita al frame {frame_offset}: {exc}") from exc
    if not isinstance(result, dict) or result.get("success") is not True:
        error = result.get("error") if isinstance(result, dict) else None
        detail = f": {error}" if isinstance(error, str) and error else ""
        raise RuntimeError(f"ExportFrame 21.2 rifiutata al frame {frame_offset}{detail}")
    encoded = result.get("data")
    if not isinstance(encoded, str) or not encoded:
        raise RuntimeError(f"ExportFrame 21.2 non ha restituito il frame {frame_offset}")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise RuntimeError(f"ExportFrame 21.2 ha restituito dati non validi al frame {frame_offset}") from exc
    if not payload.startswith(b"\xff\xd8\xff"):
        raise RuntimeError(f"ExportFrame 21.2 non ha restituito un JPEG al frame {frame_offset}")
    path.write_bytes(payload)
    return True


def _supports_timeline_export_frame(resolve: Any, timeline: Any) -> bool:
    version = safe_call(resolve, "GetVersionString") or safe_call(resolve, "GetVersion")
    numbers = [int(value) for value in re.findall(r"\d+", str(version))[:3]]
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers) >= (21, 1, 2) and callable(getattr(timeline, "ExportFrame", None))


def capture_timeline_frames(resolve: Any, project: Any, timeline: Any, config: CreativeConfig,
                            registry: Registry, frame_offsets: list[int]) -> list[Any]:
    project_name = str(safe_call(project, "GetName") or "")
    timeline_name = str(safe_call(timeline, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    require_arphe_name(timeline_name, "timeline")
    if not (registry.timeline_allowed(project_name, timeline_name) or timeline_name in config.allowed_timelines):
        raise ValidationError("Cattura consentita solo su timeline creata o allowlisted dal bridge")

    start, fps, offsets = _validate_offsets(timeline, frame_offsets)
    output_root = _diagnostic_root(config)
    native_capture = _supports_timeline_export_frame(resolve, timeline)
    previous_page = safe_call(resolve, "GetCurrentPage") if not native_capture else None
    previous_timecode = safe_call(timeline, "GetCurrentTimecode") if not native_capture else None
    if not native_capture:
        if not safe_call(resolve, "OpenPage", "edit"):
            raise RuntimeError("Impossibile aprire la pagina Edit per la cattura")
        if not isinstance(previous_timecode, str) or not previous_timecode:
            if isinstance(previous_page, str) and previous_page:
                safe_call(resolve, "OpenPage", previous_page)
            raise RuntimeError("Impossibile leggere il timecode corrente dalla pagina Edit")
    captures: list[tuple[int, str, Path]] = []
    attempted_paths: list[Path] = []
    playhead_restored = False
    try:
        stamp = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        for offset in offsets:
            timecode = frame_to_timecode(start + offset, fps)
            path = output_root / f"ARPHE_FRAME_{stamp}_{offset:06d}.jpg"
            attempted_paths.append(path)
            if native_capture:
                _timeline_export_frame(timeline, offset, path)
            else:
                if not safe_call(timeline, "SetCurrentTimecode", timecode):
                    raise RuntimeError(f"Impossibile posizionare il playhead al frame {offset}")
                if not safe_call(project, "ExportCurrentFrameAsStill", str(path)) or not path.is_file():
                    raise RuntimeError(f"Esportazione frame {offset} fallita")
            captures.append((offset, timecode, path))
        store = artifact_store_for(config)
        for _, _, path in captures:
            store.register_path(
                path,
                kind="file",
                category="DIAGNOSTIC_CAPTURE",
                producer="capture_timeline_frames",
                managed_root_id="render_root",
            )
    except Exception:
        for path in attempted_paths:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    finally:
        if native_capture:
            playhead_restored = True
        else:
            if isinstance(previous_timecode, str) and previous_timecode:
                playhead_restored = bool(safe_call(timeline, "SetCurrentTimecode", previous_timecode))
            if isinstance(previous_page, str) and previous_page:
                safe_call(resolve, "OpenPage", previous_page)

    result: list[Any] = [{
        "ok": True,
        "action": "capture_timeline_frames",
        "project": project_name,
        "timeline": timeline_name,
        "fps": fps,
        "captures": [{"frame_offset": offset, "timecode": timecode}
                     for offset, timecode, _ in captures],
        "capture_method": ("timeline_export_frame" if native_capture
                           else "project_export_current_frame"),
        "playhead_restored": playhead_restored,
        "output_paths_disclosed": False,
    }]
    result.extend(Image(path=path) for _, _, path in captures)
    return result
