from __future__ import annotations

from pathlib import Path
import re
import time
from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import Image

from .artifact_records import ProducerId, artifact_store_for
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
    "TopLeftRed", "TopLeftGreen", "TopLeftBlue", "TopLeftAlpha",
)
SAFE_CONNECTION_INPUTS = ("Input", "Background", "Foreground", "EffectMask")


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


def _connections(tool: Any) -> dict[str, str]:
    connected: dict[str, str] = {}
    for input_name in SAFE_CONNECTION_INPUTS:
        socket = safe_call(tool, "FindInput", input_name)
        output = safe_call(socket, "GetConnectedOutput") if socket is not None else None
        source = safe_call(output, "GetTool") if output is not None else None
        attrs = _attrs(source) if source is not None else {}
        source_name = attrs.get("TOOLS_Name")
        if isinstance(source_name, str) and source_name:
            connected[input_name] = source_name
    inputs = safe_call(tool, "GetInputList") or {}
    values = inputs.values() if isinstance(inputs, dict) else inputs
    for socket in values:
        attrs = _attrs(socket)
        input_name = attrs.get("INPS_ID") or attrs.get("INPS_Name")
        output = safe_call(socket, "GetConnectedOutput")
        source = safe_call(output, "GetTool") if output is not None else None
        source_name = _attrs(source).get("TOOLS_Name") if source is not None else None
        if isinstance(input_name, str) and isinstance(source_name, str) and source_name:
            connected[input_name] = source_name
    return connected


def _video_track_index(timeline: Any, target: Any) -> int | None:
    target_id = safe_call(target, "GetUniqueId")
    target_key = (safe_call(target, "GetName"), safe_call(target, "GetStart"),
                  safe_call(target, "GetEnd"))
    for track in range(1, int(safe_call(timeline, "GetTrackCount", "video") or 0) + 1):
        for item in safe_call(timeline, "GetItemListInTrack", "video", track) or []:
            if item is target:
                return track
            item_id = safe_call(item, "GetUniqueId")
            if target_id and item_id == target_id:
                return track
            if (safe_call(item, "GetName"), safe_call(item, "GetStart"),
                    safe_call(item, "GetEnd")) == target_key:
                return track
    return None


def inspect_fusion_graph(timeline: Any, registry: Registry, composition_id: str) -> dict[str, Any]:
    item, comp = find_composition(timeline, registry, composition_id)
    comp_attrs = safe_call(comp, "GetAttrs") or {}
    track_index = _video_track_index(timeline, item)
    item_properties = safe_call(item, "GetProperty") or {}
    safe_item_properties = {
        key: _number(item_properties.get(key))
        for key in ("CompositeMode", "Opacity", "ZoomX", "ZoomY", "PositionX", "PositionY")
        if isinstance(item_properties, dict) and key in item_properties
    }
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
        connections = _connections(tool)
        if connections:
            node["connections"] = connections
        styled_text = safe_call(tool, "GetInput", "StyledText")
        if isinstance(styled_text, str):
            node["text_length"] = len(styled_text)
        nodes.append(node)
    return {
        "ok": True,
        "action": "inspect_fusion_graph",
        "composition_id": composition_id,
        "timeline_item": safe_call(item, "GetName"),
        "timeline_item_range": [safe_call(item, "GetStart"), safe_call(item, "GetEnd")],
        "timeline_item_duration": safe_call(item, "GetDuration"),
        "timeline_item_enabled": safe_call(item, "GetClipEnabled"),
        "timeline_item_video_track": track_index,
        "timeline_item_track_enabled": (
            safe_call(timeline, "GetIsTrackEnabled", "video", track_index)
            if isinstance(track_index, int) else None
        ),
        "timeline_item_properties": safe_item_properties,
        "composition_range": {
            key: comp_attrs.get(key)
            for key in ("COMPN_RenderStart", "COMPN_RenderEnd",
                        "COMPN_GlobalStart", "COMPN_GlobalEnd")
            if key in comp_attrs
        },
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


def capture_timeline_frames(resolve: Any, project: Any, timeline: Any, config: CreativeConfig,
                            registry: Registry, frame_offsets: list[int], *,
                            bridge_owned_provisional: bool = False) -> list[Any]:
    project_name = str(safe_call(project, "GetName") or "")
    timeline_name = str(safe_call(timeline, "GetName") or "")
    require_arphe_name(project_name, "progetto")
    is_bridge_provisional = bool(
        bridge_owned_provisional
        and re.fullmatch(r"__ARPHE_VERTICAL_VERTICAL_[0-9A-F]{32}", timeline_name)
    )
    if not is_bridge_provisional:
        require_arphe_name(timeline_name, "timeline")
    if not (is_bridge_provisional or registry.timeline_allowed(project_name, timeline_name)
            or timeline_name in config.allowed_timelines):
        raise ValidationError("Cattura consentita solo su timeline creata o allowlisted dal bridge")

    start, fps, offsets = _validate_offsets(timeline, frame_offsets)
    store = artifact_store_for(config)
    project_id = store.bind_project(safe_call(project, "GetUniqueId"))
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
    registration_started = False
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
        registration_started = True
        for _, _, path in captures:
            store.register_produced_path(
                path,
                kind="file",
                category="DIAGNOSTIC_CAPTURE",
                producer=ProducerId.CAPTURE_TIMELINE_FRAMES,
                project_id=project_id, protection_class="DISPOSABLE",
                managed_root_id="render_root",
            )
    except Exception as exc:
        if registration_started:
            raise RuntimeError(f"Artifact registration failed; captures retained for review: {exc}") from exc
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
