from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def write_audit(path: Path, action: str, result: dict[str, Any]) -> None:
    """Write metadata only: never inputs, text, paths, environment, or credentials."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bridge": "ARPHE_MCP_BRIDGE_CREATIVE_03",
        "action": action,
        "ok": bool(result.get("ok")),
        "stage": result.get("stage"),
        "error_type": result.get("error_type"),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n")
