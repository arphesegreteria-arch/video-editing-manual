from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_PATH = Path(
    "C:/ARPHE/MCP/ARPHE_WINDOWS_BRIDGE_RUNTIME_V1/"
    "runtime-configs/PC_PERSONALE/creative_config.json"
)
os.environ["ARPHE_CREATIVE_CONFIG"] = str(CONFIG_PATH)

from bridge import server  # noqa: E402
from bridge.config import load_config  # noqa: E402
from bridge.resolve_connection import safe_call  # noqa: E402


PROJECT_NAME = "ARPHE_COLORIST_GATE_20261024_1401"
ORIGINAL_PROJECT = "ARPHE_PEELING_ADV_TEST_20261023"
ORIGINAL_TIMELINE = "__ARPHE_VERTICAL_VERTICAL_9957F4FFC8BC43E0B5B333FF4B4BFC03"
ASSET_ROOT = Path("C:/ARPHE/MCP/assets/creative/colorist-gate-20261024-1401")


def require_ok(result: dict, action: str) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{action} failed: {json.dumps(result, ensure_ascii=False)}")
    return result


def require_personal_config() -> None:
    config = load_config(CONFIG_PATH)
    if config.workstation_id != "PC_PERSONALE":
        raise RuntimeError("Gate rifiutato: config diversa da PC_PERSONALE")


def disable_colorist_gate() -> dict:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    if raw.get("workstation_id") != "PC_PERSONALE":
        raise RuntimeError("Chiusura gate rifiutata: config diversa da PC_PERSONALE")
    flags = raw.get("feature_flags")
    if not isinstance(flags, dict) or not isinstance(flags.get("CAP_COLORIST"), bool):
        raise RuntimeError("Chiusura gate rifiutata: CAP_COLORIST assente o non booleana")
    flags["CAP_COLORIST"] = False
    temporary = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".colorist-gate.tmp")
    temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, CONFIG_PATH)
    require_personal_config()
    verified = load_config(CONFIG_PATH)
    if verified.flags.get("CAP_COLORIST") is not False:
        raise RuntimeError("Chiusura gate non verificata: CAP_COLORIST non e' false")
    return {"workstation_id": verified.workstation_id, "CAP_COLORIST": False}


def setup() -> dict:
    require_ok(server.set_current_project(PROJECT_NAME), "set_current_project")
    timeline_name = "ARPHE_COLORIST_VISUAL_REVIEW_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    require_ok(server.create_timeline(timeline_name, 1920, 1080, 30.0), "create_timeline")
    status = require_ok(server.get_creative_status(), "get_creative_status")
    timeline_start = int(status["start_frame"])

    # Resolve 21.1.1 applies the local 150-frame standard-still duration when
    # appending a one-frame PNG. The bridge still verifies the returned range.
    first_end = timeline_start + 150
    second_end = first_end + 150
    require_ok(
        server.add_image_asset(str(ASSET_ROOT / "camera_a_warm_over.png"), timeline_start, first_end),
        "add_first_image",
    )
    require_ok(
        server.add_image_asset(str(ASSET_ROOT / "camera_b_cool_under.png"), first_end, second_end),
        "add_second_image",
    )

    context = require_ok(server.inspect_colorist_context(), "inspect_colorist_context")
    clips = context["clips"]
    if len(clips) != 2:
        raise RuntimeError(f"Expected two clips, found {len(clips)}")
    clip_ids = [item["clip_id"] for item in clips]
    prepared = require_ok(
        server.prepare_colorist_plan(
            clip_ids,
            clip_ids[0],
            {
                "temperature": -0.35,
                "tint": 0.04,
                "exposure_stops": -0.18,
                "contrast": 0.12,
                "saturation": 0.96,
            },
            "ARPHE_CLEAN_NEUTRAL",
            None,
        ),
        "prepare_colorist_plan",
    )
    require_ok(
        server.approve_colorist_plan(
            prepared["colorist_job_id"], prepared["plan_fingerprint"], "COLORIST"
        ),
        "approve_colorist_plan",
    )
    applied = require_ok(
        server.apply_colorist_plan(prepared["colorist_job_id"]), "apply_colorist_plan"
    )
    saved = require_ok(server.save_project(), "save_project")
    final_status = require_ok(server.get_creative_status(), "get_creative_status_after_apply")
    return {
        "ok": True,
        "project": PROJECT_NAME,
        "timeline": timeline_name,
        "timeline_start": timeline_start,
        "clip_ids": clip_ids,
        "colorist_job_id": prepared["colorist_job_id"],
        "apply_evidence": applied.get("evidence"),
        "saved": saved,
        "status": final_status,
        "human_review": "PENDING",
    }


def preview(job_id: str, clip_id: str, side: str) -> dict:
    require_ok(server.set_current_project(PROJECT_NAME), "set_current_project")
    result = require_ok(server.preview_colorist_version(job_id, clip_id, side), "preview")
    resolve, _, _, timeline, _, _, runtime_error = server._runtime()
    if runtime_error:
        raise RuntimeError(str(runtime_error))
    if safe_call(timeline, "SetCurrentTimecode", "01:00:02:00") is not True:
        raise RuntimeError("Unable to position playhead for visual review")
    safe_call(resolve, "OpenPage", "color")
    return {"ok": True, "preview": result}


def restore(job_id: str, clip_id: str) -> dict:
    require_ok(server.set_current_project(PROJECT_NAME), "set_current_project")
    result = require_ok(server.restore_colorist_preview(job_id, clip_id), "restore")
    require_ok(server.save_project(), "save_project")
    return {"ok": True, "restore": result}


def finish(job_id: str, clip_id: str) -> dict:
    restored = None
    original = None
    try:
        restored = restore(job_id, clip_id)
        require_ok(server.set_current_project(ORIGINAL_PROJECT), "restore_original_project")
        require_ok(server.set_current_timeline(ORIGINAL_TIMELINE), "restore_original_timeline")
        resolve, _, _, _, _, _, runtime_error = server._runtime()
        if runtime_error:
            raise RuntimeError(str(runtime_error))
        safe_call(resolve, "OpenPage", "edit")
        original = server.get_creative_status()
    finally:
        gate = disable_colorist_gate()
    return {"ok": True, "preview_restore": restored, "original": original, "gate": gate}


def main() -> int:
    require_personal_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("setup", "preview", "restore", "finish", "inspect"))
    parser.add_argument("--job-id")
    parser.add_argument("--clip-id")
    parser.add_argument("--side", choices=("before", "after"))
    args = parser.parse_args()
    if args.action == "setup":
        result = setup()
    elif args.action == "preview":
        if not args.job_id or not args.clip_id or not args.side:
            parser.error("preview requires --job-id, --clip-id and --side")
        result = preview(args.job_id, args.clip_id, args.side)
    elif args.action in {"restore", "finish"}:
        if not args.job_id or not args.clip_id:
            parser.error(f"{args.action} requires --job-id and --clip-id")
        result = (finish(args.job_id, args.clip_id) if args.action == "finish"
                  else restore(args.job_id, args.clip_id))
    else:
        require_ok(server.set_current_project(PROJECT_NAME), "set_current_project")
        _, _, project, timeline, _, _, runtime_error = server._runtime()
        if runtime_error:
            raise RuntimeError(str(runtime_error))
        items = []
        for track_index in range(1, int(safe_call(timeline, "GetTrackCount", "video") or 0) + 1):
            for item in safe_call(timeline, "GetItemListInTrack", "video", track_index) or []:
                media_item = safe_call(item, "GetMediaPoolItem")
                items.append({
                    "track": track_index,
                    "name": safe_call(item, "GetName"),
                    "start": safe_call(item, "GetStart"),
                    "end": safe_call(item, "GetEnd"),
                    "duration": safe_call(item, "GetDuration"),
                    "clip_properties": safe_call(media_item, "GetClipProperty") if media_item else None,
                })
        project_settings = safe_call(project, "GetSetting") or {}
        result = {
            "status": server.get_creative_status(),
            "context": server.inspect_colorist_context(),
            "items": items,
            "project_settings": {
                key: value for key, value in project_settings.items()
                if "still" in key.lower() or "frame" in key.lower()
            },
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
