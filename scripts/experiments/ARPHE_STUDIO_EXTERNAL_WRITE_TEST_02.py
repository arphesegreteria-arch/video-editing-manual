# -*- coding: utf-8 -*-
"""External Resolve Studio write probe: create one empty timeline, then return to original."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPORT = SCRIPT_DIR / "ARPHE_STUDIO_API_WRITE_DIAGNOSTIC.json"

programdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
programfiles = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
root = programdata / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
modules = root / "Modules"
dlls = [
    programfiles / "Blackmagic Design" / "DaVinci Resolve" / "fusionscript.dll",
    programfiles / "Blackmagic Design" / "DaVinci Resolve Studio" / "fusionscript.dll",
]

if modules.exists() and str(modules) not in sys.path:
    sys.path.insert(0, str(modules))
os.environ.setdefault("RESOLVE_SCRIPT_API", str(root))
if not os.environ.get("RESOLVE_SCRIPT_LIB"):
    for dll in dlls:
        if dll.exists():
            os.environ["RESOLVE_SCRIPT_LIB"] = str(dll)
            break


def main() -> int:
    import DaVinciResolveScript as dvr

    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("Connessione a Resolve fallita.")

    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    if not project:
        raise RuntimeError("Nessun progetto aperto.")

    original = project.GetCurrentTimeline()
    if not original:
        raise RuntimeError("Nessuna timeline attiva.")

    original_name = original.GetName()
    before = project.GetTimelineCount()
    media_pool = project.GetMediaPool()
    if not media_pool:
        raise RuntimeError("MediaPool non disponibile.")

    test_name = "ARPHE_API_WRITE_TEST_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    created = media_pool.CreateEmptyTimeline(test_name)
    if not created:
        raise RuntimeError("CreateEmptyTimeline ha fallito.")

    after = project.GetTimelineCount()
    back_ok = project.SetCurrentTimeline(original)
    final = project.GetCurrentTimeline()
    final_name = final.GetName() if final else None

    data = {
        "format": "ARPHE_STUDIO_EXTERNAL_WRITE_TEST_V1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "SUCCESS" if final_name == original_name else "PARTIAL",
        "project": project.GetName(),
        "original_timeline": original_name,
        "test_timeline": created.GetName(),
        "timeline_count_before": before,
        "timeline_count_after": after,
        "returned_to_original": bool(back_ok),
        "current_timeline_final": final_name,
    }
    REPORT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(data, ensure_ascii=False, indent=2))
    if final_name != original_name:
        raise RuntimeError("Timeline test creata, ma ritorno all'originale fallito.")

    print("TEST 02 SUPERATO: scrittura esterna non distruttiva funzionante.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
