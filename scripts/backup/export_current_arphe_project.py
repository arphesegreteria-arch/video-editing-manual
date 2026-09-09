from __future__ import annotations

import json
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_ROOT = REPO_ROOT / "scripts" / "experiments" / "ARPHE_MCP_BRIDGE_CREATIVE_03"
sys.path.insert(0, str(BRIDGE_ROOT))

from bridge.resolve_connection import context, safe_call  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"ok": False, "error": "Destinazione richiesta"}))
        return 2
    output_dir = Path(sys.argv[1]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _, manager, project, _, error = context()
    if error or manager is None or project is None:
        print(json.dumps({"ok": False, "error": error or "Resolve/progetto non raggiungibile"}))
        return 3
    name = str(safe_call(project, "GetName") or "")
    if not name.startswith("ARPHE_"):
        print(json.dumps({"ok": False, "error": "Il progetto corrente non è ARPHE_", "project": name}))
        return 4
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:100]
    destination = output_dir / f"{safe_name}.drp"
    if destination.exists():
        print(json.dumps({"ok": False, "error": "Export già esistente"}))
        return 5
    ok = bool(safe_call(manager, "ExportProject", name, str(destination), True))
    if not ok or not destination.is_file():
        print(json.dumps({"ok": False, "error": "ExportProject fallito", "project": name}))
        return 6
    print(json.dumps({"ok": True, "project": name, "file": destination.name,
                      "size_bytes": destination.stat().st_size}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
