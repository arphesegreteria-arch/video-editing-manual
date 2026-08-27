# -*- coding: utf-8 -*-
"""
ARPHE - TRACKED YOYO APPLY 13B v2

DA LANCIARE SOLO DOPO:
- ARPHE_MANUAL_TRACK_SETUP_13A_V2.py
- tracking manuale nativo in Fusion sul SOLO range 25.30-27.20s

Legge TrackedCenter1 e applica lo yoyo usando il tracking reale.
"""

import traceback

EXPECTED_PROJECT = "progettotest"
EXPECTED_TIMELINE_PREFIX = "MANUAL_TRACK_YOYO_13V2"
TRACKER_NAME = "ARPHE_MouthTracker_13V2"

TRACK_START_SEC = 25.30
TRACK_END_SEC = 27.20

ZOOM_KEYS = [
    (25.30, 1.00),
    (25.50, 2.20),
    (25.70, 1.20),
    (25.90, 2.45),
    (26.10, 1.25),
    (26.30, 2.35),
    (26.50, 1.20),
    (26.70, 2.20),
    (26.90, 1.15),
    (27.20, 1.00),
]


def get_resolve():
    try:
        r = globals().get("resolve")
        if r:
            return r
    except Exception:
        pass

    import DaVinciResolveScript as dvr
    return dvr.scriptapp("Resolve")


def fps_float(value):
    try:
        return float(value)
    except Exception:
        return 25.0


def find_regid(comp, regid):
    for _, tool in (comp.GetToolList(False) or {}).items():
        try:
            if (tool.GetAttrs() or {}).get("TOOLS_RegID") == regid:
                return tool
        except Exception:
            pass
    return None


def find_named(comp, name):
    try:
        return comp.FindTool(name)
    except Exception:
        return None


def point_tuple(value):
    try:
        return (
            float(value[1]),
            float(value[2])
        )
    except Exception:
        return None


def main():
    resolve = get_resolve()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None

    if not project:
        raise RuntimeError("Nessun progetto aperto.")

    if project.GetName().lower() != EXPECTED_PROJECT.lower():
        raise RuntimeError(
            "Apri il progetto '%s'."
            % EXPECTED_PROJECT
        )

    timeline = project.GetCurrentTimeline()

    if not timeline:
        raise RuntimeError("Nessuna timeline attiva.")

    if not timeline.GetName().startswith(
        EXPECTED_TIMELINE_PREFIX
    ):
        raise RuntimeError(
            "Timeline sbagliata. Attiva: '%s'"
            % timeline.GetName()
        )

    items = timeline.GetItemListInTrack(
        "video",
        1
    ) or []

    if len(items) != 1:
        raise RuntimeError(
            "Mi aspetto una sola clip su V1."
        )

    clip = items[0]

    if clip.GetFusionCompCount() < 1:
        raise RuntimeError(
            "Fusion Comp non trovata."
        )

    comp = clip.GetFusionCompByIndex(1)

    media_in = find_regid(comp, "MediaIn")
    media_out = find_regid(comp, "MediaOut")
    tracker = find_named(comp, TRACKER_NAME)

    if not media_in or not media_out or not tracker:
        raise RuntimeError(
            "MediaIn/MediaOut/Tracker non trovati."
        )

    fps = fps_float(
        timeline.GetSetting("timelineFrameRate")
    )

    start_frame = int(round(TRACK_START_SEC * fps))
    end_frame = int(round(TRACK_END_SEC * fps))

    tracked = []

    for frame in range(
        start_frame,
        end_frame + 1
    ):
        try:
            value = tracker.GetInput(
                "TrackedCenter1",
                frame
            )
        except Exception:
            value = None

        point = point_tuple(value)

        if point is not None:
            tracked.append(
                (
                    frame,
                    point[0],
                    point[1]
                )
            )

    unique = set(
        (
            round(x, 5),
            round(y, 5)
        )
        for _, x, y in tracked
    )

    print("Punti tracking:", len(tracked))
    print("Posizioni distinte:", len(unique))

    if len(unique) < 3:
        raise RuntimeError(
            "Tracking non valido o non eseguito. "
            "Non applico lo yoyo."
        )

    media_out.ConnectInput("Input", media_in)

    old = find_named(
        comp,
        "ARPHE_TRACKED_YOYO_13V2"
    )

    if old:
        try:
            comp.DeleteTool(old)
        except Exception:
            pass

    transform = comp.AddTool(
        "Transform",
        -32768,
        -32768
    )

    if not transform:
        raise RuntimeError(
            "Creazione Transform fallita."
        )

    try:
        transform.SetAttrs({
            "TOOLS_Name":
            "ARPHE_TRACKED_YOYO_13V2"
        })
    except Exception:
        pass

    transform.ConnectInput(
        "Input",
        media_in
    )

    media_out.ConnectInput(
        "Input",
        transform
    )

    transform.SetInput(
        "Center",
        {
            1: 0.5,
            2: 0.5,
            3: 0.0
        }
    )

    pivot_path = comp.Path()
    transform.Pivot = pivot_path

    for frame, x, y in tracked:
        pivot_path[frame] = {
            1: float(x),
            2: float(y),
            3: 0.0
        }

    transform.Size = comp.BezierSpline()

    for sec, zoom in ZOOM_KEYS:
        frame = int(round(sec * fps))
        transform.Size[frame] = float(zoom)

    print("")
    print("==============================================")
    print("TRACKED YOYO 13B v2 COMPLETATO")
    print("Tracking letto e validato.")
    print("Yoyo applicato.")
    print("Range:", TRACK_START_SEC, "->", TRACK_END_SEC)
    print("==============================================")


try:
    main()

except Exception as exc:
    print("")
    print("######## ERRORE APPLY 13B V2 ########")
    print(str(exc))
    traceback.print_exc()
    print("######################################")
    raise
