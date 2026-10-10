from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.resolve_connection import context, safe_call
from bridge.vertical_social_music import apply_music_duck


def main() -> int:
    _, _, project, timeline, error = context()
    if error:
        raise RuntimeError(error)
    project_name = str(safe_call(project, "GetName") or "")
    timeline_name = str(safe_call(timeline, "GetName") or "")
    if not project_name.startswith("ARPHE_VERTICAL_CUT_NATIVE_GATE_"):
        raise RuntimeError("Gate rifiutato: il progetto corrente non è il progetto sintetico Vertical Social")
    if not timeline_name.startswith("__ARPHE_VERTICAL_"):
        raise RuntimeError("Gate rifiutato: la timeline corrente non è provvisoria Vertical Social")
    items = safe_call(timeline, "GetItemListInTrack", "audio", 1) or []
    if not items:
        raise RuntimeError("Gate rifiutato: nessuna clip audio sintetica")
    item = items[0]
    start, end = safe_call(item, "GetStart"), safe_call(item, "GetEnd")
    original = safe_call(item, "GetProperty", "AudioVolume")
    if not isinstance(original, (int, float)):
        raise RuntimeError("AudioVolume originale non leggibile")
    action = {"action_id": "native-music-gate", "type": "MUSIC_DUCK", "state": "APPROVED",
              "range": {"start_frame": int(start), "end_frame": int(end)},
              "audio_track": 1, "gain_db": -12.0, "reason": "gate sintetico reversibile"}
    result = None
    try:
        result = apply_music_duck(timeline, action, int(safe_call(timeline, "GetEndFrame") or end))
    finally:
        if not safe_call(item, "SetProperty", "AudioVolume", float(original)):
            raise RuntimeError("Ripristino AudioVolume originale fallito")
    restored = safe_call(item, "GetProperty", "AudioVolume")
    if abs(float(restored) - float(original)) >= 0.001:
        raise RuntimeError("Read-back AudioVolume originale dopo restore non corrispondente")
    print(json.dumps({"ok": True, "project": project_name, "timeline": timeline_name,
                      "applied": result, "restored_audio_volume": restored}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
