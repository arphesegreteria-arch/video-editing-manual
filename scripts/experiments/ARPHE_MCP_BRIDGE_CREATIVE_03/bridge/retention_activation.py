"""Workstation-local activation evidence. No file quarantine or purge operations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from .artifact_hygiene import _signature, validate_managed_path
from .artifact_planning import _scan_artifacts_unlocked, scan_artifacts, simulate_maintenance
from .artifact_records import ArtifactPolicy, ArtifactStore, _reject_links
from .config import CreativeConfig, load_config, validate_retention_profile

QUARANTINE_SECONDS = 1296000
ALLOWED_OPERATOR_ROLES = ("ALESSIO", "TECNICO")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Activation timestamp requires timezone")
    return value.astimezone(timezone.utc)


def _json_default(value):
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, Path):
        return str(value.resolve())
    raise TypeError(type(value).__name__)


def _fingerprint(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, default=_json_default)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def policy_fingerprint(policy: ArtifactPolicy) -> str:
    if type(policy.quarantine_seconds) is not int or policy.quarantine_seconds != QUARANTINE_SECONDS:
        raise ValueError("Quarantine must last 1296000 seconds from quarantined_at")
    return _fingerprint(asdict(policy))


def _profile(config: CreativeConfig) -> dict:
    paths = {key: getattr(config, key) for key in
             ("retention_activation_path", "artifact_registry_path", "artifact_journal_path",
              "artifact_quarantine_root")}
    validate_retention_profile(config)
    if type(config.purge_enabled) is not bool:
        raise ValueError("purge_enabled must be boolean")
    return {"workstation_id": config.workstation_id, "purge_enabled": config.purge_enabled,
            **paths}


def inventory_fingerprint(config: CreativeConfig, artifact_store: ArtifactStore) -> str:
    """Hash current inventory; permit only the caller's genuinely owned guard."""
    if artifact_store.workstation_id != config.workstation_id:
        raise ValueError("Artifact inventory workstation mismatch")
    if artifact_store.path != config.artifact_registry_path.resolve():
        raise ValueError("Artifact inventory registry mismatch")
    before = artifact_store.path.read_bytes() if artifact_store.path.exists() else None
    guard_owned = artifact_store.owns_registration_guard()
    if artifact_store.registration_lock_path.exists() and not guard_owned:
        raise ValueError("Artifact inventory registration locked")
    # The public scanner refuses every lock. Its implementation is safe here only
    # under the guard owned by this exact store instance and calling thread.
    scan = (_scan_artifacts_unlocked(config, artifact_store) if guard_owned
            else scan_artifacts(config, artifact_store))
    if not scan.get("ok"):
        raise ValueError("Artifact inventory could not be completed")
    records = artifact_store.records()
    roots = {key: getattr(config, key).resolve() for key in
             ("render_root", "runtime_log_root", "audio_root", "audio_jobs_root", "asset_root",
              "resolve_archive_root")}
    roots["profile_root"] = config.artifact_registry_path.parent.resolve()
    live = []
    for record in records:
        if record.workstation_id != config.workstation_id:
            raise ValueError("Artifact record workstation mismatch")
        signature = None
        root = roots.get(record.managed_root_id)
        if root is not None:
            try:
                selected = validate_managed_path(Path(record.quarantine_path or record.path), root,
                                                 allow_directory=record.kind == "directory")
                signature = _signature(selected, record.kind)
            except (OSError, ValueError):
                signature = "INSPECTION_ONLY"
        live.append({"record": asdict(record), "live_signature": signature})
    scan["items"] = sorted(scan["items"], key=lambda item: json.dumps(item, sort_keys=True))
    for item in scan["items"]:
        if item["artifact_id"] is not None:
            continue
        root_id, _, relative = item["display_path"].partition(":")
        root = roots.get(root_id)
        signature = "INSPECTION_ONLY"
        if root is not None:
            try:
                candidate = root / relative
                selected = validate_managed_path(candidate, root, allow_directory=candidate.is_dir())
                signature = _signature(selected, "directory" if selected.is_dir() else "file")
            except (OSError, ValueError):
                pass
        live.append({"display_path": item["display_path"], "live_signature": signature})
    after = artifact_store.path.read_bytes() if artifact_store.path.exists() else None
    guard_still_owned = artifact_store.owns_registration_guard()
    if (before != after or guard_owned != guard_still_owned
            or (artifact_store.registration_lock_path.exists() and not guard_still_owned)):
        raise ValueError("Artifact inventory changed during snapshot")
    return _fingerprint({"workstation_id": config.workstation_id, "scan": scan, "records": live})


@dataclass(frozen=True)
class ActivationProposal:
    proposal_id: str
    workstation_id: str
    policy_fingerprint: str
    inventory_fingerprint: str
    dry_run_fingerprint: str
    profile_fingerprint: str
    config_path: str
    purge_enabled: bool
    operator_roles: tuple[str, ...]
    created_at: datetime
    fingerprint: str


@dataclass(frozen=True)
class ActivationApproval:
    proposal_id: str
    proposal_fingerprint: str
    workstation_id: str
    policy_fingerprint: str
    inventory_fingerprint: str
    operator_role: str
    approved_at: datetime
    fingerprint: str


@dataclass(frozen=True)
class ActivationValidation:
    proposal_id: str
    workstation_id: str
    proposal_fingerprint: str
    validated_at: datetime
    fingerprint: str


@dataclass(frozen=True)
class ActivationInvalidation:
    proposal_id: str
    workstation_id: str
    proposal_fingerprint: str
    invalidated_at: datetime
    reason: str
    fingerprint: str


def _decode(record_type, raw):
    values = dict(raw)
    for key in ("created_at", "approved_at", "validated_at", "invalidated_at"):
        if key in values:
            values[key] = _utc(datetime.fromisoformat(values[key]))
    if "operator_roles" in values:
        values["operator_roles"] = tuple(values["operator_roles"])
    record = record_type(**values)
    payload = asdict(record)
    fingerprint = payload.pop("fingerprint")
    if fingerprint != _fingerprint(payload):
        raise ValueError("Activation record fingerprint mismatch")
    return record


class RetentionActivationStore:
    """Append-only proposal/approval records in an atomic workstation-owned file.

    Local hashes detect accidental edits; filesystem access remains the trust boundary.
    """
    def __init__(self, path: Path, workstation_id: str):
        if not re.fullmatch(r"PC_[A-Z0-9_]{2,48}", workstation_id):
            raise ValueError("Invalid workstation_id")
        _reject_links(path)
        self.path = path.resolve()
        self.workstation_id = workstation_id

    def _load(self) -> dict:
        _reject_links(self.path)
        if not self.path.exists():
            return {"schema_version": 2, "workstation_id": self.workstation_id,
                    "proposals": {}, "approvals": {}, "validations": {}, "invalidations": {},
                    "latest_proposal_id": None}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("workstation_id") != self.workstation_id:
            raise ValueError("Activation store workstation mismatch")
        if data.get("schema_version") != 2 or not all(
                isinstance(data.get(key), dict) for key in
                ("proposals", "approvals", "validations", "invalidations")):
            raise ValueError("Invalid activation store")
        for key, raw in data["proposals"].items():
            record = _decode(ActivationProposal, raw)
            if record.workstation_id != self.workstation_id or record.proposal_id != key:
                raise ValueError("Activation proposal workstation mismatch")
        for key, raw in data["approvals"].items():
            record = _decode(ActivationApproval, raw)
            if record.workstation_id != self.workstation_id or record.proposal_id != key:
                raise ValueError("Activation approval workstation mismatch")
        for key, raw in data["validations"].items():
            record = _decode(ActivationValidation, raw)
            if (record.workstation_id != self.workstation_id or record.proposal_id != key
                    or key not in data["proposals"]):
                raise ValueError("Activation validation workstation mismatch")
        for key, raw in data["invalidations"].items():
            record = _decode(ActivationInvalidation, raw)
            if (record.workstation_id != self.workstation_id or record.proposal_id != key
                    or key not in data["proposals"]):
                raise ValueError("Activation invalidation workstation mismatch")
        return data

    def _save(self, data: dict) -> None:
        _reject_links(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, default=_json_default, sort_keys=True, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _guard(self):
        _reject_links(self.path)
        return ArtifactStore(self.path, self.workstation_id).registration_guard()


def prepare_activation(config, artifact_store, policy, now_utc, *, defer_validation=False) -> ActivationProposal:
    now = _utc(now_utc)
    profile = _profile(config)
    policy_hash = policy_fingerprint(policy)
    inventory_hash = inventory_fingerprint(config, artifact_store)
    dry_run = simulate_maintenance(config, artifact_store, policy, now, active_job_ids=())
    if not dry_run.get("ok"):
        raise ValueError("Activation dry-run could not be completed")
    if inventory_fingerprint(config, artifact_store) != inventory_hash:
        raise ValueError("Artifact inventory changed during dry-run")
    payload = {"proposal_id": str(uuid4()), "workstation_id": config.workstation_id,
               "policy_fingerprint": policy_hash, "inventory_fingerprint": inventory_hash,
               "dry_run_fingerprint": _fingerprint(dry_run),
               "profile_fingerprint": _fingerprint(profile), "config_path": str(config.path.resolve()),
               "purge_enabled": config.purge_enabled, "operator_roles": ALLOWED_OPERATOR_ROLES,
               "created_at": now}
    proposal = ActivationProposal(**payload, fingerprint=_fingerprint(payload))
    store = RetentionActivationStore(config.retention_activation_path, config.workstation_id)
    with store._guard():
        data = store._load()
        data["proposals"][proposal.proposal_id] = asdict(proposal)
        data["latest_proposal_id"] = proposal.proposal_id
        if not defer_validation:
            validation_payload = {"proposal_id": proposal.proposal_id,
                                  "workstation_id": store.workstation_id,
                                  "proposal_fingerprint": proposal.fingerprint,
                                  "validated_at": now}
            validation = ActivationValidation(**validation_payload,
                                              fingerprint=_fingerprint(validation_payload))
            data["validations"][proposal.proposal_id] = asdict(validation)
        store._save(data)
    return proposal


def validate_activation(store, proposal_id, fingerprint, now_utc) -> ActivationValidation:
    now = _utc(now_utc)
    with store._guard():
        data = store._load()
        proposal = _decode(ActivationProposal, data["proposals"][proposal_id])
        if proposal.fingerprint != fingerprint or proposal_id in data["invalidations"]:
            raise ValueError("Activation proposal is invalidated or mismatched")
        payload = {"proposal_id": proposal_id, "workstation_id": store.workstation_id,
                   "proposal_fingerprint": fingerprint, "validated_at": now}
        validation = ActivationValidation(**payload, fingerprint=_fingerprint(payload))
        existing = data["validations"].get(proposal_id)
        if existing is not None and _decode(ActivationValidation, existing) != validation:
            raise ValueError("Activation proposal validation is immutable")
        data["validations"][proposal_id] = asdict(validation)
        store._save(data)
    return validation


def invalidate_activation(store, proposal_id, fingerprint, now_utc) -> ActivationInvalidation:
    now = _utc(now_utc)
    with store._guard():
        data = store._load()
        proposal = _decode(ActivationProposal, data["proposals"][proposal_id])
        if proposal.fingerprint != fingerprint:
            raise ValueError("Activation proposal fingerprint is mismatched")
        payload = {"proposal_id": proposal_id, "workstation_id": store.workstation_id,
                   "proposal_fingerprint": fingerprint, "invalidated_at": now,
                   "reason": "POST_PERSISTENCE_RECHECK_FAILED"}
        invalidation = ActivationInvalidation(**payload, fingerprint=_fingerprint(payload))
        existing = data["invalidations"].get(proposal_id)
        if existing is not None and _decode(ActivationInvalidation, existing) != invalidation:
            raise ValueError("Activation proposal invalidation is immutable")
        data["invalidations"][proposal_id] = asdict(invalidation)
        store._save(data)
    return invalidation


def approve_activation(store, proposal_id, fingerprint, operator_role, now_utc) -> ActivationApproval:
    if operator_role not in ALLOWED_OPERATOR_ROLES:
        raise ValueError("Unsupported operator_role")
    now = _utc(now_utc)
    with store._guard():
        data = store._load()
        proposal = _decode(ActivationProposal, data["proposals"][proposal_id])
        if proposal.fingerprint != fingerprint or data["latest_proposal_id"] != proposal_id:
            raise ValueError("Activation proposal fingerprint is stale or mismatched")
        if proposal_id in data["invalidations"]:
            raise ValueError("Activation proposal is invalidated")
        validation = _decode(ActivationValidation, data["validations"][proposal_id])
        if (validation.workstation_id != store.workstation_id
                or validation.proposal_fingerprint != proposal.fingerprint):
            raise ValueError("Activation proposal validation is invalid")
        if operator_role not in proposal.operator_roles:
            raise ValueError("Unsupported proposal operator_role")
        if now < proposal.created_at:
            raise ValueError("Approval timestamp precedes proposal timestamp")
        if proposal_id in data["approvals"]:
            raise ValueError("Activation proposal already approved; records are immutable")
        payload = {"proposal_id": proposal_id, "proposal_fingerprint": fingerprint,
                   "workstation_id": store.workstation_id,
                   "policy_fingerprint": proposal.policy_fingerprint,
                   "inventory_fingerprint": proposal.inventory_fingerprint,
                   "operator_role": operator_role, "approved_at": now}
        approval = ActivationApproval(**payload, fingerprint=_fingerprint(payload))
        data["approvals"][proposal_id] = asdict(approval)
        store._save(data)
    return approval


def activation_allows_purge(store, workstation_id, policy_fingerprint, inventory_fingerprint) -> bool:
    """Evidence predicate only. Later purge code must enforce per-artifact safety."""
    if workstation_id != store.workstation_id or not all(
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in (policy_fingerprint, inventory_fingerprint)):
        return False
    try:
        if store.path.with_suffix(store.path.suffix + ".registration.lock").exists():
            return False
        data = store._load()
        proposal_id = data["latest_proposal_id"]
        proposal = _decode(ActivationProposal, data["proposals"][proposal_id])
        approval = _decode(ActivationApproval, data["approvals"][proposal_id])
        validation = _decode(ActivationValidation, data["validations"][proposal_id])
        config = load_config(Path(proposal.config_path))
        return bool(
            proposal.purge_enabled is True and config.purge_enabled is True
            and config.workstation_id == workstation_id
            and config.retention_activation_path.resolve() == store.path
            and _fingerprint(_profile(config)) == proposal.profile_fingerprint
            and approval.workstation_id == proposal.workstation_id == workstation_id
            and approval.proposal_fingerprint == proposal.fingerprint
            and proposal_id not in data["invalidations"]
            and validation.workstation_id == workstation_id
            and validation.proposal_fingerprint == proposal.fingerprint
            and approval.policy_fingerprint == proposal.policy_fingerprint == policy_fingerprint
            and approval.inventory_fingerprint == proposal.inventory_fingerprint == inventory_fingerprint
            and approval.operator_role in proposal.operator_roles
            and approval.operator_role in ALLOWED_OPERATOR_ROLES
            and approval.approved_at >= proposal.created_at)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
