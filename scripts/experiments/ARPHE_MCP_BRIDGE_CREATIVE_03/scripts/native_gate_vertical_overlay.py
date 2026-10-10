from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.config import load_config  # noqa: E402
from bridge.resolve_connection import context, safe_call  # noqa: E402
from bridge.vertical_social_overlay import apply_graphic_or_cta  # noqa: E402


def main() -> int:
    _, _, project, original, error = context()
    if error:
        raise RuntimeError(error)
    project_name = str(safe_call(project, "GetName") or "")
    if not project_name.startswith("ARPHE_VERTICAL_CUT_NATIVE_GATE_"):
        raise RuntimeError("Gate rifiutato: progetto corrente non sintetico")
    pool = safe_call(project, "GetMediaPool")
    name = "__ARPHE_VERTICAL_OVERLAY_NATIVE_GATE"
    timeline = safe_call(pool, "CreateEmptyTimeline", name)
    if timeline is None or not safe_call(project, "SetCurrentTimeline", timeline):
        raise RuntimeError("Creazione timeline sintetica overlay fallita")
    config = load_config(Path("C:/ARPHE/MCP/ARPHE_WINDOWS_BRIDGE_RUNTIME_V1/runtime-configs/PC_PERSONALE/creative_config.json"))
    if config.workstation_id != "PC_PERSONALE":
        raise RuntimeError("Gate rifiutato: config diversa da PC_PERSONALE")
    results = []
    try:
        graphic = {"action_id": "graphic-gate", "type": "GRAPHIC", "state": "APPROVED",
                   "graphic_kind": "TITLE", "text": "Titolo di prova", "style_role": "cream",
                   "range": {"start_frame": 0, "end_frame": 30}, "reason": "gate sintetico"}
        cta = {"action_id": "cta-gate", "type": "CTA", "state": "APPROVED",
               "headline": "Prenota una visita", "text": "Contattaci", "style_role": "burgundy",
               "range": {"start_frame": 30, "end_frame": 90}, "reason": "gate sintetico"}
        results.append(apply_graphic_or_cta(project, timeline, config, graphic, 90))
        results.append(apply_graphic_or_cta(project, timeline, config, cta, 90))
    finally:
        safe_call(project, "SetCurrentTimeline", original)
        if not safe_call(pool, "DeleteTimelines", [timeline]):
            raise RuntimeError("Rollback timeline sintetica overlay fallito")
    print(json.dumps({"ok": True, "project": project_name, "results": results,
                      "rollback": "temporary timeline deleted"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
