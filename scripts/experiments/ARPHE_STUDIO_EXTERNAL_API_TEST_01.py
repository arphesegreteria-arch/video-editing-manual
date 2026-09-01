# -*- coding: utf-8 -*-
"""Read-only test: external Python -> DaVinci Resolve Studio."""

import json
import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE / "ARPHE_STUDIO_API_DIAGNOSTIC.json"
PROGRAMDATA = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
PROGRAMFILES = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
API_ROOT = PROGRAMDATA / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Developer" / "Scripting"
MODULES = API_ROOT / "Modules"
LIB_CANDIDATES = [
    PROGRAMFILES / "Blackmagic Design" / "DaVinci Resolve" / "fusionscript.dll",
    PROGRAMFILES / "Blackmagic Design" / "DaVinci Resolve Studio" / "fusionscript.dll",
]


def safe(obj, name, *args):
    try:
        fn = getattr(obj, name, None)
        return fn(*args) if callable(fn) else None
    except Exception:
        return None


def save(report):
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    print("=" * 72)
    print("ARPHE - RESOLVE STUDIO EXTERNAL API TEST 01")
    print("READ-ONLY: non modifica nulla")
    print("=" * 72)

    report = {
        "format": "ARPHE_STUDIO_EXTERNAL_API_DIAGNOSTIC_V1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "api_root": str(API_ROOT),
        "modules_path": str(MODULES),
        "modules_exists": MODULES.exists(),
    }

    if MODULES.exists() and str(MODULES) not in sys.path:
        sys.path.insert(0, str(MODULES))
    os.environ.setdefault("RESOLVE_SCRIPT_API", str(API_ROOT))

    selected_lib = None
    for p in LIB_CANDIDATES:
        if p.exists():
            selected_lib = p
            break
    if selected_lib:
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", str(selected_lib))
    report["resolve_script_lib"] = os.environ.get("RESOLVE_SCRIPT_LIB")

    print("\n[1/4] Importo DaVinciResolveScript...")
    try:
        import DaVinciResolveScript as dvr
    except Exception as exc:
        report["status"] = "IMPORT_FAILED"
        report["error"] = f"{type(exc).__name__}: {exc}"
        save(report)
        print("IMPORT FALLITO")
        print(report["error"])
        print("Controlla che esista:")
        print(MODULES / "DaVinciResolveScript.py")
        print("Report:", REPORT)
        return 10

    print("OK")
    print("\n[2/4] Connessione a Resolve Studio...")
    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        report["status"] = "CONNECTION_FAILED"
        save(report)
        print("CONNESSIONE FALLITA")
        print("- Resolve Studio deve essere aperto")
        print("- abilita External scripting / Local nelle Preferences, se presente")
        print("- riavvia Resolve e rilancia il test")
        print("Report:", REPORT)
        return 20

    print("CONNESSO")
    print("\n[3/4] Leggo progetto e timeline...")
    pm = safe(resolve, "GetProjectManager")
    project = safe(pm, "GetCurrentProject")
    timeline = safe(project, "GetCurrentTimeline") if project else None

    info = {
        "resolve_version": safe(resolve, "GetVersionString") or safe(resolve, "GetVersion"),
        "project_name": safe(project, "GetName") if project else None,
        "timeline_name": safe(timeline, "GetName") if timeline else None,
        "timeline_fps": safe(timeline, "GetSetting", "timelineFrameRate") if timeline else None,
        "timeline_playback_fps": safe(timeline, "GetSetting", "timelinePlaybackFrameRate") if timeline else None,
        "video_track_count": safe(timeline, "GetTrackCount", "video") if timeline else None,
        "audio_track_count": safe(timeline, "GetTrackCount", "audio") if timeline else None,
    }

    try:
        info["v1_clip_count"] = len(timeline.GetItemListInTrack("video", 1) or []) if timeline else None
    except Exception:
        info["v1_clip_count"] = None
    try:
        info["a1_clip_count"] = len(timeline.GetItemListInTrack("audio", 1) or []) if timeline else None
    except Exception:
        info["a1_clip_count"] = None

    report.update(info)
    report["status"] = "SUCCESS"

    print("Resolve:", info["resolve_version"])
    print("Project:", info["project_name"])
    print("Timeline:", info["timeline_name"])
    print("FPS:", info["timeline_fps"])
    print("Video tracks:", info["video_track_count"])
    print("Audio tracks:", info["audio_track_count"])
    print("Clip V1:", info["v1_clip_count"])
    print("Clip A1:", info["a1_clip_count"])

    print("\n[4/4] Salvo report...")
    save(report)
    print("Report:", REPORT)
    print("\nTEST SUPERATO: Python esterno -> Resolve Studio funziona.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        try:
            save({
                "format": "ARPHE_STUDIO_EXTERNAL_API_DIAGNOSTIC_V1",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "status": "UNHANDLED_EXCEPTION",
                "traceback": traceback.format_exc(),
            })
        except Exception:
            pass
        raise
