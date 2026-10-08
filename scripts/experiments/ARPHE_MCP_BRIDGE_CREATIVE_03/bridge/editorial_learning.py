from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import statistics
import tempfile
from typing import Any, Iterable, Mapping

from .config import CreativeConfig
from .editorial_jobs import EditorialJob
from .editorial_selection_contract import (
    AGGREGATE_KEYS,
    WORKFLOW_ID,
    PreferenceProfile,
    canonical_digest,
)
from .safety import ValidationError


JOURNAL_SCHEMA = "ARPHE_EDITORIAL_OUTCOME_V1"
PROPOSAL_STORE_SCHEMA = "ARPHE_EDITORIAL_PROPOSALS_V1"
OVERLAY_SCHEMA = "ARPHE_EDITORIAL_PROFILE_OVERLAY_V1"
PROPOSAL_ID = re.compile(r"^proposal_[0-9a-f]{16}$")
JOB_ID = re.compile(r"editorial_[0-9a-f]{16}", re.IGNORECASE)
PATH_TEXT = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp)/)", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValidationError(f"Timestamp {label} mancante")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"Timestamp {label} non valido") from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"Timestamp {label} privo di timezone")
    return parsed


def _read_journal(config: CreativeConfig) -> list[dict[str, object]]:
    path = config.editorial_journal_path
    if not path.is_file():
        return []
    records: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        for line in lines:
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise ValidationError("Record journal editoriale non valido")
            if raw.get("schema") != JOURNAL_SCHEMA:
                raise ValidationError("Schema journal editoriale non supportato")
            if raw.get("workstation_id") != config.workstation_id:
                raise ValidationError("Journal editoriale appartenente a un altro workstation")
            records.append(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Journal editoriale non leggibile: {exc}") from exc
    return records


def _write_journal(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False))
                handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _decision_record(config: CreativeConfig, job: EditorialJob,
                     candidate: Mapping[str, object], decision: Mapping[str, object]) -> dict[str, object]:
    proposed_start = float(decision["proposed_start_seconds"])
    proposed_end = float(decision["proposed_end_seconds"])
    final_start = float(decision["source_start_seconds"])
    final_end = float(decision["source_end_seconds"])
    marked = _parse_time(job.state_timestamps.get("MARKED"), "MARKED")
    reviewed = _parse_time(job.state_timestamps.get("REVIEWED"), "REVIEWED")
    latency = (reviewed - marked).total_seconds()
    if latency < 0:
        raise ValidationError("review_latency_seconds non può essere negativo")
    outcome = str(decision["outcome"])
    unchanged = outcome == "APPROVE" and final_start == proposed_start and final_end == proposed_end
    return {
        "schema": JOURNAL_SCHEMA,
        "workstation_id": config.workstation_id,
        "workflow_id": job.workflow_id,
        "workflow_version": job.workflow_version,
        "editorial_job_id": job.editorial_job_id,
        "candidate_id": str(decision["candidate_id"]),
        "project_name": job.project_name,
        "timeline_name": job.timeline_name,
        "timeline_identity": job.timeline_identity,
        "source_fingerprint": job.source_fingerprint,
        "outcome": outcome,
        "human_reason": str(decision["reason"]),
        "normalized_reason_tags": list(decision.get("normalized_reason_tags", [])),
        "proposed_start_seconds": proposed_start,
        "proposed_end_seconds": proposed_end,
        "final_start_seconds": final_start,
        "final_end_seconds": final_end,
        "proposed_duration_seconds": proposed_end - proposed_start,
        "final_duration_seconds": float(decision["final_duration_seconds"]),
        "start_delta_seconds": final_start - proposed_start,
        "end_delta_seconds": final_end - proposed_end,
        "proposal_timestamp": job.state_timestamps["MARKED"],
        "review_timestamp": job.state_timestamps["REVIEWED"],
        "review_latency_seconds": latency,
        "first_proposal_accepted_unchanged": unchanged,
        "recorded_at": _now(),
    }


def append_local_outcome(config: CreativeConfig, job: EditorialJob) -> dict[str, object]:
    if job.state != "VERIFIED":
        raise ValidationError("Solo un job VERIFIED può alimentare il journal")
    if job.workstation_id != config.workstation_id:
        raise ValidationError("Job editoriale appartenente a un altro workstation")
    by_candidate = {str(item["candidate_id"]): item for item in job.candidates}
    if set(by_candidate) != {str(item.get("candidate_id")) for item in job.decisions}:
        raise ValidationError("Decisioni incomplete per il journal")
    records = _read_journal(config)
    existing = [record for record in records if record.get("editorial_job_id") == job.editorial_job_id]
    if existing:
        if {record.get("candidate_id") for record in existing} != set(by_candidate):
            raise ValidationError("Journal parziale per un job già registrato")
        return {"ok": True, "recorded": len(existing)}
    additions = [
        _decision_record(config, job, by_candidate[str(decision["candidate_id"])], decision)
        for decision in job.decisions
    ]
    _write_journal(config.editorial_journal_path, [*records, *additions])
    return {"ok": True, "recorded": len(additions)}


def inspect_local_metrics(config: CreativeConfig) -> dict[str, object]:
    records = _read_journal(config)
    count = len(records)
    jobs: dict[str, float] = {}
    for record in records:
        jobs[str(record["editorial_job_id"])] = float(record["review_latency_seconds"])
    unchanged = sum(bool(record["first_proposal_accepted_unchanged"]) for record in records)
    modified = sum(record["outcome"] == "MODIFY" for record in records)
    rejected = sum(record["outcome"] == "REJECT" for record in records)
    corrected = sum(
        record["outcome"] == "MODIFY"
        and (float(record["start_delta_seconds"]) != 0 or float(record["end_delta_seconds"]) != 0)
        for record in records
    )
    return {
        "workstation_id": config.workstation_id,
        "job_count": len(jobs),
        "candidate_count": count,
        "accepted_unchanged_rate": 0.0 if not count else unchanged / count,
        "modification_rate": 0.0 if not count else modified / count,
        "rejection_rate": 0.0 if not count else rejected / count,
        "boundary_correction_count": corrected,
        "review_latency_seconds": sum(jobs.values()),
    }


def _proposal_store(config: CreativeConfig) -> dict[str, object]:
    path = config.editorial_profile_proposals_path
    if not path.is_file():
        return {"schema": PROPOSAL_STORE_SCHEMA, "workstation_id": config.workstation_id,
                "proposals": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Proposte editoriali non leggibili: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema", "workstation_id", "proposals"}:
        raise ValidationError("Store proposte editoriali malformato")
    if raw["schema"] != PROPOSAL_STORE_SCHEMA:
        raise ValidationError("Schema proposte editoriali non supportato")
    if raw["workstation_id"] != config.workstation_id:
        raise ValidationError("Store proposte appartenente a un altro workstation")
    if not isinstance(raw["proposals"], dict):
        raise ValidationError("Elenco proposte editoriali non valido")
    return raw


def _sensitive_inventory(records: Iterable[Mapping[str, object]]) -> dict[str, list[str]]:
    private_fields = (
        "project_name", "timeline_name", "timeline_identity", "source_fingerprint", "human_reason",
    )
    rows = list(records)
    return {
        "job_ids": sorted({str(row["editorial_job_id"]) for row in rows}),
        "private_strings": sorted({
            str(row[field]) for row in rows for field in private_fields if row.get(field)
        }),
    }


def validate_profile_proposal_privacy(payload: object,
                                      sensitive: Mapping[str, Iterable[str]]) -> None:
    forbidden = [
        str(value).casefold() for values in sensitive.values() for value in values
        if isinstance(value, str) and len(value.strip()) >= 4
    ]

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                visit(key)
                visit(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested)
        elif isinstance(value, str):
            lowered = value.casefold()
            if JOB_ID.search(value) or PATH_TEXT.search(value) or any(item in lowered for item in forbidden):
                raise ValidationError("La proposta contiene dati editoriali privati")

    visit(payload)


def _aggregates(records: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, int]]:
    accepted = [row for row in records if row["outcome"] in {"APPROVE", "MODIFY"}]
    if not accepted:
        raise ValidationError("Servono campioni approvati o modificati")
    durations = [float(row["final_duration_seconds"]) for row in accepted]
    modified = [row for row in records if row["outcome"] == "MODIFY"]
    unchanged = [row for row in records if row["first_proposal_accepted_unchanged"]]
    weak_tags = sorted({
        str(tag) for row in records if row["outcome"] in {"MODIFY", "REJECT"}
        for tag in row["normalized_reason_tags"]
        if any(token in str(tag) for token in ("apertura", "incipit", "opening"))
    })
    unchanged_tags = sorted({str(tag) for row in unchanged for tag in row["normalized_reason_tags"]})
    aggregates: dict[str, object] = {
        "preferred_duration_seconds": {"min": min(durations), "max": max(durations)},
    }
    counts = {"preferred_duration_seconds": len(accepted)}
    if weak_tags:
        aggregates["weak_opening_tags"] = weak_tags
        counts["weak_opening_tags"] = len([
            row for row in records if row["outcome"] in {"MODIFY", "REJECT"}
        ])
    start_reductions = [
        float(row["start_delta_seconds"]) for row in modified
        if float(row["start_delta_seconds"]) > 0
    ]
    end_reductions = [
        -float(row["end_delta_seconds"]) for row in modified
        if float(row["end_delta_seconds"]) < 0
    ]
    if start_reductions and end_reductions:
        aggregates["context_reduction_seconds"] = {
            "median_start": statistics.median(start_reductions),
            "median_end": statistics.median(end_reductions),
        }
        counts["context_reduction_seconds"] = len(modified)
    if unchanged_tags:
        aggregates["unchanged_approval_tags"] = unchanged_tags
        counts["unchanged_approval_tags"] = len(unchanged)
    return aggregates, counts


def compile_profile_proposal(config: CreativeConfig, shared: PreferenceProfile,
                             *, minimum_samples: int = 5) -> dict[str, object]:
    if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int) or minimum_samples < 1:
        raise ValidationError("minimum_samples deve essere positivo")
    store = _proposal_store(config)
    records = _read_journal(config)
    if len(records) < minimum_samples:
        raise ValidationError(f"Servono almeno {minimum_samples} campioni editoriali")
    aggregates, counts = _aggregates(records)
    profile_unsigned = {
        "schema_version": 1,
        "profile_version": shared.profile_version + 1,
        "workflow_id": WORKFLOW_ID,
        "aggregate_preferences": aggregates,
        "sample_counts": counts,
    }
    proposed_digest = canonical_digest(profile_unsigned)
    proposal_id = "proposal_" + canonical_digest({
        "workstation_id": config.workstation_id,
        "prior_profile_digest": shared.digest,
        "proposed_profile_digest": proposed_digest,
    })[:16]
    proposal = {
        "proposal_id": proposal_id,
        "status": "PENDING",
        "prior_profile_digest": shared.digest,
        "proposed_profile_digest": proposed_digest,
        "proposed_profile_version": shared.profile_version + 1,
        "sample_count": len(records),
        "aggregate_preferences": aggregates,
        "sample_counts": counts,
        "created_at": _now(),
    }
    validate_profile_proposal_privacy(proposal, _sensitive_inventory(records))
    existing = store["proposals"].get(proposal_id)
    if existing is not None:
        comparable = dict(proposal); comparable.pop("created_at")
        stored = dict(existing); stored.pop("created_at", None)
        if stored.get("status") == "PENDING" and stored == comparable:
            return dict(existing)
        raise ValidationError("ID proposta già usato con contenuto o stato differente")
    store["proposals"][proposal_id] = proposal
    _atomic_json(config.editorial_profile_proposals_path, store)
    return proposal


def approve_profile_proposal(config: CreativeConfig, proposal_id: str, operator_role: str,
                             expected_prior_digest: str) -> dict[str, object]:
    if operator_role != "ALESSIO":
        raise ValidationError("Solo Alessio può approvare una proposta editoriale")
    if not PROPOSAL_ID.fullmatch(proposal_id):
        raise ValidationError("proposal_id non valido")
    store = _proposal_store(config)
    proposal = store["proposals"].get(proposal_id)
    if not isinstance(proposal, dict):
        raise ValidationError("Proposta editoriale non trovata")
    if proposal.get("status") == "APPROVED":
        raise ValidationError("Proposta già approvata")
    if proposal.get("status") != "PENDING":
        raise ValidationError("Stato proposta non approvabile")
    if expected_prior_digest != proposal.get("prior_profile_digest"):
        raise ValidationError("Digest profilo precedente stale")
    validate_profile_proposal_privacy(proposal, _sensitive_inventory(_read_journal(config)))
    overlay = {
        "schema": OVERLAY_SCHEMA,
        "workstation_id": config.workstation_id,
        "workflow_id": WORKFLOW_ID,
        "proposal_id": proposal_id,
        "prior_profile_digest": proposal["prior_profile_digest"],
        "proposed_profile_digest": proposal["proposed_profile_digest"],
        "proposed_profile_version": proposal["proposed_profile_version"],
        "aggregate_preferences": proposal["aggregate_preferences"],
        "sample_counts": proposal["sample_counts"],
        "approved_at": _now(),
    }
    _atomic_json(config.editorial_profile_overlay_path, overlay)
    proposal["status"] = "APPROVED"
    proposal["approved_at"] = overlay["approved_at"]
    _atomic_json(config.editorial_profile_proposals_path, store)
    return {"ok": True, "proposal_id": proposal_id,
            "proposed_profile_digest": proposal["proposed_profile_digest"]}


def _read_overlay(config: CreativeConfig) -> dict[str, object] | None:
    path = config.editorial_profile_overlay_path
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Overlay editoriale non leggibile: {exc}") from exc
    expected = {
        "schema", "workstation_id", "workflow_id", "proposal_id", "prior_profile_digest",
        "proposed_profile_digest", "proposed_profile_version", "aggregate_preferences",
        "sample_counts", "approved_at",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValidationError("Overlay editoriale malformato")
    if raw["schema"] != OVERLAY_SCHEMA or raw["workstation_id"] != config.workstation_id:
        raise ValidationError("Overlay editoriale appartenente a un altro workstation")
    if raw["workflow_id"] != WORKFLOW_ID:
        raise ValidationError("Workflow overlay editoriale non valido")
    unsigned = {
        "schema_version": 1,
        "profile_version": raw["proposed_profile_version"],
        "workflow_id": WORKFLOW_ID,
        "aggregate_preferences": raw["aggregate_preferences"],
        "sample_counts": raw["sample_counts"],
    }
    if canonical_digest(unsigned) != raw["proposed_profile_digest"]:
        raise ValidationError("Digest overlay editoriale non valido")
    return raw


def load_effective_preferences(config: CreativeConfig,
                               shared: PreferenceProfile) -> dict[str, object]:
    aggregates = dict(shared.aggregate_preferences)
    counts = dict(shared.sample_counts)
    overlay = _read_overlay(config)
    overlay_digest = None
    if overlay is not None:
        if overlay["prior_profile_digest"] != shared.digest:
            raise ValidationError("Overlay basato su un profilo condiviso stale")
        aggregates.update(overlay["aggregate_preferences"])
        counts.update(overlay["sample_counts"])
        overlay_digest = overlay["proposed_profile_digest"]
    if set(aggregates) - AGGREGATE_KEYS or set(counts) != set(aggregates):
        raise ValidationError("Preferenze effettive non conformi al contratto")
    return {
        "workflow_id": WORKFLOW_ID,
        "shared_profile_digest": shared.digest,
        "local_overlay_digest": overlay_digest,
        "aggregate_preferences": {key: aggregates[key] for key in sorted(aggregates)},
        "sample_counts": {key: counts[key] for key in sorted(counts)},
    }
