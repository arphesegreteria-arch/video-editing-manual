from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import tempfile
from typing import Any, Iterable, Mapping

from .carabellese_contract import CarabellesePreferences, WORKFLOW_ID
from .carabellese_jobs import CarabelleseJob
from .config import CreativeConfig
from .safety import ValidationError


OUTCOME_SCHEMA = "ARPHE_CARABELLESE_OUTCOME_V1"
APPLY_SCHEMA = "ARPHE_CARABELLESE_JOURNAL_V1"
PROPOSAL_SCHEMA = "ARPHE_CARABELLESE_PROFILE_PROPOSALS_V1"
OVERLAY_SCHEMA = "ARPHE_CARABELLESE_PROFILE_OVERLAY_V1"
PROPOSAL_ID = re.compile(r"^proposal_[0-9a-f]{16}$")
PRIVATE_ID = re.compile(r"(?:carabellese|editorial)_[0-9a-f]{16}", re.IGNORECASE)
PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp)/)", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _journal_rows(config: CreativeConfig) -> list[dict[str, object]]:
    path = config.carabellese_journal_path
    if not path.is_file():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            raw = json.loads(line)
            if not isinstance(raw, dict) or raw.get("schema") not in {APPLY_SCHEMA, OUTCOME_SCHEMA}:
                raise ValidationError("Record journal Carabellese non supportato")
            if raw.get("schema") == OUTCOME_SCHEMA:
                if raw.get("workstation_id") != config.workstation_id:
                    raise ValidationError("Journal learning appartenente a un altro workstation")
                if raw.get("workflow_id") != WORKFLOW_ID:
                    raise ValidationError("Journal learning appartenente a un altro workflow")
            rows.append(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Journal learning Carabellese non leggibile: {exc}") from exc
    return rows


def _write_journal(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _outcomes(config: CreativeConfig) -> list[dict[str, object]]:
    return [row for row in _journal_rows(config) if row.get("schema") == OUTCOME_SCHEMA]


def _band(candidate: Mapping[str, object]) -> str | None:
    kind = str(candidate.get("kind", ""))
    if kind == "PAUSE_CONTEXTUAL":
        return "CONTEXTUAL"
    if kind == "PAUSE_REDUCE":
        return "LONG"
    return None


def _category(candidate: Mapping[str, object]) -> str:
    kind = str(candidate.get("kind", "UNKNOWN"))
    return kind if kind in {
        "PAUSE_CONTEXTUAL", "PAUSE_REDUCE", "BOUNDARY_START", "BOUNDARY_END",
        "EDITORIAL_CUE", "MANUAL",
    } else "UNKNOWN"


def append_carabellese_outcome(config: CreativeConfig,
                               job: CarabelleseJob) -> dict[str, object]:
    if job.state != "CLOSED":
        raise ValidationError("Solo un job CLOSED può alimentare il learning Carabellese")
    if job.workstation_id != config.workstation_id:
        raise ValidationError("Job Carabellese appartenente a un altro workstation")
    if job.workflow_id != WORKFLOW_ID:
        raise ValidationError("Job appartenente a un workflow diverso da Carabellese")
    candidates = {str(item.get("candidate_id")): item for item in job.candidates}
    decisions = {str(item.get("candidate_id")): item for item in job.decisions}
    if not candidates or set(candidates) != set(decisions):
        raise ValidationError("Decisioni Carabellese incomplete per il learning")
    all_rows = _journal_rows(config)
    existing = [row for row in all_rows if row.get("schema") == OUTCOME_SCHEMA]
    additions = []
    expected_tokens = set()
    for candidate_id in sorted(candidates):
        candidate, decision = candidates[candidate_id], decisions[candidate_id]
        token = _digest({"workstation_id": config.workstation_id,
                         "job": job.carabellese_job_id, "candidate": candidate_id})
        expected_tokens.add(token)
        proposed_start = float(candidate["start_seconds"])
        proposed_end = float(candidate["end_seconds"])
        final_start = float(decision["start_seconds"])
        final_end = float(decision["end_seconds"])
        residual = decision.get("residual_seconds")
        additions.append({
            "schema": OUTCOME_SCHEMA,
            "workstation_id": config.workstation_id,
            "workflow_id": WORKFLOW_ID,
            "sample_token": token,
            "category": _category(candidate),
            "pause_band": _band(candidate),
            "outcome": str(decision["outcome"]),
            "residual_seconds": None if residual is None else float(residual),
            "start_delta_seconds": round(final_start - proposed_start, 6),
            "end_delta_seconds": round(final_end - proposed_end, 6),
            "recorded_at": _now(),
        })
    found = {str(row.get("sample_token")) for row in existing} & expected_tokens
    if found:
        if found != expected_tokens:
            raise ValidationError("Journal learning parziale per un job già registrato")
        return {"ok": True, "recorded": len(found)}
    _write_journal(config.carabellese_journal_path, [*all_rows, *additions])
    return {"ok": True, "recorded": len(additions)}


def _aggregate(records: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, int]]:
    if not records:
        raise ValidationError("Nessun campione Carabellese disponibile")
    pause_bands: dict[str, list[bool]] = {}
    residuals = []
    boundary_start, boundary_end = [], []
    false_positives: dict[str, int] = {}
    for row in records:
        band = row.get("pause_band")
        outcome = str(row.get("outcome"))
        if isinstance(band, str):
            pause_bands.setdefault(band, []).append(outcome != "KEEP")
            residual = row.get("residual_seconds")
            if outcome != "KEEP" and isinstance(residual, (int, float)) and not isinstance(residual, bool):
                residuals.append(float(residual))
        category = str(row.get("category"))
        if category in {"BOUNDARY_START", "BOUNDARY_END"} and outcome == "MODIFY":
            boundary_start.append(float(row["start_delta_seconds"]))
            boundary_end.append(float(row["end_delta_seconds"]))
        if outcome == "KEEP":
            false_positives[category] = false_positives.get(category, 0) + 1
    aggregates: dict[str, object] = {
        "pause_band_approval_rates": {
            key: sum(values) / len(values) for key, values in sorted(pause_bands.items())
        },
        "false_positive_categories": dict(sorted(false_positives.items())),
    }
    counts = {
        "pause_band_approval_rates": sum(len(values) for values in pause_bands.values()),
        "false_positive_categories": sum(false_positives.values()),
    }
    if residuals:
        aggregates["preferred_residual_pause_seconds"] = {
            "min": min(residuals), "median": statistics.median(residuals), "max": max(residuals),
        }
        counts["preferred_residual_pause_seconds"] = len(residuals)
    if boundary_start:
        aggregates["boundary_adjustments_seconds"] = {
            "median_start": statistics.median(boundary_start),
            "median_end": statistics.median(boundary_end),
        }
        counts["boundary_adjustments_seconds"] = len(boundary_start)
    return aggregates, counts


def inspect_carabellese_metrics(config: CreativeConfig) -> dict[str, object]:
    records = _outcomes(config)
    aggregates, _ = _aggregate(records) if records else ({}, {})
    residual = aggregates.get("preferred_residual_pause_seconds", {})
    return {
        "workstation_id": config.workstation_id,
        "sample_count": len(records),
        "pause_bands": aggregates.get("pause_band_approval_rates", {}),
        "residual_durations_seconds": sorted({
            float(row["residual_seconds"]) for row in records
            if row.get("pause_band") and row.get("outcome") != "KEEP"
            and isinstance(row.get("residual_seconds"), (int, float))
        }),
        "boundary_shifts_seconds": aggregates.get("boundary_adjustments_seconds", {}),
        "false_positive_categories": aggregates.get("false_positive_categories", {}),
        "preferred_residual_summary": residual,
    }


def _proposal_store(config: CreativeConfig) -> dict[str, object]:
    path = config.carabellese_profile_proposals_path
    if not path.is_file():
        return {"schema": PROPOSAL_SCHEMA, "workstation_id": config.workstation_id,
                "workflow_id": WORKFLOW_ID, "proposals": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Proposte Carabellese non leggibili: {exc}") from exc
    expected = {"schema", "workstation_id", "workflow_id", "proposals"}
    if not isinstance(raw, dict) or set(raw) != expected or raw.get("schema") != PROPOSAL_SCHEMA:
        raise ValidationError("Store proposte Carabellese malformato")
    if raw["workstation_id"] != config.workstation_id:
        raise ValidationError("Store proposte appartenente a un altro workstation")
    if raw["workflow_id"] != WORKFLOW_ID or not isinstance(raw["proposals"], dict):
        raise ValidationError("Store proposte appartenente a un altro workflow")
    return raw


def _validate_private_free(payload: object) -> None:
    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items(): visit(key); visit(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value: visit(nested)
        elif isinstance(value, str) and (PRIVATE_ID.search(value) or PRIVATE_PATH.search(value)):
            raise ValidationError("La proposta Carabellese contiene dati privati")
    visit(payload)


def compile_carabellese_profile_proposal(
    config: CreativeConfig, shared: CarabellesePreferences, minimum_samples: int,
) -> dict[str, object]:
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValidationError("minimum_samples deve essere positivo")
    records = _outcomes(config)
    if len(records) < minimum_samples:
        raise ValidationError(f"Servono almeno {minimum_samples} campioni Carabellese")
    aggregates, counts = _aggregate(records)
    prior_digest = _digest(asdict(shared))
    proposed_profile = {
        "schema_version": 1, "workflow_id": WORKFLOW_ID, "version": shared.version + 1,
        "aggregate_preferences": aggregates, "sample_counts": counts,
    }
    proposed_digest = _digest(proposed_profile)
    proposal_id = "proposal_" + _digest({"workstation_id": config.workstation_id,
        "prior_profile_digest": prior_digest, "proposed_profile_digest": proposed_digest})[:16]
    proposal = {
        "proposal_id": proposal_id, "status": "PENDING",
        "prior_profile_digest": prior_digest, "proposed_profile_digest": proposed_digest,
        "proposed_profile_version": shared.version + 1, "sample_count": len(records),
        "aggregate_preferences": aggregates, "sample_counts": counts, "created_at": _now(),
    }
    _validate_private_free(proposal)
    store = _proposal_store(config)
    existing = store["proposals"].get(proposal_id)
    if existing is not None:
        left, right = dict(existing), dict(proposal)
        left.pop("created_at", None); right.pop("created_at", None)
        if left == right and left.get("status") == "PENDING":
            return dict(existing)
        raise ValidationError("ID proposta Carabellese già usato")
    store["proposals"][proposal_id] = proposal
    _atomic_json(config.carabellese_profile_proposals_path, store)
    return proposal


def approve_carabellese_profile_proposal(
    config: CreativeConfig, proposal_id: str, operator_role: str,
    expected_previous_digest: str,
) -> dict[str, object]:
    if operator_role not in {"ALESSIO", "TECNICO"}:
        raise ValidationError("Solo Alessio o personale tecnico può approvare il profilo Carabellese")
    if not PROPOSAL_ID.fullmatch(proposal_id):
        raise ValidationError("proposal_id Carabellese non valido")
    store = _proposal_store(config)
    proposal = store["proposals"].get(proposal_id)
    if not isinstance(proposal, dict):
        raise ValidationError("Proposta Carabellese non trovata")
    if proposal.get("status") != "PENDING":
        raise ValidationError("Proposta Carabellese già approvata o non approvabile")
    if proposal.get("prior_profile_digest") != expected_previous_digest:
        raise ValidationError("Digest profilo Carabellese precedente stale")
    _validate_private_free(proposal)
    approved_at = _now()
    overlay = {
        "schema": OVERLAY_SCHEMA, "workstation_id": config.workstation_id,
        "workflow_id": WORKFLOW_ID, "proposal_id": proposal_id,
        "prior_profile_digest": proposal["prior_profile_digest"],
        "proposed_profile_digest": proposal["proposed_profile_digest"],
        "proposed_profile_version": proposal["proposed_profile_version"],
        "aggregate_preferences": proposal["aggregate_preferences"],
        "sample_counts": proposal["sample_counts"], "approved_at": approved_at,
    }
    _atomic_json(config.carabellese_profile_overlay_path, overlay)
    proposal["status"] = "APPROVED"
    proposal["approved_at"] = approved_at
    _atomic_json(config.carabellese_profile_proposals_path, store)
    return {"ok": True, "proposal_id": proposal_id,
            "proposed_profile_digest": proposal["proposed_profile_digest"]}
