from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any


WORKSTATIONS = {"PC_PERSONALE", "PC_SEGRETERIA"}
CHECKS = {
    "capability_probe", "source_binding", "complete_review", "checkpoint_restore",
    "single_timeline", "partial_failure_recovery", "foreign_marker_preservation",
    "rollback_flag",
}
SENSITIVE_KEYS = {
    "reason", "human_reason", "transcript", "quote", "source_path", "media_path",
    "project_name", "timeline_name", "job_id", "carabellese_job_id",
}
PRIVATE_ID = re.compile(r"(?:carabellese|editorial)_[0-9a-f]{16}", re.IGNORECASE)
PRIVATE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp)/)", re.IGNORECASE)


def _timestamp(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{label} must be an ISO-8601 timestamp with timezone")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be an ISO-8601 timestamp with timezone")
        return
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(f"{label} must include a timezone")
    elif parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        errors.append(f"{label} cannot be in the future")


def _privacy(value: Any, errors: list[str], location: str = "ledger") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in SENSITIVE_KEYS:
                errors.append(f"{location}.{key} is a private tracked field")
            _privacy(child, errors, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _privacy(child, errors, f"{location}[{index}]")
    elif isinstance(value, str) and (PRIVATE_ID.search(value) or PRIVATE_PATH.search(value)):
        errors.append(f"{location} contains private content")


def validate_carabellese_cleanup_ledger(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"ledger unreadable: {exc}"]
    if not isinstance(payload, dict):
        return ["ledger must be an object"]
    errors: list[str] = []
    _privacy(payload, errors)
    top = {"schema_version", "workflow_id", "capability_default",
           "automated_evidence", "workstation_gates"}
    if set(payload) != top:
        errors.append("ledger fields are incomplete or unknown")
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("workflow_id") != "CARABELLESE_YOUTUBE_CLEANUP":
        errors.append("workflow_id is invalid")
    if payload.get("capability_default") is not False:
        errors.append("capability_default must be false")
    automated = payload.get("automated_evidence")
    automated_keys = {"result", "observed_at", "repository_commit", "contract_digest",
                      "test_results", "limitations"}
    if not isinstance(automated, dict) or set(automated) != automated_keys:
        errors.append("automated_evidence has invalid fields")
    else:
        if automated["result"] != "PASS":
            errors.append("automated_evidence.result must be PASS")
        _timestamp(automated["observed_at"], "automated_evidence.observed_at", errors)
        if not isinstance(automated["repository_commit"], str) or not re.fullmatch(
                r"[0-9a-f]{40}", automated["repository_commit"]):
            errors.append("repository_commit must be a full commit")
        if not isinstance(automated["contract_digest"], str) or not re.fullmatch(
                r"[0-9a-f]{64}", automated["contract_digest"]):
            errors.append("contract_digest must be SHA-256")
        for field in ("test_results", "limitations"):
            if not isinstance(automated[field], list) or not automated[field]:
                errors.append(f"automated_evidence.{field} must be non-empty")
    gates = payload.get("workstation_gates")
    if not isinstance(gates, dict) or set(gates) != WORKSTATIONS:
        errors.append("workstation_gates must contain exactly both PCs")
        return errors
    for workstation in sorted(WORKSTATIONS):
        gate = gates[workstation]; location = f"workstation_gates.{workstation}"
        expected = {"workstation_id", "status", "checks", "evidence", "limitations"}
        if not isinstance(gate, dict) or set(gate) != expected:
            errors.append(f"{location} has invalid fields"); continue
        if gate["workstation_id"] != workstation:
            errors.append(f"{location}.workstation_id is invalid")
        if gate["status"] not in {"PENDING", "VALIDATED", "FAILED", "UNSUPPORTED"}:
            errors.append(f"{location}.status is unsupported")
        checks = gate["checks"]
        if not isinstance(checks, dict) or set(checks) != CHECKS or any(
                value not in {"PENDING", "PASS", "FAIL", "UNSUPPORTED"}
                for value in checks.values()):
            errors.append(f"{location}.checks are invalid")
        evidence = gate["evidence"]
        if not isinstance(evidence, list):
            errors.append(f"{location}.evidence must be a list"); evidence = []
        for index, item in enumerate(evidence):
            label = f"{location}.evidence[{index}]"
            fields = {"evidence_id", "workstation_id", "observed_at", "result",
                      "checks", "limitations"}
            if not isinstance(item, dict) or set(item) != fields:
                errors.append(f"{label} has invalid fields"); continue
            if item["workstation_id"] != workstation:
                errors.append(f"{label} cannot validate another workstation")
            _timestamp(item["observed_at"], f"{label}.observed_at", errors)
            if item["result"] not in {"PASS", "FAIL", "UNSUPPORTED"}:
                errors.append(f"{label}.result is invalid")
            if not isinstance(item["checks"], list) or set(item["checks"]) - CHECKS:
                errors.append(f"{label}.checks are invalid")
            if not isinstance(item["limitations"], list) or not item["limitations"]:
                errors.append(f"{label}.limitations are required")
        if gate["status"] == "VALIDATED":
            if not isinstance(checks, dict) or any(checks.get(name) != "PASS" for name in CHECKS):
                errors.append(f"{location} VALIDATED requires every check PASS")
            if not any(isinstance(item, dict) and item.get("workstation_id") == workstation
                       and item.get("result") == "PASS"
                       and set(item.get("checks", [])) == CHECKS for item in evidence):
                errors.append(f"{location} requires complete same-workstation evidence")
        if not isinstance(gate["limitations"], list) or not gate["limitations"]:
            errors.append(f"{location}.limitations must be non-empty")
    return errors


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Validate Carabellese cleanup rollout evidence.")
    parser.add_argument("--ledger", type=Path,
                        default=repo / "validation" / "carabellese-cleanup-ledger.json")
    args = parser.parse_args()
    errors = validate_carabellese_cleanup_ledger(args.ledger)
    if errors:
        for error in errors: print(f"ERROR: {error}")
        return 1
    print("CARABELLESE CLEANUP LEDGER: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
