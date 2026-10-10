from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.branded_longform_graphics import apply_editorial_graphic  # noqa: E402
from bridge.branded_longform_jobs import new_branded_longform_job  # noqa: E402
from bridge.branded_longform_resolve import (add_proposal_markers, create_cleanup_timeline,
                                             create_editorial_timeline, find_owned_timeline,
                                             timeline_structure_fingerprint,
                                             verify_branded_longform_timelines)  # noqa: E402
from bridge.config import load_config  # noqa: E402
from bridge.resolve_connection import context, safe_call  # noqa: E402


def main() -> int:
    _, manager, previous_project, _, error = context()
    if error:
        raise RuntimeError(error)
    previous_name = str(safe_call(previous_project, "GetName") or "")
    if not previous_name:
        raise RuntimeError("Gate rifiutato: impossibile identificare il progetto da ripristinare")
    config = load_config(Path("C:/ARPHE/MCP/ARPHE_WINDOWS_BRIDGE_RUNTIME_V1/runtime-configs/PC_PERSONALE/creative_config.json"))
    if config.workstation_id != "PC_PERSONALE":
        raise RuntimeError("Gate rifiutato: config diversa da PC_PERSONALE")
    project_name = "ARPHE_BRANDED_LONGFORM_NATIVE_GATE_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    project = safe_call(manager, "CreateProject", project_name)
    if project is None or str(safe_call(project, "GetName") or "") != project_name:
        raise RuntimeError("Creazione progetto sintetico branded longform fallita")
    pool = safe_call(project, "GetMediaPool")
    source = safe_call(pool, "CreateEmptyTimeline", "__BRANDED_LONGFORM_GATE_ORIGINAL")
    if source is None:
        raise RuntimeError("Timeline sorgente sintetica non creata")
    job = new_branded_longform_job(project_name, "__BRANDED_LONGFORM_GATE_ORIGINAL",
                                   "native-source", "native-profile", "PC_PERSONALE",
                                   "ARPHE_LONGFORM_EDITORIAL",
                                   original_timeline_fingerprint=timeline_structure_fingerprint(source))
    created = [source]
    evidence = []
    gate_error = None
    try:
        evidence.append(create_cleanup_timeline(project, job))
        cleanup = find_owned_timeline(project, job, job.cleanup_timeline); created.append(cleanup)
        proposal = {"proposal_id": "P001", "kind": "KEYWORD_BOX", "start_frame": 0,
                    "end_frame": 30, "rationale": "Gate sintetico", "executable": True}
        evidence.append(add_proposal_markers(project, job, [proposal]))
        evidence.append(create_editorial_timeline(project, job))
        editorial = find_owned_timeline(project, job, job.editorial_timeline); created.append(editorial)
        evidence.append(apply_editorial_graphic(project, editorial, config, job, proposal))
        evidence.append(verify_branded_longform_timelines(project, job))
    except Exception as exc:
        gate_error = exc
    finally:
        timelines_deleted = bool(safe_call(pool, "DeleteTimelines", list(reversed(created))))
        restored = safe_call(manager, "LoadProject", previous_name)
        project_deleted = bool(safe_call(manager, "DeleteProject", project_name))
        if not timelines_deleted or restored is None or not project_deleted:
            raise RuntimeError(
                f"Rollback gate incompleto: timelines={timelines_deleted}, "
                f"project_restored={restored is not None}, project_deleted={project_deleted}"
            )
    if gate_error is not None:
        raise gate_error
    print(json.dumps({"ok": True, "project": project_name, "evidence": evidence,
                      "restored_project": previous_name,
                      "rollback": "temporary timelines and project deleted"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
