# -*- coding: utf-8 -*-
"""
ARPHE - NUCLEAR RESET YOYO 08

RESET DAVVERO TOTALE:
- NON riusa la timeline corrente
- NON riusa nessuna Fusion Comp
- recupera solo il MediaPoolItem originale
- crea una NUOVA timeline
- inserisce UNA clip intera
- reset Inspector
- crea UNA Fusion Comp nuova
- dentro: MediaIn -> Transform -> MediaOut
- nessuna mask
- nessun blur
- nessun vecchio nodo
- nessun micro-taglio

Test:
YOYO volutamente ESAGERATO tra 24.45s e 27.20s.
Se questo script funziona, l'effetto DEVE vedersi.
"""

import traceback

EXPECTED_PROJECT = "progettotest"
NEW_TIMELINE_BASE = "NUCLEAR_YOYO_RESET"

# Effetto volutamente evidente.
ZOOM_KEYS = [
    (24.20, 1.00),
    (24.45, 1.00),
    (24.70, 2.30),
    (24.95, 1.15),
    (25.20, 2.50),
    (25.45, 1.20),
    (25.70, 2.40),
    (25.95, 1.15),
    (26.20, 2.50),
    (26.45, 1.20),
    (26.70, 2.30),
    (26.95, 1.10),
    (27.20, 1.00),
    (27.40, 1.00),
]

# Punto statico circa sulla bocca.
# Per questo test NON animiamo ancora il tracking:
# vogliamo isolare e validare lo YOYO.
MOUTH_PIVOT_X = 0.50
MOUTH_PIVOT_Y = 0.63


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


def unique_timeline_name(project, base):
    names = set()

    for i in range(1, project.GetTimelineCount() + 1):
        tl = project.GetTimelineByIndex(i)
        if tl:
            names.add(tl.GetName())

    if base not in names:
        return base

    n = 2
    while ("%s_%02d" % (base, n)) in names:
        n += 1

    return "%s_%02d" % (base, n)


def find_original_media_item(project):
    """
    Recupera solo il MediaPoolItem.
    NON recupera effetti, Fusion Comp, timeline item o trasformazioni.
    """
    for i in range(1, project.GetTimelineCount() + 1):
        tl = project.GetTimelineByIndex(i)
        if not tl:
            continue

        items = tl.GetItemListInTrack("video", 1) or []

        for item in items:
            try:
                mpi = item.GetMediaPoolItem()
                if mpi:
                    return mpi
            except Exception:
                pass

    return None


def find_regid(comp, regid):
    for _, tool in (comp.GetToolList(False) or {}).items():
        try:
            attrs = tool.GetAttrs() or {}
            if attrs.get("TOOLS_RegID") == regid:
                return tool
        except Exception:
            pass

    return None


def reset_inspector(clip):
    try:
        clip.SetProperty("ZoomGang", True)
    except Exception:
        pass

    for key, value in [
        ("ZoomX", 1.0),
        ("ZoomY", 1.0),
        ("Pan", 0.0),
        ("Tilt", 0.0),
        ("RotationAngle", 0.0),
        ("AnchorPointX", 0.0),
        ("AnchorPointY", 0.0),
    ]:
        try:
            clip.SetProperty(key, value)
        except Exception:
            pass


def main():
    resolve = get_resolve()

    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None

    if not project:
        raise RuntimeError("Nessun progetto aperto.")

    if project.GetName().lower() != EXPECTED_PROJECT.lower():
        raise RuntimeError(
            "Progetto atteso '%s', aperto '%s'."
            % (EXPECTED_PROJECT, project.GetName())
        )

    media_item = find_original_media_item(project)

    if not media_item:
        raise RuntimeError(
            "Non riesco a recuperare il MediaPoolItem originale."
        )

    media_pool = project.GetMediaPool()

    if not media_pool:
        raise RuntimeError("Media Pool non disponibile.")

    timeline_name = unique_timeline_name(
        project,
        NEW_TIMELINE_BASE
    )

    timeline = media_pool.CreateEmptyTimeline(timeline_name)

    if not timeline:
        raise RuntimeError("Impossibile creare la nuova timeline.")

    project.SetCurrentTimeline(timeline)

    appended = media_pool.AppendToTimeline([media_item])

    if not appended:
        raise RuntimeError(
            "Impossibile inserire il video originale nella timeline."
        )

    clip = appended[0]

    reset_inspector(clip)

    fps = fps_float(
        timeline.GetSetting("timelineFrameRate")
    )

    print("==============================================")
    print("RESET NUCLEARE")
    print("Nuova timeline:", timeline_name)
    print("Clip su V1: 1")
    print("Inspector: RESET")
    print("FPS:", fps)
    print("==============================================")

    comp = clip.AddFusionComp()

    if not comp:
        raise RuntimeError(
            "Resolve non ha creato la nuova Fusion Comp."
        )

    media_in = find_regid(comp, "MediaIn")
    media_out = find_regid(comp, "MediaOut")

    if not media_in or not media_out:
        raise RuntimeError(
            "MediaIn / MediaOut mancanti nella nuova Fusion Comp."
        )

    transform = comp.AddTool(
        "Transform",
        -32768,
        -32768
    )

    if not transform:
        raise RuntimeError("Creazione Transform fallita.")

    try:
        transform.SetAttrs(
            {"TOOLS_Name": "ARPHE_NUCLEAR_YOYO"}
        )
    except Exception:
        pass

    transform.ConnectInput("Input", media_in)
    media_out.ConnectInput("Input", transform)

    transform.SetInput("Size", 1.0)

    transform.SetInput(
        "Pivot",
        {
            1: MOUTH_PIVOT_X,
            2: MOUTH_PIVOT_Y,
            3: 0.0
        }
    )

    transform.SetInput(
        "Center",
        {
            1: 0.5,
            2: 0.5,
            3: 0.0
        }
    )

    transform.Size = comp.BezierSpline()

    for sec, zoom in ZOOM_KEYS:
        frame = int(round(sec * fps))
        transform.Size[frame] = float(zoom)

        print(
            "KEY %4d | %5.2fs | Size %.2f"
            % (frame, sec, zoom)
        )

    print("")
    print("Fusion tools presenti:")

    tools = comp.GetToolList(False) or {}

    for _, tool in tools.items():
        try:
            attrs = tool.GetAttrs() or {}
            print(
                " -",
                attrs.get("TOOLS_Name"),
                "[%s]" % attrs.get("TOOLS_RegID")
            )
        except Exception:
            pass

    print("")
    print("==============================================")
    print("NUCLEAR YOYO CREATO")
    print("Timeline:", timeline_name)
    print("Nessun taglio.")
    print("Nessuna maschera.")
    print("Un solo Transform.")
    print("Zoom massimo: 2.50x")
    print("Zona test: 24.2s - 27.4s")
    print("==============================================")
    print("")
    print(
        "Se tra 24.2s e 27.4s NON vedi zoom enormi avanti/indietro,"
    )
    print(
        "allora il problema e' specificamente l'animazione Fusion Size,"
    )
    print(
        "non residui dei test precedenti."
    )


try:
    main()

except Exception as exc:
    print("")
    print("######## ERRORE NUCLEAR YOYO ########")
    print(str(exc))
    traceback.print_exc()
    print("######################################")
    raise
