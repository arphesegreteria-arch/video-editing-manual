from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any


WORKSTATIONS = {"PC_PERSONALE", "PC_SEGRETERIA"}
CHECKS = {
    "marker_pairs", "complete_review", "cut_outputs", "partial_failure_resume",
    "duration_limit", "cleanup", "rollback_flag",
}
SENSITIVE_KEYS = {
    "human_reason", "reason", "start_anchor", "end_anchor", "source_path", "source_name",
    "reviewer", "review_text", "transcript", "quote", "project_name", "timeline_name",
}
JOB_ID = re.compile(r"editorial_[0-9a-f]{16}", re.IGNORECASE)
PATH_TEXT = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|var|tmp)/)", re.IGNORECASE)


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


def _sensitive(value: Any, errors: list[str], path: str = "ledger") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in SENSITIVE_KEYS:
                errors.append(f"{path}.{key} is a sensitive tracked field")
            _sensitive(child, errors, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _sensitive(child, errors, f"{path}[{index}]")
    elif isinstance(value, str) and (JOB_ID.search(value) or PATH_TEXT.search(value)):
        errors.append(f"{path} contains sensitive content")


def validate_editorial_selection_ledger(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"ledger unreadable: {exc}"]
    if not isinstance(payload, dict):
        return ["ledger must be an object"]
    errors: list[str] = []
    _sensitive(payload, errors)
    expected_top = {
        "schema_version", "workflow_id", "capability_default",
        "automated_evidence", "workstation_gates",
    }
    if set(payload) != expected_top:
        errors.append(f"ledger fields must be exactly {sorted(expected_top)}")
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("workflow_id") != "ARPHE_PODCAST_REELS_CTA":
        errors.append("workflow_id is invalid")
    if payload.get("capability_default") is not False:
        errors.append("capability_default must be false")
    automated = payload.get("automated_evidence")
    automated_keys = {
        "result", "observed_at", "repository_commit", "contract_digest",
        "test_results", "limitations",
    }
    if not isinstance(automated, dict) or set(automated) != automated_keys:
        errors.append("automated_evidence has invalid fields")
    else:
        if automated["result"] != "PASS":
            errors.append("automated_evidence.result must be PASS")
        _timestamp(automated["observed_at"], "automated_evidence.observed_at", errors)
        if not isinstance(automated["repository_commit"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", automated["repository_commit"]
        ):
            errors.append("automated_evidence.repository_commit must be a full commit")
        if not isinstance(automated["contract_digest"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", automated["contract_digest"]
        ):
            errors.append("automated_evidence.contract_digest must be SHA-256")
        for field in ("test_results", "limitations"):
            values = automated[field]
            if not isinstance(values, list) or not values or not all(
                isinstance(item, str) and item.strip() for item in values
            ):
                errors.append(f"automated_evidence.{field} must be a non-empty string list")
    gates = payload.get("workstation_gates")
    if not isinstance(gates, dict) or set(gates) != WORKSTATIONS:
        errors.append("workstation_gates must contain exactly PC_PERSONALE and PC_SEGRETERIA")
        return errors
    for workstation in sorted(WORKSTATIONS):
        gate = gates[workstation]
        prefix = f"workstation_gates.{workstation}"
        expected_gate = {"workstation_id", "status", "checks", "evidence", "limitations"}
        if not isinstance(gate, dict) or set(gate) != expected_gate:
            errors.append(f"{prefix} has invalid fields")
            continue
        if gate["workstation_id"] != workstation:
            errors.append(f"{prefix}.workstation_id is invalid")
        if gate["status"] not in {"PENDING", "VALIDATED", "FAILED"}:
            errors.append(f"{prefix}.status is unsupported")
        checks = gate["checks"]
        if not isinstance(checks, dict) or set(checks) != CHECKS or any(
            result not in {"PENDING", "PASS", "FAIL"} for result in checks.values()
        ):
            errors.append(f"{prefix}.checks are invalid")
        evidence = gate["evidence"]
        if not isinstance(evidence, list):
            errors.append(f"{prefix}.evidence must be a list")
            evidence = []
        for index, item in enumerate(evidence):
            label = f"{prefix}.evidence[{index}]"
            expected_evidence = {
                "evidence_id", "workstation_id", "observed_at", "result", "checks", "limitations",
            }
            if not isinstance(item, dict) or set(item) != expected_evidence:
                errors.append(f"{label} has invalid fields")
                continue
            if item["workstation_id"] != workstation:
                errors.append(f"{label} cannot validate another workstation")
            _timestamp(item["observed_at"], f"{label}.observed_at", errors)
            if item["result"] not in {"PASS", "FAIL"}:
                errors.append(f"{label}.result is invalid")
            if not isinstance(item["checks"], list) or set(item["checks"]) - CHECKS:
                errors.append(f"{label}.checks are invalid")
            if not isinstance(item["limitations"], list) or not item["limitations"]:
                errors.append(f"{label}.limitations are required")
        if gate["status"] == "VALIDATED":
            if not isinstance(checks, dict) or any(checks.get(name) != "PASS" for name in CHECKS):
                errors.append(f"{prefix} VALIDATED requires every check PASS")
            if not evidence or not any(
                isinstance(item, dict) and item.get("workstation_id") == workstation
                and item.get("result") == "PASS" and set(item.get("checks", [])) == CHECKS
                for item in evidence
            ):
                errors.append(f"{prefix} VALIDATED requires complete same-workstation live evidence")
        limitations = gate["limitations"]
        if not isinstance(limitations, list) or not limitations or not all(
            isinstance(item, str) and item.strip() for item in limitations
        ):
            errors.append(f"{prefix}.limitations must be a non-empty string list")
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Validate ARPHE editorial-selection rollout evidence.")
    parser.add_argument("--ledger", type=Path,
                        default=repo_root / "validation" / "editorial-selection-ledger.json")
    args = parser.parse_args()
    errors = validate_editorial_selection_ledger(args.ledger)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("EDITORIAL SELECTION LEDGER: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
