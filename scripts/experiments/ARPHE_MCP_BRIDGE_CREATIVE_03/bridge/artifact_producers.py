"""Fail-closed registration for protected audio and Colorist evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .artifact_hygiene import validate_managed_path
from .artifact_records import ArtifactRecord, artifact_store_for, sha256_file, load_artifact_policy
from .config import CreativeConfig


def _opaque(label: str, value: object) -> str:
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return f"{label}:{digest}"


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _load_completed(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.get("status") != "COMPLETED":
        raise ValueError("Solo un job audio completato può essere registrato")
    return value


def _check_digest(path: Path, expected: object, label: str) -> str:
    digest = sha256_file(path)
    if not isinstance(expected, str) or digest != expected:
        raise ValueError(f"Fingerprint {label} non corrispondente")
    return digest


def register_completed_audio_job(config: CreativeConfig, manifest_path: Path) -> tuple[ArtifactRecord, ...]:
    """Register a closed audio bundle; never adopts an active or unknown manifest."""
    manifest = validate_managed_path(manifest_path, config.audio_jobs_root.resolve())
    payload = _load_completed(manifest)
    if payload.get("workstation_id") != config.workstation_id:
        raise ValueError("Manifest audio appartenente a un'altra workstation")
    schema = payload.get("schema")
    store = artifact_store_for(config)
    manifest_digest = sha256_file(manifest)
    specs: list[dict[str, Any]] = []
    if schema == "ARPHE_AUDIO_JOB_V2":
        output = validate_managed_path(Path(str(payload.get("output_path") or "")),
                                       config.audio_root.resolve())
        output_digest = _check_digest(output, payload.get("output_sha256"), "output audio")
        source_fingerprint = str(payload.get("source_fingerprint") or "")
        if len(source_fingerprint) != 64:
            raise ValueError("Fingerprint sorgente audio non valido")
        specs.extend((
            {"path": output, "category": "AUDIO_DERIVATIVE", "producer": "audio_worker",
             "managed_root_id": "audio_root",
             "dependencies": ("fingerprint:" + source_fingerprint,
                              "manifest-sha256:" + manifest_digest),
             "review_state": "PENDING", "hold_reasons": ("HUMAN_LISTENING_REVIEW",)},
            {"path": manifest, "category": "AUDIO_MANIFEST", "producer": "audio_worker",
             "managed_root_id": "audio_jobs_root",
             "dependencies": ("fingerprint:" + output_digest,),
             "hold_reasons": ("PROVENANCE_EVIDENCE",)},
        ))
        return store.register_protected_bundle(tuple(specs))
    if schema != "ARPHE_TIMELINE_DIALOGUE_CLEANUP_JOB_V1":
        raise ValueError("Schema job audio non supportato")
    source = validate_managed_path(Path(str(payload.get("source_path") or "")),
                                   config.audio_root.resolve())
    output = validate_managed_path(Path(str(payload.get("processed_path") or "")),
                                   config.audio_root.resolve())
    worker = validate_managed_path(Path(str(payload.get("audio_worker_manifest") or "")),
                                   config.audio_jobs_root.resolve())
    worker_payload = _load_completed(worker)
    if worker_payload.get("workstation_id") != config.workstation_id:
        raise ValueError("Manifest worker appartenente a un'altra workstation")
    source_digest = _check_digest(source, payload.get("source_fingerprint"), "sorgente audio")
    output_digest = _check_digest(output, payload.get("output_fingerprint"), "output audio")
    _check_digest(output, worker_payload.get("output_sha256"), "worker audio")
    timeline_source = payload.get("timeline_source")
    if not isinstance(timeline_source, dict):
        raise ValueError("Dipendenza timeline audio non valida")
    edit_fingerprint = str(timeline_source.get("timeline_edit_fingerprint") or "")
    dependencies = ("fingerprint:" + source_digest, "resolve-edit:" + edit_fingerprint)
    specs.extend((
        {"path": source, "category": "AUDIO_SOURCE", "producer": "timeline_dialogue_cleanup",
         "managed_root_id": "audio_root", "dependencies": ("resolve-edit:" + edit_fingerprint,),
         "hold_reasons": ("RESOLVE_SOURCE_REFERENCE",)},
        {"path": output, "category": "AUDIO_DERIVATIVE", "producer": "timeline_dialogue_cleanup",
         "managed_root_id": "audio_root",
         "dependencies": dependencies + ("manifest-sha256:" + manifest_digest,),
         "review_state": "PENDING", "hold_reasons": ("HUMAN_LISTENING_REVIEW",)},
    ))
    for selected, producer in ((worker, "audio_worker"), (manifest, "timeline_dialogue_cleanup")):
        specs.append({"path": selected, "category": "AUDIO_MANIFEST", "producer": producer,
                      "managed_root_id": "audio_jobs_root",
                      "dependencies": _unique(("fingerprint:" + source_digest,
                                                "fingerprint:" + output_digest)),
                      "hold_reasons": ("PROVENANCE_EVIDENCE",)})
    return store.register_protected_bundle(tuple(specs))


def register_colorist_state(config: CreativeConfig, _job: Any = None) -> ArtifactRecord:
    """Refresh protection from the complete persisted Colorist ledger."""
    state_path = validate_managed_path(config.colorist_jobs_path,
                                       config.artifact_registry_path.parent.resolve())
    payload = json.loads(state_path.read_text(encoding="utf-8-sig"))
    if (not isinstance(payload, dict) or payload.get("workstation_id") != config.workstation_id
            or not isinstance(payload.get("jobs"), dict)):
        raise ValueError("Registry Colorist non valido per questa workstation")
    jobs = [value for value in payload["jobs"].values() if isinstance(value, dict)]
    dependencies: list[str] = []
    holds = ["RESOLVE_VERSION_REFERENCE"]
    review_values: list[str] = []
    for data in jobs:
        dependencies.extend((
            _opaque("resolve-project", data.get("project_name")),
            _opaque("resolve-timeline", data.get("timeline_identity")),
            "plan:" + str(data.get("plan_fingerprint") or ""),
        ))
        drx = data.get("drx_asset_identity")
        if isinstance(drx, dict) and drx.get("sha256"):
            dependencies.append("drx:" + str(drx["sha256"]))
        accepted = data.get("review_accepted")
        review_values.append("ACCEPTED" if accepted is True else "REJECTED" if accepted is False else "PENDING")
        if data.get("preview_restore_versions"):
            holds.append("ACTIVE_COLOR_PREVIEW")
        if str(data.get("state") or "") in {"PREPARED", "APPROVED", "APPLYING"}:
            holds.append("ACTIVE_COLORIST_JOB")
    review_state = "PENDING" if "PENDING" in review_values else (
        "REJECTED" if "REJECTED" in review_values else "ACCEPTED"
    )
    if review_state == "PENDING":
        holds.append("HUMAN_COLOR_REVIEW")
    return artifact_store_for(config).register_protected_path(
        state_path, category="COLORIST_STATE", producer="colorist_job_store",
        managed_root_id="profile_root", dependencies=_unique(tuple(dependencies)),
        review_state=review_state, hold_reasons=_unique(tuple(holds)), refresh=True,
    )


def register_timeline_transcription(config: CreativeConfig, manifest_path: Path) -> tuple[ArtifactRecord, ...]:
    """Register only new, UUID-bound timeline extractions; never adopts legacy media.

    Active/failed extraction retains its own hold. Successful transcript evidence releases
    only that hold; KEEP and external dependencies survive repeated polls.
    """
    manifest = validate_managed_path(manifest_path, config.transcript_root.resolve())
    payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    from .transcription_worker import JOB_SCHEMA
    if (not isinstance(payload, dict) or payload.get("schema") != JOB_SCHEMA
            or payload.get("workstation_id") != config.workstation_id):
        raise ValueError("Invalid timeline transcription owner/schema")
    source = payload.get("timeline_source")
    if not isinstance(source, dict) or not source.get("project_id"):
        raise ValueError("Legacy transcription requires project UUID binding; no automatic adoption")
    job_id = str(payload.get("job_id") or "")
    import re
    if not re.fullmatch(r"timeline_tx_[0-9a-f]{16}", job_id):
        raise ValueError("Invalid timeline transcription identity")
    expected_manifest = config.transcript_root.resolve() / '.timeline_jobs' / config.workstation_id / (job_id+'.json')
    if manifest != expected_manifest:
        raise ValueError("Timeline manifest path mismatch")
    wav = validate_managed_path(Path(str(payload.get("source_path") or "")), config.audio_root.resolve())
    extraction_root = config.audio_root.resolve() / 'timeline-transcriptions' / config.workstation_id
    if wav.parent != extraction_root or wav.suffix.lower() != '.wav':
        raise ValueError("Timeline extraction path mismatch")
    store = artifact_store_for(config)
    project_id = store.bind_project(source['project_id'])
    records = [store.register_produced_path(
        manifest, project_id=project_id, category='AUDIO_MANIFEST', protection_class='PROTECTED',
        producer='timeline_transcription', managed_root_id='transcript_root',
        hold_reasons=('PROVENANCE_EVIDENCE',))]
    completed = payload.get('status') == 'COMPLETED'
    previous = next((r for r in store.records() if r.path == str(wav)), None)
    output = None
    if completed:
        output = validate_managed_path(Path(str(payload.get('output_path') or '')), config.transcript_root.resolve())
        if output.parent != config.transcript_root.resolve() / config.workstation_id or output.suffix.lower() != '.json':
            raise ValueError('Timeline transcript path mismatch')
        if not wav.exists() and previous is not None and previous.state in {'QUARANTINED','PURGED'}:
            if (previous.sha256 != payload.get('source_fingerprint') or previous.project_id != project_id
                    or previous.producer != 'timeline_transcription'
                    or previous.category != 'TRANSCRIPTION_EXTRACTION'):
                raise ValueError('Retired extraction provenance mismatch')
        else:
            _check_digest(wav, payload.get('source_fingerprint'), 'timeline extraction')
        _check_digest(output, payload.get('transcript_fingerprint'), 'timeline transcript')
        transcript = json.loads(output.read_text(encoding='utf-8-sig'))
        if transcript.get('status') != 'complete' or transcript.get('timeline_source') != source:
            raise ValueError('Timeline transcript provenance mismatch')
        records.append(store.register_produced_path(
            output, project_id=project_id, category='RESOLVE_REFERENCE', protection_class='PROTECTED',
            producer='timeline_transcription', managed_root_id='transcript_root',
            hold_reasons=('TRANSCRIPT_ORIGINAL',)))
    # A render may still be appending to this file. The manifest/global producer
    # blocker protects it until final WAV evidence exists; never freeze partial bytes.
    if wav.is_file() and payload.get('source_fingerprint'):
        _check_digest(wav, payload.get('source_fingerprint'), 'timeline extraction')
        record = store.register_produced_path(
            wav, project_id=project_id, category='TRANSCRIPTION_EXTRACTION', protection_class='DISPOSABLE',
            producer='timeline_transcription', managed_root_id='audio_root',
            hold_reasons=() if completed else ('TRANSCRIPTION_ACTIVE_OR_FAILED',))
        if completed:
            with store.registration_guard():
                record = next(r for r in store.records() if r.artifact_id == record.artifact_id)
                # A changed extraction cannot be released by an old completion manifest.
                if record.sha256 != payload.get('source_fingerprint'):
                    raise ValueError('Registered extraction changed')
                now = datetime.now(timezone.utc)
                terminal = record.terminal_observed_at or now
                eligible = record.eligible_at or terminal + timedelta(seconds=load_artifact_policy(
                    config.artifact_policy_path).rules['TRANSCRIPTION_EXTRACTION'].active_seconds)
                updated = replace(record, hold_reasons=tuple(h for h in record.hold_reasons
                                  if h != 'TRANSCRIPTION_ACTIVE_OR_FAILED'),
                                  terminal_observed_at=terminal, eligible_at=eligible)
                if updated != record:
                    store.replace(updated)
                record = updated
        records.append(record)
    elif previous is not None:
        records.append(previous)
    return tuple(records)
