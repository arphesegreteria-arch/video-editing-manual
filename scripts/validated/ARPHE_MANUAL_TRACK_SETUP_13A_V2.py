# -*- coding: utf-8 -*-
"""
ARPHE - MANUAL TRACK SETUP 13A v2
RESET COMPLETO + TRACK RANGE LIMITATO

Cosa fa:
- crea una NUOVA timeline pulita
- inserisce il video originale intero come una sola clip
- resetta Inspector
- crea una NUOVA Fusion Comp
- MediaIn -> MediaOut diretto
- crea ARPHE_MouthTracker_13V2 su ramo laterale
- imposta automaticamente il RANGE DI TRACKING:
      25.30s -> 27.20s
- porta il playhead all'inizio del range
- prepara il Point 1 vicino al labbro

IMPORTANTE:
NON premere Track Forward sull'intera clip.
Il range Fusion viene limitato apposta per evitare che il tracker
continui su altre labbra / scene / dettagli dopo il segmento utile.
"""

import traceback

EXPECTED_PROJECT = "progettotest"
NEW_TIMELINE_BASE = "MANUAL_TRACK_YOYO_13V2"

TRACK_START_SEC = 25.30
TRACK_END_SEC = 27.20

TRACK_X = 0.50
TRACK_Y = 0.63

PATTERN_W = 0.075
PATTERN_H = 0.055
SEARCH_W = 0.24
SEARCH_H = 0.20


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


def safe_set(tool, name, value, frame=None):
    try:
        if frame is None:
            return tool.SetInput(name, value)
        return tool.SetInput(name, value, frame)
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
            "Progetto atteso '%s', aperto '%s'."
            % (EXPECTED_PROJECT, project.GetName())
        )

    media_item = find_original_media_item(project)

    if not media_item:
        raise RuntimeError("MediaPoolItem originale non trovato.")

    media_pool = project.GetMediaPool()

    if not media_pool:
        raise RuntimeError("Media Pool non disponibile.")

    # ============================================================
    # 1) NUOVA TIMELINE PULITA
    # ============================================================
    timeline_name = unique_timeline_name(
        project,
        NEW_TIMELINE_BASE
    )

    timeline = media_pool.CreateEmptyTimeline(timeline_name)

    if not timeline:
        raise RuntimeError("Creazione timeline fallita.")

    project.SetCurrentTimeline(timeline)

    appended = media_pool.AppendToTimeline([media_item])

    if not appended:
        raise RuntimeError("Inserimento clip originale fallito.")

    clip = appended[0]
    reset_inspector(clip)

    fps = fps_float(
        timeline.GetSetting("timelineFrameRate")
    )

    start_frame = int(round(TRACK_START_SEC * fps))
    end_frame = int(round(TRACK_END_SEC * fps))

    # ============================================================
    # 2) NUOVA FUSION COMP
    # ============================================================
    comp = clip.AddFusionComp()

    if not comp:
        raise RuntimeError("AddFusionComp fallita.")

    media_in = find_regid(comp, "MediaIn")
    media_out = find_regid(comp, "MediaOut")

    if not media_in or not media_out:
        raise RuntimeError("MediaIn/MediaOut non trovati.")

    # Output pulito: Tracker NON influenza il render.
    media_out.ConnectInput("Input", media_in)

    # ============================================================
    # 3) RANGE FUSION LIMITATO
    # ============================================================
    #
    # COMPN_RenderStart / COMPN_RenderEnd sono gli attributi Fusion
    # del render/work range. NON limitiamo GlobalStart/GlobalEnd:
    # la clip resta valida per tutta la sua durata.
    #
    try:
        comp.SetAttrs({
            "COMPN_RenderStart": start_frame,
            "COMPN_RenderEnd": end_frame,
        })
    except Exception as exc:
        raise RuntimeError(
            "Impossibile impostare il range Fusion: %s" % exc
        )

    # Porta il playhead all'inizio del range.
    try:
        comp.CurrentTime = start_frame
    except Exception:
        pass

    # ============================================================
    # 4) TRACKER LATERALE
    # ============================================================
    tracker = comp.AddTool(
        "Tracker",
        -32768,
        -32768
    )

    if not tracker:
        raise RuntimeError("Creazione Tracker fallita.")

    try:
        tracker.SetAttrs({
            "TOOLS_Name": "ARPHE_MouthTracker_13V2"
        })
    except Exception:
        pass

    tracker.ConnectInput("Input", media_in)

    safe_set(tracker, "Name1", "Mouth / Lip")
    safe_set(tracker, "Enabled1", 1)

    safe_set(
        tracker,
        "PatternCenter1",
        {
            1: TRACK_X,
            2: TRACK_Y,
            3: 0.0
        },
        start_frame
    )

    safe_set(
        tracker,
        "PatternWidth1",
        PATTERN_W
    )

    safe_set(
        tracker,
        "PatternHeight1",
        PATTERN_H
    )

    safe_set(
        tracker,
        "SearchWidth1",
        SEARCH_W
    )

    safe_set(
        tracker,
        "SearchHeight1",
        SEARCH_H
    )

    safe_set(
        tracker,
        "FramesPerPathPoint",
        1
    )

    # ============================================================
    # 5) VERIFICA RANGE
    # ============================================================
    attrs = comp.GetAttrs() or {}

    actual_start = attrs.get("COMPN_RenderStart")
    actual_end = attrs.get("COMPN_RenderEnd")

    print("")
    print("==============================================")
    print("MANUAL TRACK SETUP 13A v2 COMPLETATO")
    print("Timeline:", timeline_name)
    print("FPS:", fps)
    print("")
    print(
        "TRACK RANGE: %.2fs -> %.2fs"
        % (TRACK_START_SEC, TRACK_END_SEC)
    )
    print(
        "FRAME RANGE: %d -> %d"
        % (start_frame, end_frame)
    )
    print(
        "Fusion RenderStart letto:",
        actual_start
    )
    print(
        "Fusion RenderEnd letto:",
        actual_end
    )
    print("")
    print("Tracker:", "ARPHE_MouthTracker_13V2")
    print("Tracker NON collegato a MediaOut.")
    print("")
    print("PASSO SUCCESSIVO MANUALE:")
    print("1. Apri Fusion.")
    print("2. Seleziona ARPHE_MouthTracker_13V2.")
    print("3. Mettilo sul bordo del labbro.")
    print("4. Premi Track Forward UNA VOLTA.")
    print(
        "Resolve deve fermarsi al frame %d, non continuare."
        % end_frame
    )
    print("==============================================")


try:
    main()

except Exception as exc:
    print("")
    print("######## ERRORE SETUP 13A V2 ########")
    print(str(exc))
    traceback.print_exc()
    print("######################################")
    raise
