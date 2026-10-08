from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Callable

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .audit import write_audit
from .asset_tools import add_asset
from .audio_tools import audio_job as do_audio_job, start_audio_job as do_start_audio_job
from .artifact_hygiene import (inspect_artifacts as do_inspect_artifacts,
                               restore_artifact as do_restore_artifact,
                               run_maintenance as do_run_maintenance)
from .artifact_records import artifact_store_for, load_artifact_policy
from .config import load_config
from .creative_tools import (add_end_card as do_add_end_card,
                             animate_element, animate_stack,
                             set_review_highlight as do_set_review_highlight)
from .diagnostic_tools import (capture_timeline_frames as do_capture_timeline_frames,
                               inspect_fusion_graph as do_inspect_fusion_graph)
from .edge_fade_tools import create_edge_fade_test as do_create_edge_fade_test
from .editorial_workflows import (EditorialBrief, load_render_profile_registry,
                                  load_workflow_registry,
                                  resolve_delivery_profile,
                                  validate_editorial_brief as do_validate_editorial_brief)
from .format_contract import ResolvedFormat
from .feature_flags import report as feature_report
from .fusion_tools import (MAX_AUTOMATIC_FUSION_FRAMES, add_background, add_text,
                           create_composition, retime)
from .longform_tools import (apply_plan as do_apply_longform_plan,
                             list_media as do_list_longform_media,
                             transcript_chunk as do_transcript_chunk,
                             transcript_metadata as do_transcript_metadata,
                             validate_plan as do_validate_longform_plan)
from .project_tools import (create_project as do_create_project,
                            save_project as do_save_project,
                            set_current_project as do_set_current_project)
from .registry import Registry
from .readability_approvals import approve_readability as do_approve_readability
from .review_workflow import (
    add_guarded_review_card as do_add_guarded_review_card,
    create_guarded_review_sequence as do_create_guarded_review_sequence,
    inspect_sequence_readability as do_inspect_sequence_readability,
)
from .render_batches import (approve_render_batch as do_approve_render_batch,
                             create_render_batch)
from .render_tools import (queue_longform_exports as do_queue_longform_exports,
                           queue_publish_package_exports as do_queue_publish_package_exports,
                           render_preview as do_render_preview,
                           start_longform_exports as do_start_longform_exports,
                           prepare_render_batch as do_prepare_render_batch,
                           start_render_batch as do_start_render_batch,
                           get_render_batch_status as do_get_render_batch_status,
                           cancel_render_batch as do_cancel_render_batch)
from .resolve_retirement import (
    approve_retirement as do_approve_resolve_retirement,
    execute_retirement as do_execute_resolve_retirement,
    inspect_retirements as do_inspect_resolve_retirements,
    prepare_retirement as do_prepare_resolve_retirement,
    recover_retirement as do_recover_resolve_retirement,
    retirement_store_for,
)
from .media_verification import verify_and_promote_batch as do_verify_render_batch
from .maintenance_scheduler import start_lazy_maintenance
from .resolve_connection import RESOLVE_ACCESS_LOCK, context, safe_call
from .safety import PlaybackFpsActionRequired, ValidationError
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

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
SAFE_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)
IDEMPOTENT_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
DESTRUCTIVE_IDEMPOTENT_WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False
)


def _error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, PlaybackFpsActionRequired):
        return {"ok": False, "stage": "operator_action_required",
                "error_type": type(exc).__name__, "error": str(exc), **exc.payload()}
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


@mcp.tool(annotations=READ_ONLY)
def list_editorial_workflows() -> dict[str, Any]:
    """List versioned workflow metadata without local briefs, paths or media content."""
    try:
        config = load_config()
        registry = load_workflow_registry(config.workflow_registry_path)
        return {"ok": True, "workflows": [
            {"workflow_id": item.workflow_id, "version": item.version, "label": item.label,
             "purpose": item.purpose, "automation_level": item.automation_level,
             "allowed_profiles": list(item.allowed_profiles), "questions": list(item.questions)}
            for item in registry.workflows.values()]}
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def validate_editorial_brief(brief: dict[str, Any]) -> dict[str, Any]:
    """Validate and store a local structured brief; performs no Resolve write."""
    try:
        config = load_config(); registry = Registry(config.state_path)
        value = do_validate_editorial_brief(brief, load_workflow_registry(config.workflow_registry_path))
        registry.save_brief(value)
        return {"ok": not value.unresolved_questions, "action": "validate_editorial_brief",
                "brief_id": value.brief_id, "workflow_id": value.workflow_id,
                "unresolved_questions": list(value.unresolved_questions)}
    except Exception as exc: return _error(exc)


def _stored_brief(registry: Registry, brief_id: str) -> EditorialBrief:
    raw = registry.brief(brief_id)
    if raw is None: raise ValidationError("Brief non trovato")
    return EditorialBrief(raw["brief_id"], raw["workflow_id"], raw["workflow_version"],
                          raw["operator_role"], raw.get("primary_source"),
                          tuple(raw.get("requested_outputs", [])), raw.get("format_request", {}),
                          raw.get("answers", {}), tuple(raw.get("unresolved_questions", [])))


@mcp.tool(annotations=SAFE_WRITE)
def prepare_render_batch(brief_id: str, profile_id: str, project_name: str,
                         timeline_names: list[str], output_names: list[str],
                         width: int, height: int, frame_rate: str) -> dict[str, Any]:
    """Create and prepare an isolated batch; never starts rendering."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        brief = _stored_brief(registry, brief_id)
        profile = resolve_delivery_profile(
            brief, profile_id, load_render_profile_registry(config.render_profile_registry_path)
        )
        rate = Fraction(frame_rate)
        if profile.resolution_mode == "fixed" and profile.resolution != (width, height):
            raise ValidationError("Risoluzione incompatibile con il render profile")
        if profile.frame_rate_mode == "fixed" and Fraction(profile.frame_rate or "0") != rate:
            raise ValidationError("Frame rate incompatibile con il render profile")
        batch = create_render_batch(brief, profile, ResolvedFormat(width, height, rate, rate),
                                    project_name, tuple(timeline_names), tuple(output_names), config.workstation_id)
        registry.save_render_batch(batch)
        return _call(do_prepare_render_batch, project, config, registry, batch.batch_id)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def approve_render_batch(batch_id: str, operator_role: str) -> dict[str, Any]:
    """Approve one prepared batch fingerprint."""
    try:
        config = load_config(); batch = do_approve_render_batch(Registry(config.state_path), batch_id, operator_role)
        return {"ok": True, "action": "approve_render_batch", "batch_id": batch_id,
                "actor_role": operator_role, "transition": "PREPARED->APPROVED",
                "fingerprint": batch.approval_token, "approval_token": batch.approval_token,
                "job_ids": list(batch.created_job_ids)}
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def start_render_batch(batch_id: str, approval_token: str) -> dict[str, Any]:
    """Start only job IDs bound to one approved batch."""
    try:
        _, _, project, _, _, registry, error = _runtime()
        if error: return error
        return _call(do_start_render_batch, project, registry, batch_id, approval_token)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def get_render_batch_status(batch_id: str) -> dict[str, Any]:
    """Read persisted batch and owned Resolve job status."""
    try:
        _, _, project, _, _, registry, error = _runtime()
        if error: return error
        return _call(do_get_render_batch_status, project, registry, batch_id)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def verify_render_batch(batch_id: str) -> dict[str, Any]:
    """Verify staged media and promote only conforming outputs."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_verify_render_batch, project, config, registry, batch_id)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def cancel_render_batch(batch_id: str, operator_role: str) -> dict[str, Any]:
    """Cancel only jobs owned by the named batch; technical role required."""
    try:
        _, _, project, _, _, registry, error = _runtime()
        if error: return error
        return _call(do_cancel_render_batch, project, registry, batch_id, operator_role)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def ping() -> dict[str, Any]:
    """Harmless bridge/config health check."""
    try:
        config = load_config()
        return {"ok": True, "bridge": "ARPHE_MCP_BRIDGE_CREATIVE_03", "mode": "CREATIVE_GATED",
                "workstation_id": config.workstation_id,
                "configured_feature_flags": config.flags, "arbitrary_execution": False}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def resolve_status() -> dict[str, Any]:
    """Read the current Resolve context without modifying it."""
    with RESOLVE_ACCESS_LOCK:
        try:
            resolve, _, project, timeline, config, _, error = _runtime()
            if error:
                return {**error, "workstation_id": config.workstation_id}
            result = {"ok": True, "workstation_id": config.workstation_id,
                      "resolve_version": safe_call(resolve, "GetVersionString") or safe_call(resolve, "GetVersion"),
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


@mcp.tool(annotations=READ_ONLY)
def get_feature_flags() -> dict[str, Any]:
    """Return configured, implemented, available and validated state separately."""
    with RESOLVE_ACCESS_LOCK:
        try:
            _, manager, project, timeline, config, _, error = _runtime()
            return {"ok": True, "workstation_id": config.workstation_id,
                    "connection": error, "capabilities": feature_report(config, manager, project, timeline)}
        except Exception as exc:
            return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def list_longform_media() -> dict[str, Any]:
    """List video files only inside locally allowlisted longform folders."""
    try:
        return _call(do_list_longform_media, load_config())
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def get_transcript_metadata(transcript_path: str) -> dict[str, Any]:
    """Read metadata and counts from one allowlisted ARPHE_TRANSCRIPT_V1 JSON."""
    try:
        return _call(do_transcript_metadata, transcript_path, load_config())
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def get_transcript_chunk(transcript_path: str, start_second: float,
                         end_second: float) -> dict[str, Any]:
    """Read at most ten minutes from one allowlisted transcript JSON."""
    try:
        return _call(do_transcript_chunk, transcript_path, load_config(), start_second, end_second)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def validate_longform_edit_plan(clips: list[dict[str, Any]], fps: float = 30.0) -> dict[str, Any]:
    """Validate a non-destructive longform plan and convert seconds to source frames."""
    try:
        plan = do_validate_longform_plan(clips, fps)
        canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {"ok": True, "action": "validate_longform_edit_plan",
                "clip_count": len(plan), "total_frames": sum(v["duration_frames"] for v in plan),
                "maximum_clip_frames": max(v["duration_frames"] for v in plan),
                "fps": float(fps), "plan_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "writes_performed": False}
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def apply_longform_edit_plan(media_path: str, project_name: str, master_timeline_name: str,
                             clips: list[dict[str, Any]], fps: float = 30.0,
                             enhanced_audio_path: str | None = None,
                             full_timeline_name: str | None = None,
                             apply_edge_fades: bool = False) -> dict[str, Any]:
    """Create a new project, one master and separate clip timelines; never alter the source."""
    try:
        resolve, manager, _, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_apply_longform_plan, resolve, manager, config, registry, media_path,
                     project_name, master_timeline_name, clips, fps, enhanced_audio_path,
                     full_timeline_name, apply_edge_fades)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def start_prepare_longform_audio(media_path: str,
                                 preset: str = "ARPHE_DIALOGUE_CLEAN_V1") -> dict[str, Any]:
    """Start whole-source dialogue restoration asynchronously; poll its job before cutting."""
    try:
        return _call(do_start_audio_job, load_config(), media_path, preset)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def get_longform_audio_job(job_id: str) -> dict[str, Any]:
    """Read progress and output path for a previously started audio-restoration job."""
    try:
        return _call(do_audio_job, load_config(), job_id)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def create_safe_working_timeline(name_prefix: str = "ARPHE_CHATGPT_TEST") -> dict[str, Any]:
    """Validated legacy-safe primitive: create one empty ARPHE timeline and restore the original."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        if not project: return {"ok": False, "stage": "preflight", "error": "Serve un progetto aperto."}
        return _call(do_safe_timeline, project, config, registry, name_prefix)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def create_project(project_name: str) -> dict[str, Any]:
    """Create a new, uniquely named ARPHE project; never overwrite."""
    try:
        _, manager, _, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_create_project, manager, config, registry, project_name)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def set_current_project(project_name: str) -> dict[str, Any]:
    """Load only an ARPHE project registered or explicitly allowlisted locally."""
    try:
        _, manager, _, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_set_current_project, manager, config, registry, project_name)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def create_timeline(name: str, width: int = 1080, height: int = 1920, fps: float = 30.0) -> dict[str, Any]:
    """Create a separate ARPHE timeline with allowlisted format settings."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        if not project: return {"ok": False, "stage": "preflight", "error": "Serve un progetto aperto."}
        return _call(do_create_timeline, project, config, registry, name, width, height, fps)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def set_current_timeline(name: str) -> dict[str, Any]:
    """Select only an ARPHE or locally allowlisted timeline."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_set_current_timeline, project, config, registry, name)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def duplicate_timeline_version(source_timeline: str, requested_suffix: str | None = "V2",
                               target_name: str | None = None) -> dict[str, Any]:
    """Duplicate an allowed timeline into a new ARPHE version without modifying its source."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_duplicate_timeline, project, config, registry, source_timeline, requested_suffix, target_name)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def create_edge_fade_test(source_timeline: str, target_name: str,
                          video_in_frames: int = 6, video_out_frames: int = 8,
                          audio_in_frames: int = 4, audio_out_frames: int = 10) -> dict[str, Any]:
    """Duplicate a one-clip timeline and add deterministic video/audio edge fades."""
    try:
        _, _, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_create_edge_fade_test, project, config, registry, source_timeline, target_name,
                     video_in_frames, video_out_frames, audio_in_frames, audio_out_frames)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
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


@mcp.tool(annotations=READ_ONLY)
def inspect_fusion_graph(composition_id: str) -> dict[str, Any]:
    """Inspect an ARPHE Fusion graph without disclosing text content or modifying Resolve."""
    try:
        _, _, project, timeline, _, registry, error = _runtime()
        if error: return error
        if not project or not timeline: return {"ok": False, "stage": "preflight", "error": "Serve una timeline aperta."}
        return _call(do_inspect_fusion_graph, timeline, registry, composition_id)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def capture_timeline_frames(frame_offsets: list[int]) -> CallToolResult:
    """Export 1-8 exact ARPHE timeline frames as JPEG images and restore the playhead/page."""
    try:
        resolve, _, project, timeline, config, registry, error = _runtime()
        if error:
            result: list[Any] = [error]
        elif not project or not timeline:
            result = [{"ok": False, "stage": "preflight", "error": "Serve una timeline aperta."}]
        else:
            result = do_capture_timeline_frames(
                resolve, project, timeline, config, registry, frame_offsets
            )
    except Exception as exc:
        result = [_error(exc)]

    metadata = result[0]
    content = [TextContent(type="text", text=json.dumps(metadata, ensure_ascii=False, indent=2))]
    content.extend(item.to_image_content() for item in result[1:] if isinstance(item, Image))
    return CallToolResult(content=content, structuredContent=metadata)


@mcp.tool(annotations=SAFE_WRITE)
def create_fusion_composition(name: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Insert one controlled Fusion composition into the current allowed timeline."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(create_composition, project, timeline, config, registry, name, start_frame, end_frame)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
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


@mcp.tool(annotations=SAFE_WRITE)
def add_logo(path: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Import one allowlisted logo image onto video track 3."""
    return _asset("image", path, start_frame, end_frame, 3)


@mcp.tool(annotations=SAFE_WRITE)
def add_image_asset(path: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Import one allowlisted image onto video track 2."""
    return _asset("image", path, start_frame, end_frame, 2)


@mcp.tool(annotations=SAFE_WRITE)
def add_video_background(path: str, start_frame: int, end_frame: int) -> dict[str, Any]:
    """Import one allowlisted video background onto video track 1."""
    return _asset("video", path, start_frame, end_frame, 1)


@mcp.tool(annotations=SAFE_WRITE)
def add_text_plus(composition_id: str, text: str, start_frame: int, end_frame: int,
                  style_role: str = "dark_brown", size: float = 0.06) -> dict[str, Any]:
    """Add controlled Text+ to a bridge-created composition."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(add_text, project, timeline, config, registry, composition_id, text,
                     start_frame, end_frame, style_role, size)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def approve_review_readability(assessment_fingerprint: str, decisions: list[dict[str, Any]],
                               operator_role: str) -> dict[str, Any]:
    """Approve only fingerprint-bound long-card or verbatim-split exceptions."""
    try:
        config = load_config()
        registry = Registry(config.state_path)
        approval = do_approve_readability(
            registry, config.workstation_id, assessment_fingerprint, decisions, operator_role
        )
        return {"ok": True, "action": "approve_review_readability", "token": approval.token,
                "assessment_fingerprint": approval.assessment_fingerprint,
                "workstation_id": approval.workstation_id,
                "decision_count": len(approval.decisions)}
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def inspect_review_readability(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Inspect review timing, type fit and font readiness without mutating Resolve."""
    try:
        _, _, _project, timeline, config, _registry, error = _runtime()
        if error: return error
        return {"ok": True, "action": "inspect_review_readability",
                **do_inspect_sequence_readability(timeline, config, reviews).to_dict()}
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def add_review_card(composition_id: str, text: str, stars: int, start_frame: int, end_frame: int,
                    style_role: str = "cream", highlight_text: str | None = None,
                    small_label: str | None = None,
                    readability_approval_token: str | None = None) -> dict[str, Any]:
    """Create one controlled review card; review content is input and never hardcoded."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(do_add_guarded_review_card, project, timeline, config, registry, composition_id,
                     text, stars, start_frame, end_frame, style_role, highlight_text, small_label,
                     readability_approval_token)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def create_review_sequence(name: str, reviews: list[dict[str, Any]],
                           duration_frames: int = 0, stagger_frames: int = 24,
                           style_role: str = "cream",
                           readability_approval_token: str | None = None) -> dict[str, Any]:
    """Compatibility wrapper; create one gap-free sequence for older clients."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        requested = duration_frames + max(0, len(reviews) - 1) * stagger_frames
        total = 0 if duration_frames == 0 else max(len(reviews), min(MAX_AUTOMATIC_FUSION_FRAMES, requested))
        result = _call(do_create_guarded_review_sequence, project, timeline, config, registry,
                       name, reviews, total, style_role, None, None,
                       readability_approval_token)
        if isinstance(result, dict):
            result["compatibility_mode"] = True
            result["preferred_tool"] = "create_review_sequence_v2"
        return result
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def create_review_sequence_v2(name: str, reviews: list[dict[str, Any]],
                              total_duration_frames: int = 0,
                              style_role: str = "cream", cta: dict[str, Any] | None = None,
                              intro: dict[str, Any] | None = None,
                              readability_approval_token: str | None = None) -> dict[str, Any]:
    """Create 1-8 cards, with optional kit-based intro and branded CTA."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(do_create_guarded_review_sequence, project, timeline, config, registry,
                     name, reviews, total_duration_frames, style_role, cta, intro,
                     readability_approval_token)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def set_review_highlight(composition_id: str, card_id: str, highlight_text: str) -> dict[str, Any]:
    """Set controlled highlight text on a bridge-created review card."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(do_set_review_highlight, project, timeline, config, registry,
                     composition_id, card_id, highlight_text)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
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


@mcp.tool(annotations=SAFE_WRITE)
def animate_card_entry(composition_id: str, card_id: str, preset: str = "ARPHE_SOFT_DROP",
                       duration_frames: int = 18, direction: str = "top",
                       easing: str = "ease_out", settle: bool = True) -> dict[str, Any]:
    """Animate a semantic card entry with one allowlisted preset."""
    return _animate(card_id, composition_id, preset, duration_frames, direction, easing, settle, False)


@mcp.tool(annotations=SAFE_WRITE)
def animate_card_exit(composition_id: str, card_id: str, preset: str = "ARPHE_ELEGANT_REVEAL",
                      duration_frames: int = 15, direction: str = "bottom",
                      easing: str = "ease_in_out", settle: bool = False) -> dict[str, Any]:
    """Animate a semantic card exit with one allowlisted preset."""
    return _animate(card_id, composition_id, preset, duration_frames, direction, easing, settle, True)


@mcp.tool(annotations=SAFE_WRITE)
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


@mcp.tool(annotations=SAFE_WRITE)
def apply_transition_preset(composition_id: str, element_id: str,
                            preset: str = "ARPHE_ELEGANT_REVEAL",
                            duration_frames: int = 18) -> dict[str, Any]:
    """Apply one allowlisted semantic transition; no arbitrary Fusion properties."""
    return _animate(element_id, composition_id, preset, duration_frames, "top", "ease_out", True, False)


@mcp.tool(annotations=SAFE_WRITE)
def retime_creative_duration(composition_id: str, duration_frames: int) -> dict[str, Any]:
    """Adjust the controlled Fusion work range; timeline trim remains a manual validation gate."""
    try:
        _, _, project, timeline, config, registry, error = _runtime()
        if error: return error
        return _call(retime, project, timeline, config, registry, composition_id, duration_frames)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def save_project() -> dict[str, Any]:
    """Save only the current registered/allowlisted ARPHE project."""
    try:
        _, manager, project, _, config, registry, error = _runtime()
        if error: return error
        return _call(do_save_project, manager, project, config, registry)
    except Exception as exc: return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def render_preview(output_name: str = "ARPHE_PREVIEW") -> dict[str, Any]:
    """Deprecated compatibility response; use prepare_render_batch."""
    return {"ok": False, "action": "render_preview", "deprecated": True,
            "render_started": False, "next_action": "prepare_render_batch"}


@mcp.tool(annotations=SAFE_WRITE)
def queue_longform_exports() -> dict[str, Any]:
    """Deprecated compatibility response; use prepare_render_batch."""
    return {"ok": False, "action": "queue_longform_exports", "deprecated": True,
            "render_started": False, "next_action": "prepare_render_batch"}


@mcp.tool(annotations=SAFE_WRITE)
def start_longform_exports() -> dict[str, Any]:
    """Deprecated compatibility response; approved batch start is required."""
    return {"ok": False, "action": "start_longform_exports", "deprecated": True,
            "render_started": False, "next_action": "prepare_render_batch"}


@mcp.tool(annotations=SAFE_WRITE)
def queue_publish_package_exports(full_timeline_name: str, clip_timeline_names: list[str],
                                  output_directory: str) -> dict[str, Any]:
    """Compatibility queue-only wrapper; never starts rendering."""
    return {"ok": False, "action": "queue_publish_package_exports", "deprecated": True,
            "render_started": False, "next_action": "prepare_render_batch"}


def _artifact_components(config: Any) -> tuple[Any, Registry, Any]:
    return (artifact_store_for(config), Registry(config.state_path),
            load_artifact_policy(config.artifact_policy_path))


def _require_artifact_mutation(config: Any) -> None:
    if not config.flags.get("CAP_ARTIFACT_MAINTENANCE", False):
        raise RuntimeError("CAP_ARTIFACT_MAINTENANCE non attiva")


def _require_resolve_retirement(config: Any) -> None:
    if not config.flags.get("CAP_RESOLVE_RETIREMENT", False):
        raise RuntimeError("CAP_RESOLVE_RETIREMENT non attiva")


@mcp.tool(annotations=READ_ONLY)
def inspect_artifact_hygiene() -> dict[str, Any]:
    """Inspect only bridge-owned artifacts; accepts no filesystem path."""
    try:
        config = load_config()
        store, registry, policy = _artifact_components(config)
        return _call(do_inspect_artifacts, config, store, registry, policy, datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=DESTRUCTIVE_IDEMPOTENT_WRITE)
def run_artifact_maintenance() -> dict[str, Any]:
    """Apply the fixed retention policy to registered artifacts only."""
    try:
        config = load_config()
        _require_artifact_mutation(config)
        store, registry, policy = _artifact_components(config)
        return _call(do_run_maintenance, config, store, registry, policy, datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def restore_quarantined_artifact(artifact_id: str) -> dict[str, Any]:
    """Restore one quarantined artifact by opaque ID; accepts no path."""
    try:
        config = load_config()
        _require_artifact_mutation(config)
        store, _, policy = _artifact_components(config)
        return _call(do_restore_artifact, config, store, artifact_id, policy, datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def inspect_resolve_retirements() -> dict[str, Any]:
    """Inspect archive-first Resolve retirements; returns no absolute filesystem path."""
    try:
        config = load_config()
        return _call(do_inspect_resolve_retirements, config, retirement_store_for(config),
                     datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def prepare_resolve_retirement(kind: str, project_name: str,
                               timeline_name: str | None = None) -> dict[str, Any]:
    """Export and verify a DRP proposal; never removes a Resolve object."""
    try:
        selected = load_config()
        _require_resolve_retirement(selected)
        with RESOLVE_ACCESS_LOCK:
            _, manager, project, _, config, registry, error = _runtime()
            if error:
                return error
            _require_resolve_retirement(config)
            return _call(do_prepare_resolve_retirement, manager, project, config, registry,
                         retirement_store_for(config), kind, project_name, timeline_name,
                         datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def approve_resolve_retirement(retirement_id: str, operator_role: str) -> dict[str, Any]:
    """Approve the immutable fingerprint of one prepared Resolve retirement."""
    try:
        config = load_config()
        _require_resolve_retirement(config)
        return _call(do_approve_resolve_retirement, retirement_store_for(config), retirement_id,
                     operator_role, datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=DESTRUCTIVE_IDEMPOTENT_WRITE)
def execute_resolve_retirement(retirement_id: str) -> dict[str, Any]:
    """Remove exactly one approved target after revalidating its verified DRP archive."""
    try:
        selected = load_config()
        _require_resolve_retirement(selected)
        with RESOLVE_ACCESS_LOCK:
            _, manager, project, _, config, registry, error = _runtime()
            if error:
                return error
            _require_resolve_retirement(config)
            return _call(do_execute_resolve_retirement, manager, project, config, registry,
                         retirement_store_for(config), retirement_id, datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def recover_resolve_retirement(retirement_id: str) -> dict[str, Any]:
    """Import a verified DRP as a new ARPHE_RECOVERY project without overwriting."""
    try:
        selected = load_config()
        _require_resolve_retirement(selected)
        with RESOLVE_ACCESS_LOCK:
            _, manager, _, _, config, _, error = _runtime()
            if error:
                return error
            _require_resolve_retirement(config)
            return _call(do_recover_resolve_retirement, manager, config,
                         retirement_store_for(config), retirement_id, datetime.now(timezone.utc))
    except Exception as exc:
        return _error(exc)


def run() -> None:
    try:
        start_lazy_maintenance(load_config)
    except Exception:
        pass
    mcp.run()
