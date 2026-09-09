from __future__ import annotations

from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import Image

from .config import CreativeConfig
from .fusion_tools import find_composition
from .registry import Registry
from .resolve_connection import safe_call
from .safety import ValidationError, require_arphe_name


MAX_FRAME_BATCH = 8
MAX_DIAGNOSTIC_FILES = 64
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
    _prune_diagnostics(root)
    return root


def _prune_diagnostics(root: Path) -> None:
    files = sorted((item for item in root.glob("ARPHE_FRAME_*")
                    if item.is_file() and item.suffix.lower() in {".jpg", ".png"}),
                   key=lambda item: item.stat().st_mtime, reverse=True)
    for old in files[MAX_DIAGNOSTIC_FILES:]:
        try:
            old.unlink()
        except OSError:
            pass


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
    previous_page = safe_call(resolve, "GetCurrentPage")
    if not safe_call(resolve, "OpenPage", "edit"):
        raise RuntimeError("Impossibile aprire la pagina Edit per la cattura")
    previous_timecode = safe_call(timeline, "GetCurrentTimecode")
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
            if not safe_call(timeline, "SetCurrentTimecode", timecode):
                raise RuntimeError(f"Impossibile posizionare il playhead al frame {offset}")
            path = output_root / f"ARPHE_FRAME_{stamp}_{offset:06d}.jpg"
            attempted_paths.append(path)
            if not safe_call(project, "ExportCurrentFrameAsStill", str(path)) or not path.is_file():
                raise RuntimeError(f"Esportazione frame {offset} fallita")
            captures.append((offset, timecode, path))
    except Exception:
        for path in attempted_paths:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    finally:
        if isinstance(previous_timecode, str) and previous_timecode:
            playhead_restored = bool(safe_call(timeline, "SetCurrentTimecode", previous_timecode))
        if isinstance(previous_page, str) and previous_page:
            safe_call(resolve, "OpenPage", previous_page)

    _prune_diagnostics(output_root)

    result: list[Any] = [{
        "ok": True,
        "action": "capture_timeline_frames",
        "project": project_name,
        "timeline": timeline_name,
        "fps": fps,
        "captures": [{"frame_offset": offset, "timecode": timecode}
                     for offset, timecode, _ in captures],
        "playhead_restored": playhead_restored,
        "output_paths_disclosed": False,
    }]
    result.extend(Image(path=path) for _, _, path in captures)
    return result
