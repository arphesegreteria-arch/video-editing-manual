# -*- coding: utf-8 -*-
"""
ARPHE - DaVinci Resolve AUTOCUT TEST
Progetto atteso: progettotest

Cosa fa:
- legge la clip principale gia presente nella timeline attiva
- crea una NUOVA timeline, lasciando intatta l'originale
- elimina virtualmente i segmenti 00:08-00:11 e 00:28-00:33
- ricompone i segmenti rimanenti uno di seguito all'altro

Eseguire da:
Workspace -> Scripts -> Utility
"""

import sys
import traceback

EXPECTED_PROJECT = "progettotest"
NEW_TIMELINE_NAME = "AUTOCUT_TEST_01"

# Segmenti da RIMUOVERE, in secondi rispetto all'inizio della clip in timeline.
REMOVE_RANGES = [
    (8.0, 11.0),
    (28.0, 33.0),
]


def get_resolve():
    # Quando lo script viene lanciato DENTRO Resolve, spesso "resolve"
    # e' gia disponibile. In caso contrario proviamo il modulo ufficiale.
    try:
        r = globals().get("resolve")
        if r:
            return r
    except Exception:
        pass

    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except Exception as exc:
        raise RuntimeError(
            "Impossibile collegarsi a DaVinci Resolve. "
            "Lancia questo file da Workspace > Scripts > Utility."
        ) from exc


def fps_to_float(value):
    """Gestisce fps come '25', '29.97', '24.0', ecc."""
    try:
        return float(value)
    except Exception:
        return 25.0


def merge_remove_ranges(ranges, duration_sec):
    cleaned = []
    for start, end in sorted(ranges):
        start = max(0.0, float(start))
        end = min(float(duration_sec), float(end))
        if end <= start:
            continue

        if cleaned and start <= cleaned[-1][1]:
            cleaned[-1] = (cleaned[-1][0], max(cleaned[-1][1], end))
        else:
            cleaned.append((start, end))
    return cleaned


def build_keep_ranges(remove_ranges, duration_sec):
    keep = []
    cursor = 0.0

    for cut_start, cut_end in remove_ranges:
        if cut_start > cursor:
            keep.append((cursor, cut_start))
        cursor = max(cursor, cut_end)

    if cursor < duration_sec:
        keep.append((cursor, duration_sec))

    return keep


def main():
    resolve = get_resolve()

    pm = resolve.GetProjectManager()
    if not pm:
        raise RuntimeError("Project Manager non disponibile.")

    project = pm.GetCurrentProject()
    if not project:
        raise RuntimeError("Nessun progetto aperto.")

    project_name = project.GetName()
    print("Progetto aperto:", project_name)

    if project_name.lower() != EXPECTED_PROJECT.lower():
        raise RuntimeError(
            "Progetto sbagliato. Atteso '%s', aperto '%s'."
            % (EXPECTED_PROJECT, project_name)
        )

    source_timeline = project.GetCurrentTimeline()
    if not source_timeline:
        raise RuntimeError("Nessuna timeline attiva.")

    print("Timeline sorgente:", source_timeline.GetName())

    video_items = source_timeline.GetItemListInTrack("video", 1) or []
    if not video_items:
        raise RuntimeError("Nessuna clip trovata sulla traccia video V1.")

    # Per questo primo test prendiamo la clip piu lunga su V1.
    source_item = max(video_items, key=lambda item: item.GetDuration())
    media_item = source_item.GetMediaPoolItem()

    if not media_item:
        raise RuntimeError(
            "La clip principale non sembra collegata a un Media Pool Item."
        )

    clip_name = source_item.GetName()
    print("Clip scelta:", clip_name)

    fps = fps_to_float(source_timeline.GetSetting("timelineFrameRate"))
    duration_frames = int(source_item.GetDuration())
    duration_sec = duration_frames / fps

    print("FPS timeline:", fps)
    print("Durata clip in timeline: %.3f sec" % duration_sec)

    # Recuperiamo il punto IN sorgente della clip gia montata, se disponibile.
    try:
        source_start = int(source_item.GetSourceStartFrame())
    except Exception:
        source_start = 0

    remove_ranges = merge_remove_ranges(REMOVE_RANGES, duration_sec)
    keep_ranges = build_keep_ranges(remove_ranges, duration_sec)

    if not keep_ranges:
        raise RuntimeError("I tagli eliminerebbero l'intera clip.")

    print("Segmenti rimossi:", remove_ranges)
    print("Segmenti mantenuti:", keep_ranges)

    media_pool = project.GetMediaPool()
    if not media_pool:
        raise RuntimeError("Media Pool non disponibile.")

    # Se esiste gia una timeline con questo nome, ne creiamo una con suffisso.
    timeline_name = NEW_TIMELINE_NAME
    existing_names = set()
    try:
        count = project.GetTimelineCount()
        for i in range(1, count + 1):
            tl = project.GetTimelineByIndex(i)
            if tl:
                existing_names.add(tl.GetName())
    except Exception:
        pass

    suffix = 2
    while timeline_name in existing_names:
        timeline_name = "%s_%02d" % (NEW_TIMELINE_NAME, suffix)
        suffix += 1

    new_timeline = media_pool.CreateEmptyTimeline(timeline_name)
    if not new_timeline:
        raise RuntimeError("Impossibile creare la nuova timeline.")

    project.SetCurrentTimeline(new_timeline)

    # Record frame iniziale della nuova timeline.
    record_cursor = int(new_timeline.GetStartFrame())

    appended_total = []

    for keep_start_sec, keep_end_sec in keep_ranges:
        rel_start = int(round(keep_start_sec * fps))
        rel_end_exclusive = int(round(keep_end_sec * fps))

        # AppendToTimeline usa un range sorgente.
        # Usiamo endFrame inclusivo, quindi -1.
        src_start = source_start + rel_start
        src_end = source_start + rel_end_exclusive - 1

        if src_end < src_start:
            continue

        clip_info = {
            "mediaPoolItem": media_item,
            "startFrame": src_start,
            "endFrame": src_end,
            "recordFrame": record_cursor,
        }

        result = media_pool.AppendToTimeline([clip_info])
        if not result:
            raise RuntimeError(
                "Append fallito per il segmento %.3f-%.3f sec"
                % (keep_start_sec, keep_end_sec)
            )

        appended_total.extend(result)

        segment_frames = rel_end_exclusive - rel_start
        record_cursor += segment_frames

        print(
            "OK segmento %.3f-%.3f sec -> %d frame"
            % (keep_start_sec, keep_end_sec, segment_frames)
        )

    if len(appended_total) < 3:
        print(
            "ATTENZIONE: sono stati creati meno elementi del previsto. "
            "Controlla comunque la timeline."
        )

    print("")
    print("==============================================")
    print("AUTOCUT COMPLETATO")
    print("Nuova timeline:", timeline_name)
    print("Rimossi: 00:08-00:11 e 00:28-00:33")
    print("Originale lasciato intatto.")
    print("==============================================")


try:
    main()
except Exception as exc:
    print("")
    print("############ ERRORE AUTOCUT ############")
    print(str(exc))
    traceback.print_exc()
    print("#########################################")
    raise
