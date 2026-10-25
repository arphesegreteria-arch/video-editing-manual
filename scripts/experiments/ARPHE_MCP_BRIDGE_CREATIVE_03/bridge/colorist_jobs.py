from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from .colorist_model import cdl_digest, plan_fingerprint
from .safety import ValidationError


SCHEMA = "ARPHE_COLORIST_JOBS_V1"
PLAN_V1 = "ARPHE_COLORIST_PLAN_V1"
PLAN_V2 = "ARPHE_COLORIST_PLAN_V2"
JOB_ID = re.compile(r"^colorist_[0-9a-f]{16}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
STATES = {"PREPARED", "APPROVED", "APPLYING", "FAILED_RECOVERABLE", "FAILED_MANUAL",
          "APPLIED", "ACCEPTED", "REJECTED", "CANCELLED"}
ROLES = {"ALESSIO", "COLORIST"}
_STORE_WRITE_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ColoristJob:
    colorist_job_id: str
    workstation_id: str
    state: str
    revision: int
    project_name: str
    timeline_name: str
    timeline_identity: str
    clip_ids: tuple[str, ...]
    reference_clip_id: str | None
    adjustments: dict[str, object]
    preset_name: str
    drx_preset_name: str | None
    drx_asset_identity: dict[str, object] | None
    before_versions: dict[str, dict[str, object]]
    cdl: dict[str, object]
    plan_schema: str
    matching_strategy: str
    adjustments_by_clip: dict[str, dict[str, object]]
    observations_by_clip: dict[str, dict[str, object]]
    cdl_by_clip: dict[str, dict[str, object]]
    plan_fingerprint: str
    operator_role: str | None
    apply_evidence: tuple[dict[str, object], ...]
    failure_evidence: dict[str, object] | None
    cancellation_evidence: dict[str, object] | None
    preview_restore_versions: dict[str, str]
    review_accepted: bool | None
    state_timestamps: dict[str, str]


def _plan_payload_v1(*, workstation_id: str, project_name: str, timeline_name: str,
                     timeline_identity: str, clip_ids: Sequence[str], reference_clip_id: str | None,
                     adjustments: Mapping[str, object], preset_name: str, drx_preset_name: str | None,
                     drx_asset_identity: Mapping[str, object] | None,
                     before_versions: Mapping[str, Mapping[str, object]],
                     cdl: Mapping[str, object]) -> dict[str, Any]:
    return {
        "workstation_id": workstation_id,
        "project_name": project_name,
        "timeline_name": timeline_name,
        "timeline_identity": timeline_identity,
        "clip_ids": list(clip_ids),
        "reference_clip_id": reference_clip_id,
        "adjustments": dict(adjustments),
        "preset_name": preset_name,
        "drx_preset_name": drx_preset_name,
        "drx_asset_identity": None if drx_asset_identity is None else dict(drx_asset_identity),
        "before_versions": {key: dict(value) for key, value in before_versions.items()},
        "cdl": dict(cdl),
    }


def _plan_payload_v2(*, workstation_id: str, project_name: str, timeline_name: str,
                     timeline_identity: str, clip_ids: Sequence[str], reference_clip_id: str | None,
                     preset_name: str, drx_preset_name: str | None,
                     drx_asset_identity: Mapping[str, object] | None,
                     before_versions: Mapping[str, Mapping[str, object]],
                     matching_strategy: str,
                     adjustments_by_clip: Mapping[str, Mapping[str, object]],
                     observations_by_clip: Mapping[str, Mapping[str, object]],
                     cdl_by_clip: Mapping[str, Mapping[str, object]]) -> dict[str, Any]:
    return {
        "plan_schema": PLAN_V2,
        "workstation_id": workstation_id,
        "project_name": project_name,
        "timeline_name": timeline_name,
        "timeline_identity": timeline_identity,
        "clip_ids": list(clip_ids),
        "reference_clip_id": reference_clip_id,
        "preset_name": preset_name,
        "drx_preset_name": drx_preset_name,
        "drx_asset_identity": None if drx_asset_identity is None else dict(drx_asset_identity),
        "before_versions": {key: dict(value) for key, value in before_versions.items()},
        "matching_strategy": matching_strategy,
        "adjustments_by_clip": {key: dict(value) for key, value in adjustments_by_clip.items()},
        "observations_by_clip": {key: dict(value) for key, value in observations_by_clip.items()},
        "cdl_by_clip": {key: dict(value) for key, value in cdl_by_clip.items()},
    }


def new_colorist_job(**kwargs: Any) -> ColoristJob:
    plan_schema = kwargs.pop("plan_schema", PLAN_V1)
    if plan_schema == PLAN_V2:
        matching_strategy = kwargs.pop("matching_strategy")
        adjustments_by_clip = kwargs.pop("adjustments_by_clip")
        observations_by_clip = kwargs.pop("observations_by_clip")
        cdl_by_clip = kwargs.pop("cdl_by_clip")
        legacy_adjustments = dict(kwargs.pop("adjustments"))
        legacy_cdl = dict(kwargs.pop("cdl"))
        if legacy_adjustments or legacy_cdl:
            raise ValidationError("I campi globali V1 devono essere vuoti nei piani V2")
        payload = _plan_payload_v2(
            **kwargs, matching_strategy=matching_strategy,
            adjustments_by_clip=adjustments_by_clip,
            observations_by_clip=observations_by_clip, cdl_by_clip=cdl_by_clip,
        )
    elif plan_schema == PLAN_V1:
        payload = _plan_payload_v1(**kwargs)
        legacy_adjustments = dict(payload["adjustments"])
        legacy_cdl = dict(payload["cdl"])
        matching_strategy = ("LEGACY_COPY_REFERENCE" if payload["reference_clip_id"] is not None
                             else "UNIFORM_MANUAL")
        adjustments_by_clip = {
            str(clip_id): dict(legacy_adjustments) for clip_id in payload["clip_ids"]
        }
        observations_by_clip = {}
        cdl_by_clip = {str(clip_id): dict(legacy_cdl) for clip_id in payload["clip_ids"]}
    else:
        raise ValidationError("Schema piano Colorist non supportato")
    created = _now()
    job = ColoristJob(
        colorist_job_id="colorist_" + uuid4().hex[:16],
        workstation_id=str(payload["workstation_id"]),
        state="PREPARED",
        revision=0,
        project_name=str(payload["project_name"]),
        timeline_name=str(payload["timeline_name"]),
        timeline_identity=str(payload["timeline_identity"]),
        clip_ids=tuple(str(value) for value in payload["clip_ids"]),
        reference_clip_id=None if payload["reference_clip_id"] is None else str(payload["reference_clip_id"]),
        adjustments=legacy_adjustments,
        preset_name=str(payload["preset_name"]),
        drx_preset_name=None if payload["drx_preset_name"] is None else str(payload["drx_preset_name"]),
        drx_asset_identity=(None if payload["drx_asset_identity"] is None
                            else dict(payload["drx_asset_identity"])),
        before_versions={str(key): dict(value) for key, value in payload["before_versions"].items()},
        cdl=legacy_cdl,
        plan_schema=plan_schema,
        matching_strategy=str(matching_strategy),
        adjustments_by_clip={str(key): dict(value) for key, value in adjustments_by_clip.items()},
        observations_by_clip={str(key): dict(value) for key, value in observations_by_clip.items()},
        cdl_by_clip={str(key): dict(value) for key, value in cdl_by_clip.items()},
        plan_fingerprint=plan_fingerprint(payload),
        operator_role=None,
        apply_evidence=(),
        failure_evidence=None,
        cancellation_evidence=None,
        preview_restore_versions={},
        review_accepted=None,
        state_timestamps={"PREPARED": created},
    )
    _validate(job)
    return job


def _validate(job: ColoristJob) -> None:
    if not JOB_ID.fullmatch(job.colorist_job_id):
        raise ValidationError("colorist_job_id non valido")
    if not re.fullmatch(r"PC_[A-Z0-9_]{2,48}", job.workstation_id):
        raise ValidationError("workstation Colorist non valido")
    if job.state not in STATES or isinstance(job.revision, bool) or job.revision < 0:
        raise ValidationError("Stato o revision Colorist non validi")
    if not all(isinstance(value, str) and value.strip() for value in (
        job.project_name, job.timeline_name, job.timeline_identity, job.preset_name
    )):
        raise ValidationError("Contesto Colorist incompleto")
    if not job.clip_ids or len(set(job.clip_ids)) != len(job.clip_ids) or any(not value for value in job.clip_ids):
        raise ValidationError("clip_ids Colorist vuoti o duplicati")
    if job.reference_clip_id is not None and job.reference_clip_id not in job.clip_ids:
        raise ValidationError("reference_clip_id deve appartenere ai target")
    if set(job.before_versions) != set(job.clip_ids):
        raise ValidationError("before_versions deve coprire esattamente i target")
    for version in job.before_versions.values():
        if not isinstance(version, dict) or set(version) != {"versionName", "versionType"}:
            raise ValidationError("Versione colore iniziale malformata")
        if not isinstance(version["versionName"], str) or not version["versionName"] or version["versionType"] != 0:
            raise ValidationError("Solo versioni colore locali valide sono supportate")
    if job.plan_schema not in {PLAN_V1, PLAN_V2}:
        raise ValidationError("Schema piano Colorist non supportato")
    targets = set(job.clip_ids)
    if set(job.adjustments_by_clip) != targets or set(job.cdl_by_clip) != targets:
        raise ValidationError("Correzioni e CDL devono coprire esattamente i target")
    if any(not isinstance(value, dict) for value in job.adjustments_by_clip.values()):
        raise ValidationError("Correzioni per clip malformate")
    required_cdl = {"NodeIndex", "Slope", "Offset", "Power", "Saturation"}
    for cdl in job.cdl_by_clip.values():
        if not isinstance(cdl, dict) or set(cdl) != required_cdl:
            raise ValidationError("CDL per clip malformato")
        try:
            cdl_digest(cdl)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"CDL per clip malformato: {exc}") from exc
    if job.plan_schema == PLAN_V1:
        expected_strategy = ("LEGACY_COPY_REFERENCE" if job.reference_clip_id is not None
                             else "UNIFORM_MANUAL")
        if (job.matching_strategy != expected_strategy or job.observations_by_clip
                or any(value != job.adjustments for value in job.adjustments_by_clip.values())
                or any(value != job.cdl for value in job.cdl_by_clip.values())):
            raise ValidationError("Compatibilità piano Colorist V1 non valida")
    else:
        if job.adjustments or job.cdl:
            raise ValidationError("I campi globali V1 devono essere vuoti nei piani V2")
        if job.matching_strategy == "UNIFORM_MANUAL":
            if job.observations_by_clip:
                raise ValidationError("Un piano uniforme non accetta osservazioni per clip")
        elif job.matching_strategy == "PER_CLIP_MEASURED":
            if set(job.observations_by_clip) != targets:
                raise ValidationError("Le osservazioni devono coprire esattamente i target")
        else:
            raise ValidationError("Strategia matching Colorist V2 non consentita")
    if not HEX64.fullmatch(job.plan_fingerprint):
        raise ValidationError("plan_fingerprint non valido")
    if (job.drx_preset_name is None) != (job.drx_asset_identity is None):
        raise ValidationError("Preset DRX e identità asset devono essere presenti insieme")
    if job.drx_asset_identity is not None:
        identity = job.drx_asset_identity
        if set(identity) != {"relative_path", "size", "sha256"}:
            raise ValidationError("Identità asset DRX malformata")
        if (not isinstance(identity["relative_path"], str) or not identity["relative_path"]
                or Path(identity["relative_path"]).is_absolute()
                or ".." in Path(identity["relative_path"]).parts
                or isinstance(identity["size"], bool) or not isinstance(identity["size"], int)
                or identity["size"] < 0 or not isinstance(identity["sha256"], str)
                or not HEX64.fullmatch(identity["sha256"])):
            raise ValidationError("Identità asset DRX non valida")
    if job.state == "PREPARED" and job.operator_role is not None:
        raise ValidationError("Un piano PREPARED non può essere approvato")
    if job.state != "PREPARED" and job.operator_role not in ROLES:
        raise ValidationError("Piano Colorist privo di approvazione umana")
    if job.state in {"APPLIED", "ACCEPTED", "REJECTED"}:
        _validate_apply_evidence(job)
    elif job.apply_evidence:
        raise ValidationError("Evidenza apply presente prima del completamento")
    if job.state in {"FAILED_RECOVERABLE", "FAILED_MANUAL"}:
        if not isinstance(job.failure_evidence, dict) or not job.failure_evidence:
            raise ValidationError("Fallimento Colorist privo di evidenza")
        expected_recoverable = job.state == "FAILED_RECOVERABLE"
        if job.failure_evidence.get("recoverable") is not expected_recoverable:
            raise ValidationError("Stato di recupero Colorist incoerente con l'evidenza")
    elif job.failure_evidence is not None:
        raise ValidationError("Evidenza di fallimento incoerente")
    if job.state == "CANCELLED":
        evidence = job.cancellation_evidence
        if not isinstance(evidence, dict) or set(evidence) != {
            "expected_revision", "plan_fingerprint", "reason"
        }:
            raise ValidationError("Evidenza annullamento Colorist non valida")
        reason = evidence.get("reason")
        expected_revision = evidence.get("expected_revision")
        if (not isinstance(reason, str) or not reason or len(reason) > 500
                or not all(character.isprintable() for character in reason)
                or isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
                or expected_revision < 1
                or evidence.get("plan_fingerprint") != job.plan_fingerprint
                or "CANCELLED" not in job.state_timestamps):
            raise ValidationError("Evidenza annullamento Colorist non valida")
    elif job.cancellation_evidence is not None:
        raise ValidationError("Evidenza annullamento presente su piano non annullato")
    if set(job.preview_restore_versions) - set(job.clip_ids):
        raise ValidationError("Tracking preview fuori dal piano Colorist")
    if job.preview_restore_versions and job.state not in {"APPLIED", "ACCEPTED", "REJECTED"}:
        raise ValidationError("Tracking preview richiede apply completato")
    if job.state in {"ACCEPTED", "REJECTED"} and job.review_accepted != (job.state == "ACCEPTED"):
        raise ValidationError("Decisione review incoerente")
    if "PREPARED" not in job.state_timestamps:
        raise ValidationError("Cronologia Colorist incompleta")


def after_version_names(job: ColoristJob) -> dict[str, str]:
    token = job.colorist_job_id.split("_", 1)[1].upper()
    return {clip_id: f"ARPHE_COLOR_{token}_{index:02d}"
            for index, clip_id in enumerate(job.clip_ids, start=1)}


def _validate_apply_evidence(job: ColoristJob) -> None:
    expected_names = after_version_names(job)
    if len(job.apply_evidence) != len(job.clip_ids):
        raise ValidationError("Evidenza apply deve avere un record per target")
    seen: set[str] = set()
    required = {"clip_id", "before_version", "after_version", "reference_clip_id",
                "cdl_applied_directly", "drx_preset_name"}
    if job.plan_schema == PLAN_V2:
        required |= {"matching_strategy", "cdl_sha256"}
    for item in job.apply_evidence:
        if set(item) != required:
            raise ValidationError("Record evidenza apply malformato")
        clip_id = item.get("clip_id")
        if not isinstance(clip_id, str) or clip_id not in expected_names or clip_id in seen:
            raise ValidationError("clip_id evidenza apply non valido o duplicato")
        seen.add(clip_id)
        direct_expected = (True if job.plan_schema == PLAN_V2
                           else job.reference_clip_id is None or clip_id == job.reference_clip_id)
        if (item.get("before_version") != job.before_versions[clip_id]["versionName"]
                or item.get("after_version") != expected_names[clip_id]
                or item.get("reference_clip_id") != job.reference_clip_id
                or item.get("drx_preset_name") != job.drx_preset_name
                or item.get("cdl_applied_directly") is not direct_expected):
            raise ValidationError("Evidenza apply non coerente con il piano")
        if job.plan_schema == PLAN_V2 and (
            item.get("matching_strategy") != job.matching_strategy
            or item.get("cdl_sha256") != cdl_digest(job.cdl_by_clip[clip_id])
        ):
            raise ValidationError("Evidenza CDL non coerente con il piano")


def approve_colorist_job(job: ColoristJob, expected_fingerprint: str, operator_role: str) -> ColoristJob:
    _validate(job)
    if job.state != "PREPARED":
        raise ValidationError("Solo un piano PREPARED può essere approvato")
    if expected_fingerprint != job.plan_fingerprint:
        raise ValidationError("plan fingerprint Colorist non corrispondente")
    role = str(operator_role).upper()
    if role not in ROLES:
        raise ValidationError("ruolo approvatore Colorist non consentito")
    timestamps = {**job.state_timestamps, "APPROVED": _now()}
    approved = replace(job, state="APPROVED", operator_role=role, state_timestamps=timestamps)
    _validate(approved)
    return approved


def record_colorist_apply_started(job: ColoristJob) -> ColoristJob:
    _validate(job)
    if job.state != "APPROVED":
        raise ValidationError("Avvio apply Colorist richiede piano APPROVED")
    if job.plan_schema == PLAN_V1:
        raise ValidationError("Un piano Colorist V1 non può essere applicato: preparare un piano V2")
    applying = replace(job, state="APPLYING",
                       state_timestamps={**job.state_timestamps, "APPLYING": _now()})
    _validate(applying)
    return applying


def record_colorist_apply(job: ColoristJob, evidence: Sequence[Mapping[str, object]]) -> ColoristJob:
    _validate(job)
    if job.state != "APPLYING":
        raise ValidationError("Completamento apply Colorist richiede piano APPLYING")
    applied = replace(job, state="APPLIED", apply_evidence=tuple(dict(item) for item in evidence),
                      state_timestamps={**job.state_timestamps, "APPLIED": _now()})
    _validate(applied)
    return applied


def record_colorist_apply_failure(job: ColoristJob, evidence: Mapping[str, object]) -> ColoristJob:
    _validate(job)
    if job.state != "APPLYING":
        raise ValidationError("Registrazione fallimento Colorist richiede piano APPLYING")
    state = "FAILED_RECOVERABLE" if evidence.get("recoverable") is True else "FAILED_MANUAL"
    failed = replace(job, state=state, failure_evidence=dict(evidence),
                     state_timestamps={**job.state_timestamps, state: _now()})
    _validate(failed)
    return failed


def record_colorist_preview_start(job: ColoristJob, clip_id: str, restore_version: str) -> ColoristJob:
    _validate(job)
    if job.state not in {"APPLIED", "ACCEPTED", "REJECTED"} or clip_id not in job.clip_ids:
        raise ValidationError("Preview Colorist non consentita")
    if clip_id in job.preview_restore_versions:
        return job
    if not isinstance(restore_version, str) or not restore_version:
        raise ValidationError("Versione di ripristino preview non valida")
    updated = replace(job, preview_restore_versions={**job.preview_restore_versions,
                                                     clip_id: restore_version})
    _validate(updated)
    return updated


def record_colorist_preview_restored(job: ColoristJob, clip_id: str) -> ColoristJob:
    _validate(job)
    if clip_id not in job.preview_restore_versions:
        raise ValidationError("Nessuna preview Colorist attiva per il clip")
    remaining = dict(job.preview_restore_versions)
    remaining.pop(clip_id)
    updated = replace(job, preview_restore_versions=remaining)
    _validate(updated)
    return updated


def record_colorist_review(job: ColoristJob, accepted: bool, operator_role: str) -> ColoristJob:
    _validate(job)
    if job.state != "APPLIED":
        raise ValidationError("Review Colorist richiede piano APPLIED")
    if job.preview_restore_versions:
        raise ValidationError("Ripristinare tutte le preview Colorist prima della review")
    if not isinstance(accepted, bool):
        raise ValidationError("accepted deve essere booleano")
    role = str(operator_role).upper()
    if role not in ROLES:
        raise ValidationError("ruolo review Colorist non consentito")
    state = "ACCEPTED" if accepted else "REJECTED"
    reviewed = replace(job, state=state, operator_role=role, review_accepted=accepted,
                       state_timestamps={**job.state_timestamps, state: _now()})
    _validate(reviewed)
    return reviewed


def _from_payload(raw: object) -> ColoristJob:
    fields = set(ColoristJob.__dataclass_fields__)
    compatibility_fields = {
        "plan_schema", "matching_strategy", "adjustments_by_clip",
        "observations_by_clip", "cdl_by_clip",
    }
    v1_fields = fields - compatibility_fields
    allowed = {frozenset(fields), frozenset(fields - {"cancellation_evidence"}),
               frozenset(v1_fields), frozenset(v1_fields - {"cancellation_evidence"})}
    if not isinstance(raw, dict) or frozenset(raw) not in allowed:
        raise ValidationError("Record Colorist malformato")
    try:
        clip_ids = tuple(str(value) for value in raw["clip_ids"])
        reference_clip_id = (None if raw["reference_clip_id"] is None
                             else str(raw["reference_clip_id"]))
        adjustments = dict(raw["adjustments"])
        cdl = {str(key): value for key, value in raw["cdl"].items()}
        if "plan_schema" in raw:
            plan_schema = str(raw["plan_schema"])
            matching_strategy = str(raw["matching_strategy"])
            adjustments_by_clip = {
                str(key): dict(value) for key, value in raw["adjustments_by_clip"].items()
            }
            observations_by_clip = {
                str(key): dict(value) for key, value in raw["observations_by_clip"].items()
            }
            cdl_by_clip = {str(key): dict(value) for key, value in raw["cdl_by_clip"].items()}
        else:
            plan_schema = PLAN_V1
            matching_strategy = ("LEGACY_COPY_REFERENCE" if reference_clip_id is not None
                                 else "UNIFORM_MANUAL")
            adjustments_by_clip = {clip_id: dict(adjustments) for clip_id in clip_ids}
            observations_by_clip = {}
            cdl_by_clip = {clip_id: dict(cdl) for clip_id in clip_ids}
        job = ColoristJob(
            colorist_job_id=str(raw["colorist_job_id"]), workstation_id=str(raw["workstation_id"]),
            state=str(raw["state"]), revision=int(raw["revision"]), project_name=str(raw["project_name"]),
            timeline_name=str(raw["timeline_name"]), timeline_identity=str(raw["timeline_identity"]),
            clip_ids=clip_ids, reference_clip_id=reference_clip_id,
            adjustments=adjustments, preset_name=str(raw["preset_name"]),
            drx_preset_name=None if raw["drx_preset_name"] is None else str(raw["drx_preset_name"]),
            drx_asset_identity=(None if raw["drx_asset_identity"] is None
                                else dict(raw["drx_asset_identity"])),
            before_versions={str(key): dict(value) for key, value in raw["before_versions"].items()},
            cdl=cdl, plan_schema=plan_schema, matching_strategy=matching_strategy,
            adjustments_by_clip=adjustments_by_clip,
            observations_by_clip=observations_by_clip, cdl_by_clip=cdl_by_clip,
            plan_fingerprint=str(raw["plan_fingerprint"]),
            operator_role=None if raw["operator_role"] is None else str(raw["operator_role"]),
            apply_evidence=tuple(dict(item) for item in raw["apply_evidence"]),
            failure_evidence=(None if raw["failure_evidence"] is None else dict(raw["failure_evidence"])),
            cancellation_evidence=(None if raw.get("cancellation_evidence") is None
                                   else dict(raw["cancellation_evidence"])),
            preview_restore_versions={str(key): str(value)
                                      for key, value in raw["preview_restore_versions"].items()},
            review_accepted=raw["review_accepted"],
            state_timestamps={str(key): str(value) for key, value in raw["state_timestamps"].items()},
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(f"Record Colorist malformato: {exc}") from exc
    _validate(job)
    common = dict(
        workstation_id=job.workstation_id, project_name=job.project_name,
        timeline_name=job.timeline_name, timeline_identity=job.timeline_identity,
        clip_ids=job.clip_ids, reference_clip_id=job.reference_clip_id,
        preset_name=job.preset_name, drx_preset_name=job.drx_preset_name,
        before_versions=job.before_versions, drx_asset_identity=job.drx_asset_identity,
    )
    if job.plan_schema == PLAN_V1:
        payload = _plan_payload_v1(**common, adjustments=job.adjustments, cdl=job.cdl)
    else:
        payload = _plan_payload_v2(
            **common, matching_strategy=job.matching_strategy,
            adjustments_by_clip=job.adjustments_by_clip,
            observations_by_clip=job.observations_by_clip, cdl_by_clip=job.cdl_by_clip,
        )
    expected = plan_fingerprint(payload)
    if expected != job.plan_fingerprint:
        raise ValidationError("Record Colorist con fingerprint alterato")
    return job


class ColoristJobStore:
    def __init__(self, path: Path, workstation_id: str,
                 on_save: Callable[[ColoristJob], None] | None = None):
        if not re.fullmatch(r"PC_[A-Z0-9_]{2,48}", workstation_id):
            raise ValidationError("workstation store Colorist non valido")
        self.path = path
        self.workstation_id = workstation_id
        self.on_save = on_save

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema": SCHEMA, "workstation_id": self.workstation_id, "jobs": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Registry Colorist non leggibile: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"schema", "workstation_id", "jobs"}:
            raise ValidationError("Registry Colorist malformato")
        if data["schema"] != SCHEMA or data["workstation_id"] != self.workstation_id:
            raise ValidationError("Registry Colorist di schema o workstation differente")
        if not isinstance(data["jobs"], dict):
            raise ValidationError("Jobs Colorist non validi")
        for key, raw in data["jobs"].items():
            if _from_payload(raw).colorist_job_id != key:
                raise ValidationError("Identità job Colorist incoerente")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=str(self.path.parent), text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create(self, job: ColoristJob) -> ColoristJob:
        _validate(job)
        if job.workstation_id != self.workstation_id or job.state != "PREPARED" or job.revision != 0:
            raise ValidationError("Nuovo job Colorist non valido per questo store")
        with _STORE_WRITE_LOCK:
            data = self._load()
            if job.colorist_job_id in data["jobs"]:
                raise ValidationError("colorist_job_id già esistente")
            created = replace(job, revision=1)
            data["jobs"][created.colorist_job_id] = asdict(created)
            self._save(data)
        if self.on_save is not None:
            self.on_save(created)
        return created

    def get(self, job_id: str, workstation_id: str) -> ColoristJob:
        if workstation_id != self.workstation_id:
            raise ValidationError("Richiesta Colorist da workstation differente")
        raw = self._load()["jobs"].get(job_id)
        if raw is None:
            raise ValidationError("Job Colorist non trovato")
        return _from_payload(raw)

    def list_jobs(self) -> tuple[ColoristJob, ...]:
        return tuple(_from_payload(raw) for raw in self._load()["jobs"].values())

    def save(self, job: ColoristJob, expected_revision: int) -> ColoristJob:
        _validate(job)
        with _STORE_WRITE_LOCK:
            data = self._load()
            raw = data["jobs"].get(job.colorist_job_id)
            if raw is None:
                raise ValidationError("Job Colorist non trovato")
            current = _from_payload(raw)
            if job == current:
                return current
            if current.revision != expected_revision:
                raise ValidationError("revision Colorist stale")
            if job.revision != current.revision:
                raise ValidationError("Il chiamante non può impostare revision")
            immutable = (
                "colorist_job_id", "workstation_id", "project_name", "timeline_name", "timeline_identity",
                "clip_ids", "reference_clip_id", "adjustments", "preset_name", "drx_preset_name",
                "drx_asset_identity", "before_versions", "cdl", "plan_schema", "matching_strategy",
                "adjustments_by_clip", "observations_by_clip", "cdl_by_clip", "plan_fingerprint",
            )
            if any(getattr(job, name) != getattr(current, name) for name in immutable):
                raise ValidationError("Identità immutabile Colorist modificata")
            allowed = {"PREPARED": "APPROVED", "APPROVED": "APPLYING", "APPLYING": None,
                       "FAILED_RECOVERABLE": None, "FAILED_MANUAL": None,
                       "APPLIED": None, "ACCEPTED": None, "REJECTED": None,
                       "CANCELLED": None}
            if job.state != current.state:
                if current.state == "APPLIED":
                    if job.state not in {"ACCEPTED", "REJECTED"}:
                        raise ValidationError("Transizione review Colorist non consentita")
                elif current.state == "APPLYING" and job.state in {
                    "APPLIED", "FAILED_RECOVERABLE", "FAILED_MANUAL"
                }:
                    pass
                elif allowed[current.state] != job.state:
                    raise ValidationError("Transizione Colorist non consentita")
            elif job.state not in {"APPLIED", "ACCEPTED", "REJECTED"}:
                raise ValidationError("Aggiornamento Colorist senza transizione non consentito")
            saved = replace(job, revision=current.revision + 1)
            data["jobs"][saved.colorist_job_id] = asdict(saved)
            self._save(data)
        if self.on_save is not None:
            self.on_save(saved)
        return saved

    def cancel(self, job_id: str, expected_plan_fingerprint: str, expected_revision: int,
               operator_role: str, reason: str) -> ColoristJob:
        if not isinstance(expected_plan_fingerprint, str) or not HEX64.fullmatch(expected_plan_fingerprint):
            raise ValidationError("plan fingerprint Colorist non valido")
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1:
            raise ValidationError("revision Colorist non valida")
        role = str(operator_role).upper()
        if role not in ROLES:
            raise ValidationError("ruolo annullamento Colorist non consentito")
        normalized_reason = reason.strip() if isinstance(reason, str) else ""
        if (not normalized_reason or len(normalized_reason) > 500
                or not all(character.isprintable() for character in normalized_reason)):
            raise ValidationError("motivo annullamento Colorist non valido")
        evidence = {
            "expected_revision": expected_revision,
            "plan_fingerprint": expected_plan_fingerprint,
            "reason": normalized_reason,
        }
        with _STORE_WRITE_LOCK:
            data = self._load()
            raw = data["jobs"].get(job_id)
            if raw is None:
                raise ValidationError("Job Colorist non trovato")
            current = _from_payload(raw)
            if current.plan_fingerprint != expected_plan_fingerprint:
                raise ValidationError("plan fingerprint Colorist non corrispondente")
            if current.state == "CANCELLED":
                if (current.revision == expected_revision + 1
                        and current.operator_role == role
                        and current.cancellation_evidence == evidence):
                    return current
                raise ValidationError("Piano Colorist già CANCELLED con parametri differenti")
            if current.state != "PREPARED":
                raise ValidationError("Solo un piano PREPARED può essere annullato")
            if current.revision != expected_revision:
                raise ValidationError("revision Colorist stale")
            if current.preview_restore_versions:
                raise ValidationError("Annullamento Colorist vietato con preview attiva")
            if current.apply_evidence:
                raise ValidationError("Annullamento Colorist vietato con evidenza apply")
            cancelled = replace(
                current,
                state="CANCELLED",
                operator_role=role,
                cancellation_evidence=evidence,
                state_timestamps={**current.state_timestamps, "CANCELLED": _now()},
            )
            _validate(cancelled)
            saved = replace(cancelled, revision=current.revision + 1)
            data["jobs"][saved.colorist_job_id] = asdict(saved)
            self._save(data)
        if self.on_save is not None:
            self.on_save(saved)
        return saved


def cancel_colorist_job(store: ColoristJobStore, job_id: str, expected_plan_fingerprint: str,
                         expected_revision: int, operator_role: str, reason: str) -> ColoristJob:
    return store.cancel(
        job_id, expected_plan_fingerprint, expected_revision, operator_role, reason,
    )

