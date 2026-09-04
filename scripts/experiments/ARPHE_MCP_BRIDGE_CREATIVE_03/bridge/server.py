from __future__ import annotations

from typing import Any, Callable

from mcp.server import MCPServer

from .audit import write_audit
from .asset_tools import add_asset
from .config import load_config
from .creative_tools import (add_end_card as do_add_end_card,
                             add_review_card as do_add_review_card,
                             animate_element, animate_stack,
                             set_review_highlight as do_set_review_highlight)
from .feature_flags import report as feature_report
from .fusion_tools import (add_background, add_text, create_composition,
                           retime)
from .project_tools import (create_project as do_create_project,
                            save_project as do_save_project,
                            set_current_project as do_set_current_project)
from .registry import Registry
from .render_tools import render_preview as do_render_preview
from .resolve_connection import context, safe_call
from .safety import ValidationError
from .timeline_tools import (create_safe_working_timeline as do_safe_timeline,
                             create_timeline as do_create_timeline,
                             duplicate_timeline as do_duplicate_timeline,
                             set_current_timeline as do_set_current_timeline)


mcp = MCPServer(
    "ARPHE Resolve Creative",
    instructions=(
        "Bridge creativo ARPHE non distruttivo. Opera solo su progetti/timeline ARPHE o allowlisted; "
        "le capability Fusion/Review/Motion/Assets/Render sono disabilitate finché il relativo gate "
        "non viene abilitato nella config locale. Nessuna esecuzione arbitraria è disponibile."
    ),
)


def _error(exc: Exception) -> dict[str, Any]:
    return {"ok": False, "stage": "validation" if isinstance(exc, ValidationError) else "runtime",
            "error_type": type(exc).__name__, "error": str(exc)}


def _runtime() -> tuple[Any, Any, Any, Any, Any, Registry, dict | None]:
    config = load_config()
    resolve, manager, project, timeline, error = context()
    return resolve, manager, project, timeline, config, Registry(config.state_path), error


def _call(operation: Callable[..., dict], *args: Any, **kwargs: Any) -> dict:
    try:
        result = operation(*args, **kwargs)
    except Exception as exc:
        result = _error(exc)
    try:
        config = load_config()
        write_audit(config.audit_log_path, str(result.get("action") or operation.__name__), result)
    except Exception:
        pass
    return result


@mcp.tool()
def ping() -> dict[str, Any]:
    """Harmless bridge/config health check."""
    try:
        config = load_config()
        return {"ok": True, "bridge": "ARPHE_MCP_BRIDGE_CREATIVE_03", "mode": "CREATIVE_GATED",
                "configured_feature_flags": config.flags, "arbitrary_execution": False}
    except Exception as exc:
        return _error(exc)


@mcp.tool()
def resolve_status() -> dict[str, Any]:
    """Read the current Resolve context without modifying it."""
    try:
        resolve, _, project, timeline, _, _, error = _runtime()
        if error:
            return error
        result = {"ok": True, "resolve_version": safe_call(resolve, "GetVersionString") or safe_call(resolve, "GetVersion"),
                  "project_name": safe_call(project, "GetName") if project else None,
                  "timeline_name": safe_call(timeline, "GetName") if timeline else None,
                  "timeline_fps": safe_call(timeline, "GetSetting", "timelineFrameRate") if timeline else None,
                  "video_track_count": safe_call(timeline, "GetTrackCount", "video") if timeline else None,
                  "audio_track_count": safe_call(timeline, "GetTrackCount", "audio") if timeline else None,
                  "v1_clip_count": None, "a1_clip_count": None}
        if timeline:
            result["v1_clip_count"] = len(safe_call(timeline, "GetItemListInTrack", "video", 1) or [])
            result["a1_clip_count"] = len(safe_call(timeline, "GetItemListInTrack", "audio", 1) or [])
        return result
    except Exception as exc:
        return _error(exc)


@mcp.tool()
def get_feature_flags() -> dict[str, Any]:
    """Return configured, implemented, available and validated state separately."""
    try:
        _, manager, project, timeline, config, _, error = _runtime()
        return {"ok": True, "connection": error, "capabilities": feature_report(config, manager, project, timeline)}
    except Exception as exc:
        return _error(exc)


@mcp.tool()
def create_safe_working_timeline(name_prefix: str = "ARPHE_CHATGPT_TEST") -> dict[str, Any]:
    """Validated legacy-safe primitive: create one empty ARPHE timeline and restore the original."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        if not project: return {"ok": False, "stage": "preflight", "error": "Serve un progetto aperto."}
        return _call(do_safe_timeline, project, config, registry, name_prefix)
    except Exception as exc: return _error(exc)


@mcp.tool()
def create_project(project_name: str) -> dict[str, Any]:
    """Create a new, uniquely named ARPHE project; never overwrite."""
    try:
        _, manager, _, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_create_project, manager, config, registry, project_name)
    except Exception as exc: return _error(exc)


@mcp.tool()
def set_current_project(project_name: str) -> dict[str, Any]:
    """Load only an ARPHE project registered or explicitly allowlisted locally."""
    try:
        _, manager, _, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_set_current_project, manager, config, registry, project_name)
    except Exception as exc: return _error(exc)


@mcp.tool()
def create_timeline(name: str, width: int = 1080, height: int = 1920, fps: float = 30.0) -> dict[str, Any]:
    """Create a separate ARPHE timeline with allowlisted format settings."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        if not project: return {"ok": False, "stage": "preflight", "error": "Serve un progetto aperto."}
        return _call(do_create_timeline, project, config, registry, name, width, height, fps)
    except Exception as exc: return _error(exc)


@mcp.tool()
def set_current_timeline(name: str) -> dict[str, Any]:
    """Select only an ARPHE or locally allowlisted timeline."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_set_current_timeline, project, config, registry, name)
    except Exception as exc: return _error(exc)


@mcp.tool()
def duplicate_timeline_version(source_timeline: str, requested_suffix: str | None = "V2",
                               target_name: str | None = None) -> dict[str, Any]:
    """Duplicate an allowed timeline into a new ARPHE version without modifying its source."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_duplicate_timeline, project, config, registry, source_timeline, requested_suffix, target_name)
    except Exception as exc: return _error(exc)


@mcp.tool()
def get_creative_status() -> dict[str, Any]:
    """Read project, timeline, duration, track/Fusion counts and capability flags."""
    try:
        resolve, manager, project, timeline, config, _, error = _runtime()
        if error: return error
        start = safe_call(timeline, "GetStartFrame") if timeline else None
        end = safe_call(timeline, "GetEndFrame") if timeline else None
        fusion_count = 0
        if timeline:
            for track in range(1, int(safe_call(timeline, "GetTrackCount", "video") or 0) + 1):
                for item in safe_call(timeline, "GetItemListInTrack", "video", track) or []:
                    fusion_count += int(safe_call(item, "GetFusionCompCount") or 0)
        return {"ok": True, "resolve_version": safe_call(resolve, "GetVersionString") or safe_call(resolve, "GetVersion"),
                "project": safe_call(project, "GetName"), "timeline": safe_call(timeline, "GetName"),
                "resolution": {"width": safe_call(timeline, "GetSetting", "timelineResolutionWidth"),
                               "height": safe_call(timeline, "GetSetting", "timelineResolutionHeight")},
                "fps": safe_call(timeline, "GetSetting", "timelineFrameRate"), "start_frame": start, "end_frame": end,
                "duration_frames": end - start if isinstance(start, int) and isinstance(end, int) else None,
                "tracks": {kind: safe_call(timeline, "GetTrackCount", kind) for kind in ("video", "audio", "subtitle")},
                "fusion_composition_count": fusion_count,
                "feature_flags": feature_report(config, manager, project, timeline)}
    except Exception as exc: return _error(exc)


@mcp.tool()
def create_fusion_composition(name: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Insert one controlled Fusion composition into the current allowed timeline."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(create_composition, project, timeline, config, registry, name, start_frame, end_frame)
    except Exception as exc: return _error(exc)


@mcp.tool()
def add_brand_background(composition_id: str, color_role: str = "ivory") -> dict[str, Any]:
    """Set the composition canvas to one configured ARPHE palette role."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(add_background, project, timeline, config, registry, composition_id, color_role)
    except Exception as exc: return _error(exc)


def _asset(kind: str, path: str, start_frame: int, end_frame: int, track_index: int) -> dict:
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(add_asset, project, timeline, config, registry, path, kind, start_frame, end_frame, track_index)
    except Exception as exc: return _error(exc)


@mcp.tool()
def add_logo(path: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Import one allowlisted logo image onto video track 3."""
    return _asset("image", path, start_frame, end_frame, 3)


@mcp.tool()
def add_image_asset(path: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Import one allowlisted image onto video track 2."""
    return _asset("image", path, start_frame, end_frame, 2)


@mcp.tool()
def add_video_background(path: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Import one allowlisted video background onto video track 1."""
    return _asset("video", path, start_frame, end_frame, 1)


@mcp.tool()
def add_text_plus(composition_id: str, text: str, start_frame: int, end_frame: int,
                  style_role: str = "dark_brown", size: float = 0.06) -> dict[str, Any]:
    """Add controlled Text+ to a bridge-created composition."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(add_text, project, timeline, config, registry, composition_id, text,
                     start_frame, end_frame, style_role, size)
    except Exception as exc: return _error(exc)


@mcp.tool()
def add_review_card(composition_id: str, text: str, stars: int, start_frame: int, end_frame: int,
                    style_role: str = "cream", highlight_text: str | None = None,
                    small_label: str | None = None) -> dict[str, Any]:
    """Create one controlled review card; review content is input and never hardcoded."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(do_add_review_card, project, timeline, config, registry, composition_id,
                     text, stars, start_frame, end_frame, style_role, highlight_text, small_label)
    except Exception as exc: return _error(exc)


@mcp.tool()
def set_review_highlight(composition_id: str, card_id: str, highlight_text: str) -> dict[str, Any]:
    """Set controlled highlight text on a bridge-created review card."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(do_set_review_highlight, project, timeline, config, registry,
                     composition_id, card_id, highlight_text)
    except Exception as exc: return _error(exc)


@mcp.tool()
def add_end_card(composition_id: str, headline: str, cta: str, start_frame: int,
                 end_frame: int, style_role: str = "burgundy") -> dict[str, Any]:
    """Create a controlled CTA/end card in a bridge-created composition."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(do_add_end_card, project, timeline, config, registry, composition_id,
                     headline, cta, start_frame, end_frame, style_role)
    except Exception as exc: return _error(exc)


def _animate(element_id: str, composition_id: str, preset: str, duration_frames: int,
             direction: str, easing: str, settle: bool, exit_motion: bool) -> dict:
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(animate_element, project, timeline, config, registry, composition_id,
                     element_id, preset, duration_frames, direction, easing, settle, exit_motion)
    except Exception as exc: return _error(exc)


@mcp.tool()
def animate_card_entry(composition_id: str, card_id: str, preset: str = "ARPHE_SOFT_DROP",
                       duration_frames: int = 18, direction: str = "top",
                       easing: str = "ease_out", settle: bool = True) -> dict[str, Any]:
    """Animate a semantic card entry with one allowlisted preset."""
    return _animate(card_id, composition_id, preset, duration_frames, direction, easing, settle, False)


@mcp.tool()
def animate_card_exit(composition_id: str, card_id: str, preset: str = "ARPHE_ELEGANT_REVEAL",
                      duration_frames: int = 15, direction: str = "bottom",
                      easing: str = "ease_in_out", settle: bool = False) -> dict[str, Any]:
    """Animate a semantic card exit with one allowlisted preset."""
    return _animate(card_id, composition_id, preset, duration_frames, direction, easing, settle, True)


@mcp.tool()
def animate_review_stack(composition_id: str, card_ids: list[str], start_frame: int,
                         stagger_frames: int = 12, overlap: float = 0.25,
                         direction: str = "top", rotation_pattern: str = "alternate",
                         position_offsets: list[float] | None = None, scale_start: float = 0.94,
                         opacity_start: float = 0.0, duration_frames: int = 18,
                         easing: str = "ease_out", settle: bool = True) -> dict[str, Any]:
    """Animate an ordered stack of 1-8 bridge-created review cards."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(animate_stack, project, timeline, config, registry, composition_id, card_ids,
                     start_frame, stagger_frames, overlap, direction, rotation_pattern, position_offsets,
                     scale_start, opacity_start, duration_frames, easing, settle)
    except Exception as exc: return _error(exc)


@mcp.tool()
def apply_transition_preset(composition_id: str, element_id: str,
                            preset: str = "ARPHE_ELEGANT_REVEAL",
                            duration_frames: int = 18) -> dict[str, Any]:
    """Apply one allowlisted semantic transition; no arbitrary Fusion properties."""
    return _animate(element_id, composition_id, preset, duration_frames, "top", "ease_out", True, False)


@mcp.tool()
def retime_creative_duration(composition_id: str, duration_frames: int) -> dict[str, Any]:
    """Adjust the controlled Fusion work range; timeline trim remains a manual validation gate."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(retime, project, timeline, config, registry, composition_id, duration_frames)
    except Exception as exc: return _error(exc)


@mcp.tool()
def save_project() -> dict[str, Any]:
    """Save only the current registered/allowlisted ARPHE project."""
    try:
        _, manager, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_save_project, manager, project, config, registry)
    except Exception as exc: return _error(exc)


@mcp.tool()
def render_preview(output_name: str = "ARPHE_PREVIEW") -> dict[str, Any]:
    """Queue/start a preview only when CAP_RENDER is explicitly enabled; default is false."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(do_render_preview, project, timeline, config, registry, output_name)
    except Exception as exc: return _error(exc)


def run() -> None:
    mcp.run()
