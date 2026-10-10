from __future__ import annotations

import json
from pathlib import Path


def validate_branded_longform_ledger(path: Path) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"ledger unreadable: {exc}"]
    errors: list[str] = []
    if value.get("schema_version") != 1: errors.append("schema_version")
    if value.get("workflow_id") != "BRANDED_LONGFORM_EDITORIAL": errors.append("workflow_id")
    if value.get("capability_default") is not False: errors.append("capability_default")
    if value.get("automated_evidence", {}).get("result") != "PASS": errors.append("automated_evidence")
    gates = value.get("workstation_gates", {})
    for workstation in ("PC_PERSONALE", "PC_SEGRETERIA"):
        gate = gates.get(workstation)
        if not isinstance(gate, dict) or gate.get("workstation_id") != workstation:
            errors.append(f"gate:{workstation}")
        elif gate.get("status") not in {"PENDING", "VALIDATED"}:
            errors.append(f"status:{workstation}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ledger = root / "validation" / "branded-longform-ledger.json"
    errors = validate_branded_longform_ledger(ledger)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "ledger": str(ledger)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
