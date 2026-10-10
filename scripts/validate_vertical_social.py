from __future__ import annotations
import json
from pathlib import Path


def validate_vertical_social_ledger(path: Path) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"ledger unreadable: {exc}"]
    errors: list[str] = []
    if value.get("schema_version") != 1: errors.append("schema_version")
    if value.get("workflow_id") != "ARPHE_VERTICAL_SOCIAL": errors.append("workflow_id")
    if value.get("capability_default") is not False: errors.append("capability_default")
    if value.get("automated_evidence", {}).get("result") != "PASS": errors.append("automated_evidence")
    gates = value.get("workstation_gates", {})
    for name in ("PC_PERSONALE", "PC_SEGRETERIA"):
        gate = gates.get(name)
        if not isinstance(gate, dict) or gate.get("workstation_id") != name: errors.append(f"gate:{name}")
        elif gate.get("status") not in {"PENDING", "VALIDATED"}: errors.append(f"status:{name}")
    return errors

