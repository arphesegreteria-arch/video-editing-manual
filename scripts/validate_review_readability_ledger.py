from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any


KINDS = {
    "AUTOMATED": None,
    "PC_PERSONALE_LIVE": "PC_PERSONALE",
    "PC_SEGRETERIA_LIVE": "PC_SEGRETERIA",
}
RESULTS = {"PASS", "FAIL", "PENDING"}
ENTRY_KEYS = {
    "evidence_id",
    "kind",
    "workstation_id",
    "video_repository_commit",
    "graphic_kit_repository_commit",
    "policy_version",
    "policy_digest",
    "observed_at",
    "result",
    "limitations",
    "current_state_reference",
    "validated_workstations",
}
RAW_REVIEW_KEYS = {"review", "reviews", "review_text", "raw_text", "text", "content"}


def _contains_raw_review_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in RAW_REVIEW_KEYS or _contains_raw_review_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_raw_review_key(child) for child in value)
    return False


def _is_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_readability_ledger(path: Path, current_state: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"ledger unreadable: {exc}"]
    try:
        state_text = current_state.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"current state unreadable: {exc}"]

    if not isinstance(payload, dict):
        return ["ledger must be an object"]
    if set(payload) != {"schema_version", "evidence"}:
        errors.append("ledger keys must be exactly schema_version and evidence")
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    entries = payload.get("evidence")
    if not isinstance(entries, list):
        return errors + ["evidence must be a list"]

    seen_ids: set[str] = set()
    seen_kinds: list[str] = []
    expected_versions: set[str] = set()
    expected_digests: set[str] = set()
    video_commits: set[str] = set()
    graphic_commits: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"evidence[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} must be an object")
            continue
        if _contains_raw_review_key(entry):
            errors.append(f"{prefix} contains raw review content")
        missing = ENTRY_KEYS - set(entry)
        unknown = set(entry) - ENTRY_KEYS
        if missing:
            errors.append(f"{prefix} missing fields: {sorted(missing)}")
        if unknown:
            errors.append(f"{prefix} unknown fields: {sorted(unknown)}")

        evidence_id = entry.get("evidence_id")
        if not isinstance(evidence_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,79}", evidence_id):
            errors.append(f"{prefix}.evidence_id is invalid")
        elif evidence_id in seen_ids:
            errors.append(f"{prefix}.evidence_id is duplicated")
        else:
            seen_ids.add(evidence_id)

        kind = entry.get("kind")
        if kind not in KINDS:
            errors.append(f"{prefix}.kind is invalid")
            expected_workstation = None
        else:
            seen_kinds.append(kind)
            expected_workstation = KINDS[kind]
        workstation = entry.get("workstation_id")
        if workstation != expected_workstation:
            errors.append(f"{prefix}.workstation_id must be {expected_workstation!r} for {kind}")

        video_commit = entry.get("video_repository_commit")
        graphic_commit = entry.get("graphic_kit_repository_commit")
        digest = entry.get("policy_digest")
        version = entry.get("policy_version")
        if not _is_hex(video_commit, 40):
            errors.append(f"{prefix}.video_repository_commit must be an exact 40-character commit")
        else:
            video_commits.add(video_commit)
        if not _is_hex(graphic_commit, 40):
            errors.append(f"{prefix}.graphic_kit_repository_commit must be an exact 40-character commit")
        else:
            graphic_commits.add(graphic_commit)
        if not _is_hex(digest, 64):
            errors.append(f"{prefix}.policy_digest must be an exact SHA-256 digest")
        else:
            expected_digests.add(digest)
        if version != "ARPHE_VIDEO_READABILITY_V1":
            errors.append(f"{prefix}.policy_version is invalid")
        else:
            expected_versions.add(version)
        if not _valid_timestamp(entry.get("observed_at")):
            errors.append(f"{prefix}.observed_at must be an ISO-8601 timestamp with timezone")

        result = entry.get("result")
        if result not in RESULTS:
            errors.append(f"{prefix}.result is invalid")
        limitations = entry.get("limitations")
        if not isinstance(limitations, list) or not limitations or not all(
            isinstance(item, str) and item.strip() for item in limitations
        ):
            errors.append(f"{prefix}.limitations must be a non-empty string list")

        reference = entry.get("current_state_reference")
        if not isinstance(reference, str) or not reference.startswith("CURRENT_STATE.md#"):
            errors.append(f"{prefix}.current_state_reference is invalid")
        else:
            anchor = reference.split("#", 1)[1]
            if not anchor or anchor not in state_text:
                errors.append(f"{prefix}.current_state_reference is not present in CURRENT_STATE.md")

        validated = entry.get("validated_workstations")
        if not isinstance(validated, list) or any(item not in {"PC_PERSONALE", "PC_SEGRETERIA"} for item in validated):
            errors.append(f"{prefix}.validated_workstations is invalid")
        elif kind == "AUTOMATED" and validated:
            errors.append(f"{prefix} automated evidence cannot validate a workstation")
        elif kind in KINDS and kind != "AUTOMATED":
            if any(item != expected_workstation for item in validated):
                errors.append(f"{prefix} cannot validate another workstation")
            expected_validated = [expected_workstation] if result == "PASS" else []
            if validated != expected_validated:
                errors.append(f"{prefix}.validated_workstations must be {expected_validated!r} for result {result}")

    if sorted(seen_kinds) != sorted(KINDS):
        errors.append("evidence must contain exactly one AUTOMATED, PC_PERSONALE_LIVE and PC_SEGRETERIA_LIVE entry")
    for label, values in (
        ("video_repository_commit", video_commits),
        ("graphic_kit_repository_commit", graphic_commits),
        ("policy_version", expected_versions),
        ("policy_digest", expected_digests),
    ):
        if len(values) > 1:
            errors.append(f"all evidence entries must use the same {label}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the ARPHE review-readability evidence ledger.")
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--current-state", type=Path, required=True)
    args = parser.parse_args()
    errors = validate_readability_ledger(args.ledger, args.current_state)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("REVIEW READABILITY LEDGER: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
