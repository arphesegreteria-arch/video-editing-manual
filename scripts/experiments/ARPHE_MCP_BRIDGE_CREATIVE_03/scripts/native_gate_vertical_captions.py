from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.config import load_config  # noqa: E402
from bridge.resolve_connection import context, safe_call  # noqa: E402
from bridge.vertical_social_captions import apply_caption_action, timeline_edit_fingerprint  # noqa: E402


def main() -> int:
    _, _, project, original, error = context()
    if error:
        raise RuntimeError(error)
    project_name = str(safe_call(project, "GetName") or "")
    if not project_name.startswith("ARPHE_VERTICAL_CUT_NATIVE_GATE_"):
        raise RuntimeError("Gate rifiutato: progetto corrente non sintetico")
    config = load_config(Path("C:/ARPHE/MCP/ARPHE_WINDOWS_BRIDGE_RUNTIME_V1/runtime-configs/PC_PERSONALE/creative_config.json"))
    if config.workstation_id != "PC_PERSONALE":
        raise RuntimeError("Gate rifiutato: config diversa da PC_PERSONALE")
    pool = safe_call(project, "GetMediaPool")
    timeline = safe_call(pool, "CreateEmptyTimeline", "__ARPHE_VERTICAL_CAPTIONS_NATIVE_GATE")
    if timeline is None or not safe_call(project, "SetCurrentTimeline", timeline):
        raise RuntimeError("Creazione timeline sintetica CAPTIONS fallita")
    locked_edit_fingerprint = timeline_edit_fingerprint(timeline)
    action = {"action_id": "captions-gate", "type": "CAPTIONS", "state": "APPROVED",
              "locked_edit_fingerprint": locked_edit_fingerprint, "reason": "gate sintetico",
              "cues": [
                  {"cue_id": "c1", "start_frame": 0, "end_frame": 20,
                   "text": "Prima frase", "position": "LOWER"},
                  {"cue_id": "c2", "start_frame": 30, "end_frame": 60,
                   "text": "Seconda frase", "position": "UPPER"},
              ]}
    result = None
    try:
        result = apply_caption_action(project, timeline, config, action, 60)
    finally:
        safe_call(project, "SetCurrentTimeline", original)
        if not safe_call(pool, "DeleteTimelines", [timeline]):
            raise RuntimeError("Rollback timeline sintetica CAPTIONS fallito")
    print(json.dumps({"ok": True, "project": project_name,
                      "locked_edit_fingerprint": locked_edit_fingerprint, "result": result,
                      "rollback": "temporary timeline deleted"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
