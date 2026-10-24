"""Fail-closed registration for protected audio and Colorist evidence."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact_hygiene import validate_managed_path
from .artifact_records import ArtifactRecord, artifact_store_for, sha256_file
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
    schema = payload.get("schema")
    store = artifact_store_for(config)
    records: list[ArtifactRecord] = []
    if schema == "ARPHE_AUDIO_JOB_V2":
        output = validate_managed_path(Path(str(payload.get("output_path") or "")),
                                       config.audio_root.resolve())
        output_digest = _check_digest(output, payload.get("output_sha256"), "output audio")
        source_fingerprint = str(payload.get("source_fingerprint") or "")
        if len(source_fingerprint) != 64:
            raise ValueError("Fingerprint sorgente audio non valido")
        records.append(store.register_protected_path(
            output, category="AUDIO_DERIVATIVE", producer="audio_worker",
            managed_root_id="audio_root",
            dependencies=("fingerprint:" + source_fingerprint,), review_state="PENDING",
            hold_reasons=("HUMAN_LISTENING_REVIEW",),
        ))
        records.append(store.register_protected_path(
            manifest, category="AUDIO_MANIFEST", producer="audio_worker",
            managed_root_id="audio_jobs_root",
            dependencies=("fingerprint:" + output_digest,),
            hold_reasons=("PROVENANCE_EVIDENCE",),
        ))
        return tuple(records)
    if schema != "ARPHE_TIMELINE_DIALOGUE_CLEANUP_JOB_V1":
        raise ValueError("Schema job audio non supportato")
    source = validate_managed_path(Path(str(payload.get("source_path") or "")),
                                   config.audio_root.resolve())
    output = validate_managed_path(Path(str(payload.get("processed_path") or "")),
                                   config.audio_root.resolve())
    worker = validate_managed_path(Path(str(payload.get("audio_worker_manifest") or "")),
                                   config.audio_jobs_root.resolve())
    worker_payload = _load_completed(worker)
    source_digest = _check_digest(source, payload.get("source_fingerprint"), "sorgente audio")
    output_digest = _check_digest(output, payload.get("output_fingerprint"), "output audio")
    _check_digest(output, worker_payload.get("output_sha256"), "worker audio")
    timeline_source = payload.get("timeline_source")
    if not isinstance(timeline_source, dict):
        raise ValueError("Dipendenza timeline audio non valida")
    edit_fingerprint = str(timeline_source.get("timeline_edit_fingerprint") or "")
    dependencies = ("fingerprint:" + source_digest, "resolve-edit:" + edit_fingerprint)
    records.append(store.register_protected_path(
        source, category="AUDIO_SOURCE", producer="timeline_dialogue_cleanup",
        managed_root_id="audio_root", dependencies=("resolve-edit:" + edit_fingerprint,),
        hold_reasons=("RESOLVE_SOURCE_REFERENCE",),
    ))
    records.append(store.register_protected_path(
        output, category="AUDIO_DERIVATIVE", producer="timeline_dialogue_cleanup",
        managed_root_id="audio_root", dependencies=dependencies,
        review_state="PENDING", hold_reasons=("HUMAN_LISTENING_REVIEW",),
    ))
    for selected, producer in ((worker, "audio_worker"), (manifest, "timeline_dialogue_cleanup")):
        records.append(store.register_protected_path(
            selected, category="AUDIO_MANIFEST", producer=producer,
            managed_root_id="audio_jobs_root",
            dependencies=_unique(("fingerprint:" + source_digest,
                                  "fingerprint:" + output_digest)),
            hold_reasons=("PROVENANCE_EVIDENCE",),
        ))
    return tuple(records)


def register_colorist_state(config: CreativeConfig, job: Any) -> ArtifactRecord:
    """Refresh the protected Colorist ledger after its own atomic save."""
    state_path = validate_managed_path(config.colorist_jobs_path,
                                       config.artifact_registry_path.parent.resolve())
    data = asdict(job) if hasattr(job, "__dataclass_fields__") else dict(job)
    state = str(data.get("state") or "")
    accepted = data.get("review_accepted")
    review_state = "ACCEPTED" if accepted is True else "REJECTED" if accepted is False else "PENDING"
    dependencies = [
        _opaque("resolve-project", data.get("project_name")),
        _opaque("resolve-timeline", data.get("timeline_identity")),
        "plan:" + str(data.get("plan_fingerprint") or ""),
    ]
    drx = data.get("drx_asset_identity")
    if isinstance(drx, dict) and drx.get("sha256"):
        dependencies.append("drx:" + str(drx["sha256"]))
    holds = ["RESOLVE_VERSION_REFERENCE"]
    if review_state == "PENDING":
        holds.append("HUMAN_COLOR_REVIEW")
    if data.get("preview_restore_versions"):
        holds.append("ACTIVE_COLOR_PREVIEW")
    if state in {"PREPARED", "APPROVED", "APPLYING"}:
        holds.append("ACTIVE_COLORIST_JOB")
    return artifact_store_for(config).register_protected_path(
        state_path, category="COLORIST_STATE", producer="colorist_job_store",
        managed_root_id="profile_root", dependencies=tuple(dependencies),
        review_state=review_state, hold_reasons=tuple(holds), refresh=True,
    )
