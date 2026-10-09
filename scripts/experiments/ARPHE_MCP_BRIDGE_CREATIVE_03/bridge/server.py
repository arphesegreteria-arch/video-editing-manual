from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
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
from .audio_provenance import media_fingerprint
from .config import load_config
from .carabellese_analysis import (
    cleanup_candidate_fingerprint,
    derive_pause_candidates,
    load_carabellese_inputs,
    validate_cleanup_candidates,
)
from .carabellese_apply import (
    apply_or_resume_carabellese_cleanup as do_apply_carabellese_cleanup,
    media_source_identity as carabellese_media_source_identity,
)
from .carabellese_checkpoint import (
    export_timeline_checkpoint as do_export_carabellese_checkpoint,
    timeline_content_fingerprint as carabellese_timeline_fingerprint,
)
from .carabellese_contract import (
    carabellese_contract_fingerprint,
    load_carabellese_contract,
    load_carabellese_preferences,
)
from .carabellese_jobs import CarabelleseJobStore, new_carabellese_job
from .carabellese_learning import (
    append_carabellese_outcome as do_append_carabellese_outcome,
    approve_carabellese_profile_proposal as do_approve_carabellese_profile,
    compile_carabellese_profile_proposal as do_compile_carabellese_profile,
    inspect_carabellese_metrics as do_inspect_carabellese_metrics,
)
from .carabellese_markers import mark_carabellese_review as do_mark_carabellese_review
from .carabellese_recovery import (
    close_carabellese_cleanup as do_close_carabellese_cleanup,
    recover_carabellese_cleanup as do_recover_carabellese_cleanup,
)
from .carabellese_review import (
    carabellese_secretary_instructions,
    submit_carabellese_review as do_submit_carabellese_review,
)
from .carabellese_transcription import (
    get_carabellese_transcription_job as do_get_carabellese_transcription_job,
    start_carabellese_transcription as do_start_carabellese_transcription,
)
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
from .editorial_cut_workflow import apply_or_resume_editorial_cuts as do_apply_editorial_cuts
from .editorial_jobs import EditorialJobStore, new_editorial_job
from .editorial_learning import (
    append_local_outcome as do_append_editorial_outcome,
    approve_profile_proposal as do_approve_editorial_profile,
    compile_profile_proposal as do_compile_editorial_profile,
    inspect_local_metrics as do_inspect_editorial_metrics,
    load_effective_preferences,
)
from .editorial_markers import (
    cleanup_verified_markers as do_cleanup_editorial_markers,
    mark_candidates as do_mark_candidates,
    timeline_identity as editorial_timeline_identity,
)
from .editorial_review import secretary_instructions, submit_structured_review as do_submit_editorial_review
from .editorial_selection import load_pinned_transcript, validate_candidate_batch
from .editorial_selection_contract import (
    canonical_digest, load_preference_profile, load_selection_contract,
)
from .format_contract import ResolvedFormat, require_project_playback
from .feature_flags import report as feature_report, require_capability
from .fusion_tools import (MAX_AUTOMATIC_FUSION_FRAMES, add_background, add_text,
                           create_composition, retime)
from .longform_tools import (apply_plan as do_apply_longform_plan,
                             allowed_media,
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
    require_readability_guard as do_require_readability_guard,
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


EDITORIAL_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "editorial_selection_contract.json"
EDITORIAL_SHARED_PROFILE_PATH = Path(__file__).resolve().parents[1] / "editorial_preferences.json"
CARABELLESE_CONTRACT_PATH = Path(__file__).resolve().parents[1] / "carabellese_cleanup_contract.json"
CARABELLESE_SHARED_PROFILE_PATH = Path(__file__).resolve().parents[1] / "carabellese_preferences.json"


def _carabellese_store(config: Any) -> CarabelleseJobStore:
    return CarabelleseJobStore(config.carabellese_jobs_path, config.workstation_id)


def _require_carabellese(config: Any, manager: Any = None, project: Any = None,
                          timeline: Any = None, *, resolve_required: bool = False) -> None:
    if not config.flags.get("CAP_CARABELLESE_CLEANUP", False):
        raise ValidationError("CAP_CARABELLESE_CLEANUP non attiva nella config locale")
    if resolve_required:
        try:
            require_capability("CAP_CARABELLESE_CLEANUP", config, manager, project, timeline)
        except RuntimeError as exc:
            raise ValidationError(str(exc)) from exc


def _carabellese_current_timeline(project: Any, job: Any) -> Any:
    timeline = safe_call(project, "GetCurrentTimeline")
    if (timeline is None or safe_call(timeline, "GetName") != job.timeline_name
            or editorial_timeline_identity(timeline) != job.timeline_identity):
        raise ValidationError("Timeline Carabellese corrente diversa dal job")
    return timeline


def _carabellese_source_fingerprint(timeline: Any, config: Any) -> str:
    video = safe_call(timeline, "GetItemListInTrack", "video", 1) or []
    audio = safe_call(timeline, "GetItemListInTrack", "audio", 1) or []
    if len(video) != 1 or len(audio) != 1:
        raise ValidationError("La preparazione richiede una singola clip sorgente A/V")
    video_media = safe_call(video[0], "GetMediaPoolItem")
    audio_media = safe_call(audio[0], "GetMediaPoolItem")
    video_identity = carabellese_media_source_identity(video_media) \
        if video_media is not None else None
    audio_identity = carabellese_media_source_identity(audio_media) \
        if audio_media is not None else None
    if (video_media is None or audio_media is None or video_identity is None
            or video_identity != audio_identity):
        raise ValidationError("Le clip A/V non appartengono alla stessa sorgente")
    selected = allowed_media(str(safe_call(video_media, "GetClipProperty", "File Path") or ""), config)
    return media_fingerprint(selected)


@mcp.tool(annotations=READ_ONLY)
def inspect_carabellese_cleanup() -> dict[str, Any]:
    """Inspect the fixed Carabellese cleanup contract even while its local gate is disabled."""
    try:
        config = load_config()
        contract = load_carabellese_contract(CARABELLESE_CONTRACT_PATH)
        preferences = load_carabellese_preferences(CARABELLESE_SHARED_PROFILE_PATH)
        return {
            "ok": True, "card_count": 1, "workflow_id": contract.workflow_id,
            "workflow_version": contract.version, "workstation_id": config.workstation_id,
            "capability_enabled": bool(config.flags.get("CAP_CARABELLESE_CLEANUP", False)),
            "frame_rate_mode": contract.frame_rate_mode, "resolution": list(contract.resolution),
            "residual_pause_seconds": preferences.residual_pause_seconds,
            "render_included": False, "cta_included": False, "graphics_included": False,
        }
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def start_carabellese_transcription(media_path: str, expected_source_fingerprint: str,
                                    model: str = "small", language: str = "it") -> dict[str, Any]:
    """Start or resume the isolated managed transcription job for one allowed media source."""
    def operation() -> dict[str, Any]:
        config = load_config(); _require_carabellese(config)
        return dict(do_start_carabellese_transcription(
            config, media_path, expected_source_fingerprint, model=model, language=language))
    return _call(operation)


@mcp.tool(annotations=READ_ONLY)
def get_carabellese_transcription_job(job_id: str) -> dict[str, Any]:
    """Read one workstation-local managed transcription status."""
    return _call(lambda: dict(do_get_carabellese_transcription_job(load_config(), job_id)))


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def prepare_carabellese_cleanup(transcript_path: str, transcript_fingerprint: str,
                                source_fingerprint: str, audio_job_id: str,
                                candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind source, transcript and cleanup proposals, then add owned review markers."""
    def operation() -> dict[str, Any]:
        configured = load_config(); _require_carabellese(configured)
        resolve, manager, project, timeline, config, _, error = _runtime()
        del resolve
        _require_carabellese(config, manager, project, timeline, resolve_required=True)
        if error: return error
        if project is None or timeline is None:
            raise ValidationError("Serve un progetto e una timeline Carabellese aperti")
        with RESOLVE_ACCESS_LOCK:
            contract = load_carabellese_contract(CARABELLESE_CONTRACT_PATH)
            actual_source = _carabellese_source_fingerprint(timeline, config)
            if actual_source != source_fingerprint:
                raise ValidationError("La sorgente della timeline non coincide con quella dichiarata")
            selected_transcript = _allowed_transcript(transcript_path, config)
            inputs = load_carabellese_inputs(
                config, selected_transcript, transcript_fingerprint, audio_job_id, source_fingerprint)
            source = inputs.transcript.get("source")
            duration = source.get("duration_seconds") if isinstance(source, dict) else None
            explicit = validate_cleanup_candidates(candidates, inputs.transcript, contract, float(duration))
            pauses = derive_pause_candidates(inputs.words, inputs.audio.silence_windows, contract)
            combined = tuple(sorted((*explicit, *pauses), key=lambda item: item.start_seconds))
            ids = [item.candidate_id for item in combined]
            if len(ids) != len(set(ids)):
                raise ValidationError("candidate_id Carabellese duplicato")
            if any(current.start_seconds < previous.end_seconds
                   for previous, current in zip(combined, combined[1:])):
                raise ValidationError("Proposte Carabellese sovrapposte")
            if not combined:
                raise ValidationError("Nessuna proposta Carabellese da revisionare")
            payload = tuple(asdict(item) for item in combined)
            store = _carabellese_store(config)
            identity = editorial_timeline_identity(timeline)
            fingerprint = cleanup_candidate_fingerprint(combined)
            owner = store.active_for_timeline(identity)
            if owner is not None:
                if (owner.source_fingerprint == source_fingerprint
                        and owner.transcript_fingerprint == transcript_fingerprint
                        and owner.proposal_fingerprint == fingerprint):
                    return {"ok": True, "action": "prepare_carabellese_cleanup",
                            "carabellese_job_id": owner.carabellese_job_id,
                            "state": owner.state, "candidate_count": len(owner.candidates),
                            "idempotent": True}
                raise ValidationError("La timeline ha già un job Carabellese differente non chiuso")
            job = store.create(new_carabellese_job(
                workstation_id=config.workstation_id, workflow_version=contract.version,
                project_name=str(safe_call(project, "GetName")),
                timeline_name=str(safe_call(timeline, "GetName")), timeline_identity=identity,
                timeline_fingerprint=carabellese_timeline_fingerprint(timeline),
                source_fingerprint=source_fingerprint, transcript_fingerprint=transcript_fingerprint,
                contract_fingerprint=carabellese_contract_fingerprint(contract),
                proposal_fingerprint=fingerprint, candidates=payload))
            marked = do_mark_carabellese_review(timeline, store, job, contract)
            result = {"ok": marked.state == "MARKED", "action": "prepare_carabellese_cleanup",
                      "carabellese_job_id": marked.carabellese_job_id, "state": marked.state,
                      "candidate_count": len(marked.candidates), "idempotent": False}
            if marked.state == "MARKED":
                result["instructions"] = carabellese_secretary_instructions(marked)
            return result
    return _call(operation)


@mcp.tool(annotations=READ_ONLY)
def inspect_carabellese_job(carabellese_job_id: str) -> dict[str, Any]:
    """Return one compact operator card for a workstation-local Carabellese job."""
    try:
        config = load_config()
        job = _carabellese_store(config).get(carabellese_job_id, config.workstation_id)
        result: dict[str, Any] = {
            "ok": True, "card_count": 1, "carabellese_job_id": job.carabellese_job_id,
            "state": job.state, "revision": job.revision, "candidate_count": len(job.candidates),
            "project": job.project_name, "timeline": job.timeline_name,
        }
        if job.state == "MARKED":
            result["instructions"] = carabellese_secretary_instructions(job)
            result["next_action"] = "submit_complete_review"
        elif job.state in {"BLOCKED", "FAILED_RECOVERABLE", "STALE"}:
            result["next_action"] = "technical_recovery"
            result["instruction"] = "Non avviare un nuovo job; chiedi il recupero tecnico di questo ID."
        else:
            result["next_action"] = {"REVIEWED": "apply_cleanup", "CHECKPOINTED": "apply_cleanup",
                "APPLYING": "resume_cleanup", "VERIFIED": "close_cleanup",
                "CLOSED": "complete"}.get(job.state, "wait")
        return result
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def submit_carabellese_review(carabellese_job_id: str,
                              boundary_decisions: list[dict[str, Any]],
                              pause_decision: dict[str, Any],
                              exception_decisions: list[dict[str, Any]],
                              transcript_path: str,
                              transcript_fingerprint: str) -> dict[str, Any]:
    """Bind the complete one-message review and mandatory reasons to the marked job."""
    def operation() -> dict[str, Any]:
        config = load_config(); _require_carabellese(config)
        store = _carabellese_store(config)
        job = store.get(carabellese_job_id, config.workstation_id)
        transcript = load_pinned_transcript(
            _allowed_transcript(transcript_path, config), transcript_fingerprint)
        transcript["_pinned_fingerprint"] = transcript_fingerprint
        reviewed = do_submit_carabellese_review(
            store, job, boundary_decisions, pause_decision, exception_decisions,
            load_carabellese_contract(CARABELLESE_CONTRACT_PATH), transcript=transcript)
        return {"ok": True, "action": "submit_carabellese_review",
                "carabellese_job_id": reviewed.carabellese_job_id, "state": reviewed.state,
                "review_fingerprint": reviewed.review_fingerprint,
                "decision_count": len(reviewed.decisions)}
    return _call(operation)


@mcp.tool(annotations=DESTRUCTIVE_IDEMPOTENT_WRITE)
def apply_carabellese_cleanup(carabellese_job_id: str,
                              expected_review_fingerprint: str) -> dict[str, Any]:
    """Checkpoint, apply and verify the approved cleanup; never renders or adds graphics."""
    def operation() -> dict[str, Any]:
        configured = load_config(); _require_carabellese(configured)
        resolve, manager, project, timeline, config, _, error = _runtime()
        _require_carabellese(config, manager, project, timeline, resolve_required=True)
        if error: return error
        with RESOLVE_ACCESS_LOCK:
            store = _carabellese_store(config)
            job = store.get(carabellese_job_id, config.workstation_id)
            if job.review_fingerprint != expected_review_fingerprint:
                raise ValidationError("Review fingerprint Carabellese stale")
            if job.state == "REVIEWED":
                target = _carabellese_current_timeline(project, job)
                job = do_export_carabellese_checkpoint(
                    resolve, project, target, store, job, config.carabellese_checkpoint_root)
            result = do_apply_carabellese_cleanup(
                resolve, manager, config, store, job.carabellese_job_id,
                expected_review_fingerprint)
            return {"ok": result.state == "VERIFIED", "action": "apply_carabellese_cleanup",
                    "carabellese_job_id": result.carabellese_job_id, "state": result.state}
    return _call(operation)


@mcp.tool(annotations=DESTRUCTIVE_IDEMPOTENT_WRITE)
def recover_carabellese_cleanup(carabellese_job_id: str) -> dict[str, Any]:
    """Restore the verified DRT checkpoint after a recoverable apply failure."""
    def operation() -> dict[str, Any]:
        configured = load_config(); _require_carabellese(configured)
        resolve, manager, project, timeline, config, _, error = _runtime()
        _require_carabellese(config, manager, project, timeline, resolve_required=True)
        if error: return error
        job = do_recover_carabellese_cleanup(
            resolve, manager, config, _carabellese_store(config), carabellese_job_id)
        return {"ok": job.state == "CHECKPOINTED", "action": "recover_carabellese_cleanup",
                "carabellese_job_id": job.carabellese_job_id, "state": job.state}
    return _call(operation)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def close_carabellese_cleanup(carabellese_job_id: str) -> dict[str, Any]:
    """Remove owned markers, retain checkpoint metadata and record redacted local learning."""
    def operation() -> dict[str, Any]:
        configured = load_config(); _require_carabellese(configured)
        _, manager, project, timeline, config, _, error = _runtime()
        _require_carabellese(config, manager, project, timeline, resolve_required=True)
        if error: return error
        store = _carabellese_store(config)
        job = store.get(carabellese_job_id, config.workstation_id)
        if job.state != "CLOSED":
            target = _carabellese_current_timeline(project, job)
            job = do_close_carabellese_cleanup(target, store, job)
        learning = do_append_carabellese_outcome(config, job)
        return {"ok": True, "action": "close_carabellese_cleanup",
                "carabellese_job_id": job.carabellese_job_id, "state": job.state,
                "learning_recorded": learning["recorded"]}
    return _call(operation)


@mcp.tool(annotations=READ_ONLY)
def inspect_carabellese_learning() -> dict[str, Any]:
    """Inspect privacy-safe local aggregates without returning reasons or transcript content."""
    try:
        return {"ok": True, **do_inspect_carabellese_metrics(load_config())}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def compile_carabellese_profile_proposal(minimum_samples: int = 5) -> dict[str, Any]:
    """Compile a redacted local profile proposal without editing the repository profile."""
    def operation() -> dict[str, Any]:
        config = load_config(); _require_carabellese(config)
        proposal = do_compile_carabellese_profile(
            config, load_carabellese_preferences(CARABELLESE_SHARED_PROFILE_PATH), minimum_samples)
        return {"ok": True, "action": "compile_carabellese_profile_proposal", **proposal}
    return _call(operation)


@mcp.tool(annotations=SAFE_WRITE)
def approve_carabellese_profile_proposal(proposal_id: str, operator_role: str,
                                         expected_previous_digest: str) -> dict[str, Any]:
    """Approve a redacted local Carabellese overlay as Alessio or qualified technical staff."""
    def operation() -> dict[str, Any]:
        config = load_config(); _require_carabellese(config)
        return {"action": "approve_carabellese_profile_proposal",
                **do_approve_carabellese_profile(
                    config, proposal_id, operator_role, expected_previous_digest)}
    return _call(operation)


def _editorial_store(config: Any) -> EditorialJobStore:
    return EditorialJobStore(config.editorial_jobs_path, config.workstation_id)


def _require_editorial(config: Any, manager: Any = None, project: Any = None,
                       timeline: Any = None, *, resolve_required: bool = False) -> None:
    if not config.flags.get("CAP_EDITORIAL_SELECTION", False):
        raise ValidationError("CAP_EDITORIAL_SELECTION non attiva nella config locale")
    if resolve_required:
        try:
            require_capability("CAP_EDITORIAL_SELECTION", config, manager, project, timeline)
        except RuntimeError as exc:
            raise ValidationError(str(exc)) from exc


def _require_podcast_reel_fps(project: Any, timeline: Any, required_fps: float) -> None:
    required = Fraction(str(required_fps))
    require_project_playback(project, required)
    required_label = str(required.numerator) if required.denominator == 1 else str(float(required))
    for target, key in (
        (project, "timelineFrameRate"),
        (timeline, "timelineFrameRate"),
        (timeline, "timelinePlaybackFrameRate"),
    ):
        actual = safe_call(target, "GetSetting", key)
        try:
            matches = Fraction(str(actual)) == required
        except (ValueError, ZeroDivisionError):
            matches = False
        if not matches:
            raise PlaybackFpsActionRequired(actual, required_label)


def _allowed_transcript(path_text: str, config: Any) -> Path:
    selected = Path(path_text).expanduser().resolve(strict=True)
    root = config.transcript_root.expanduser().resolve(strict=True)
    if not selected.is_file() or not selected.is_relative_to(root):
        raise ValidationError("Transcript fuori dalla cartella consentita")
    return selected


def _editorial_timeline(project: Any, job: Any) -> Any:
    matches = [
        safe_call(project, "GetTimelineByIndex", index)
        for index in range(1, int(safe_call(project, "GetTimelineCount") or 0) + 1)
    ]
    matches = [item for item in matches if item is not None and safe_call(item, "GetName") == job.timeline_name]
    if len(matches) != 1 or editorial_timeline_identity(matches[0]) != job.timeline_identity:
        raise ValidationError("Timeline sorgente del job non disponibile o diversa")
    return matches[0]


@mcp.tool(annotations=READ_ONLY)
def inspect_editorial_selection() -> dict[str, Any]:
    """Inspect the fixed podcast-Reel contract and effective aggregate preferences."""
    try:
        config = load_config()
        contract = load_selection_contract(EDITORIAL_CONTRACT_PATH)
        shared = load_preference_profile(EDITORIAL_SHARED_PROFILE_PATH)
        effective = load_effective_preferences(config, shared)
        return {
            "ok": True, "workflow_id": contract.workflow_id,
            "max_candidates": contract.max_candidates,
            "max_final_seconds": contract.max_final_seconds,
            "required_project_fps": contract.required_project_fps,
            "cta_duration_seconds": contract.cta_duration_seconds,
            "marker_color": contract.marker_color,
            "capability_enabled": bool(config.flags.get("CAP_EDITORIAL_SELECTION", False)),
            "effective_preferences": effective,
        }
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def prepare_podcast_reel_selection(transcript_path: str, transcript_fingerprint: str,
                                   source_fingerprint: str,
                                   candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate structured candidates and mark the current source timeline in one workflow call."""
    try:
        _, manager, project, timeline, config, _, error = _runtime()
        _require_editorial(config, manager, project, timeline, resolve_required=True)
        if error:
            return error
        if project is None or timeline is None:
            raise ValidationError("Serve un progetto e una timeline sorgente aperti")
        contract = load_selection_contract(EDITORIAL_CONTRACT_PATH)
        _require_podcast_reel_fps(project, timeline, contract.required_project_fps)
        transcript = load_pinned_transcript(
            _allowed_transcript(transcript_path, config), transcript_fingerprint
        )
        fps = Fraction(str(safe_call(timeline, "GetSetting", "timelineFrameRate")))
        resolved = validate_candidate_batch(candidates, transcript=transcript, fps=fps, contract=contract)
        payload = []
        for item in resolved:
            value = asdict(item.proposal)
            value.update({
                "source_in_frame": item.source_in_frame,
                "source_out_frame_exclusive": item.source_out_frame_exclusive,
                "transcript_start_seconds": item.transcript_start_seconds,
                "transcript_end_seconds": item.transcript_end_seconds,
            })
            payload.append(value)
        candidate_fingerprint = canonical_digest({"candidates": payload})
        store = _editorial_store(config)
        identity = editorial_timeline_identity(timeline)
        owner = store.active_for_timeline(identity)
        if owner is not None:
            if (owner.source_fingerprint == source_fingerprint
                    and owner.transcript_fingerprint == transcript_fingerprint
                    and owner.candidate_fingerprint == candidate_fingerprint):
                return {"ok": True, "action": "prepare_podcast_reel_selection",
                        "editorial_job_id": owner.editorial_job_id, "state": owner.state,
                        "candidate_count": len(owner.candidates), "idempotent": True}
            raise ValidationError("La timeline ha già un job editoriale differente non chiuso")
        job = store.create(new_editorial_job(
            workstation_id=config.workstation_id, workflow_version=1,
            project_name=str(safe_call(project, "GetName")),
            timeline_name=str(safe_call(timeline, "GetName")), timeline_identity=identity,
            source_fingerprint=source_fingerprint, transcript_fingerprint=transcript_fingerprint,
            candidate_fingerprint=candidate_fingerprint, candidates=payload,
        ))
        marked = do_mark_candidates(timeline, store, job, contract)
        return {"ok": marked.state == "MARKED", "action": "prepare_podcast_reel_selection",
                "editorial_job_id": marked.editorial_job_id, "state": marked.state,
                "candidate_count": len(marked.candidates), "idempotent": False}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def inspect_editorial_selection_job(editorial_job_id: str) -> dict[str, Any]:
    """Return compact operator or recovery instructions for one local editorial job."""
    try:
        config = load_config()
        job = _editorial_store(config).get(editorial_job_id, config.workstation_id)
        result: dict[str, Any] = {
            "ok": True, "editorial_job_id": job.editorial_job_id, "state": job.state,
            "revision": job.revision, "candidate_count": len(job.candidates),
            "project": job.project_name, "timeline": job.timeline_name,
        }
        if job.state == "MARKED":
            result["instructions"] = secretary_instructions(job)
            result["next_action"] = "submit_complete_review"
        elif job.state in {"BLOCKED", "FAILED_RECOVERABLE", "STALE"}:
            result["next_action"] = "recovery_required"
            result["instructions"] = [
                "Non avviare un nuovo job sulla stessa timeline.",
                "Chiedi ad Alessio o a personale tecnico di ispezionare e riprendere questo job.",
            ]
        else:
            result["next_action"] = {
                "REVIEWED": "apply_selection", "CUT": "resume_selection",
                "VERIFIED": "close_selection", "CLOSED": "complete",
            }.get(job.state, "wait")
        return result
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def submit_podcast_reel_review(editorial_job_id: str, decisions: list[dict[str, Any]],
                               transcript_path: str, transcript_fingerprint: str) -> dict[str, Any]:
    """Bind one complete structured human review to the marked candidate job."""
    try:
        config = load_config()
        _require_editorial(config)
        store = _editorial_store(config)
        job = store.get(editorial_job_id, config.workstation_id)
        transcript = load_pinned_transcript(
            _allowed_transcript(transcript_path, config), transcript_fingerprint
        )
        reviewed = do_submit_editorial_review(
            store, job, decisions, transcript, load_selection_contract(EDITORIAL_CONTRACT_PATH)
        )
        return {"ok": True, "action": "submit_podcast_reel_review",
                "editorial_job_id": reviewed.editorial_job_id, "state": reviewed.state,
                "review_fingerprint": reviewed.review_fingerprint,
                "decision_count": len(reviewed.decisions)}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def apply_podcast_reel_selection(editorial_job_id: str,
                                 expected_review_fingerprint: str,
                                 audio_job_id: str | None = None) -> dict[str, Any]:
    """Apply or resume verified Reel cuts; never starts rendering."""
    try:
        resolve, manager, project, timeline, config, _, error = _runtime()
        _require_editorial(config, manager, project, timeline, resolve_required=True)
        if error:
            return error
        job = do_apply_editorial_cuts(
            resolve, manager, config, _editorial_store(config), editorial_job_id,
            expected_review_fingerprint, audio_job_id=audio_job_id,
        )
        return {"ok": job.state == "VERIFIED", "action": "apply_podcast_reel_selection",
                "editorial_job_id": job.editorial_job_id, "state": job.state,
                "verified_outputs": sum(op.get("status") == "VERIFIED" for op in job.operations)}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=IDEMPOTENT_WRITE)
def close_podcast_reel_selection(editorial_job_id: str) -> dict[str, Any]:
    """Record verified learning, remove only owned markers and close the job."""
    try:
        _, manager, project, timeline, config, _, error = _runtime()
        _require_editorial(config, manager, project, timeline, resolve_required=True)
        if error:
            return error
        store = _editorial_store(config)
        job = store.get(editorial_job_id, config.workstation_id)
        if job.state == "CLOSED":
            return {"ok": True, "action": "close_podcast_reel_selection",
                    "editorial_job_id": job.editorial_job_id, "state": job.state}
        do_append_editorial_outcome(config, job)
        closed = do_cleanup_editorial_markers(_editorial_timeline(project, job), store, job)
        return {"ok": closed.state == "CLOSED", "action": "close_podcast_reel_selection",
                "editorial_job_id": closed.editorial_job_id, "state": closed.state}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=READ_ONLY)
def inspect_editorial_learning() -> dict[str, Any]:
    """Inspect aggregate local metrics without returning reasons, media or transcript content."""
    try:
        return {"ok": True, **do_inspect_editorial_metrics(load_config())}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def compile_editorial_profile_proposal(minimum_samples: int = 5) -> dict[str, Any]:
    """Compile a redacted local proposal; never edits or pushes the repository profile."""
    try:
        config = load_config()
        _require_editorial(config)
        proposal = do_compile_editorial_profile(
            config, load_preference_profile(EDITORIAL_SHARED_PROFILE_PATH),
            minimum_samples=minimum_samples,
        )
        return {"ok": True, "action": "compile_editorial_profile_proposal", **proposal}
    except Exception as exc:
        return _error(exc)


@mcp.tool(annotations=SAFE_WRITE)
def approve_editorial_profile_proposal(proposal_id: str, operator_role: str,
                                       expected_prior_digest: str) -> dict[str, Any]:
    """Approve one redacted profile overlay locally as Alessio; performs no Git action."""
    try:
        config = load_config()
        _require_editorial(config)
        return {"action": "approve_editorial_profile_proposal", **do_approve_editorial_profile(
            config, proposal_id, operator_role, expected_prior_digest
        )}
    except Exception as exc:
        return _error(exc)


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
        do_require_readability_guard(config)
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
        do_require_readability_guard(config)
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
