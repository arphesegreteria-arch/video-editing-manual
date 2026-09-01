# 03 — Tracking e Fusion

## Stato del documento

Le osservazioni sul trigger automatico del Tracker qui sotto provengono dalla fase **DaVinci Resolve Free / scripting interno**.

Non devono essere considerate automaticamente valide per Resolve Studio 21.0.4.5. Con Studio il tracking/IntelliTrack va rieseguito come probe esterno e registrato in `RESOLVE_STUDIO_CAPABILITIES.md`.

## Cosa abbiamo verificato nella build precedente

Il nodo `Tracker` può essere creato da Python.

Input esposti includevano:
- `PatternCenter1`
- `PatternWidth1`
- `PatternHeight1`
- `SearchWidth1`
- `SearchHeight1`
- `TrackedCenter1`
- `TrackForward`
- `TrackForwardFromCurrentTime`
- `FramesPerPathPoint`
- `AdaptiveMode`

## Problema del trigger automatico — build Free testata

Nonostante gli input fossero esposti, l'avvio del tracking via script non risultò affidabile.

Sintomi osservati:
- `TrackedCenter1` immobile;
- render range anomalo;
- nessun path/modifier generato.

## Workaround legacy

Il workaround validato come proof-of-concept era:
- Python prepara setup/range;
- operatore esegue tracking nell'interfaccia nativa;
- Python legge il path;
- Python applica l'effetto.

Con Studio non preservare questo passaggio manuale per inerzia: prima provare le capacità Studio da Python esterno.

## REGOLA FONDAMENTALE — RANGE

Anche nel nuovo percorso resta valida la regola di non tracciare inutilmente l'intera clip se l'effetto interessa solo un tratto.

Prima del tracking:
1. determinare start/end;
2. limitare l'analisi al range utile quando l'API lo consente;
3. partire dallo start corretto;
4. verificare il path solo sull'intervallo necessario.

## REGOLA FONDAMENTALE — TRACKING VS FRAMING

**Tracking anchor ≠ aesthetic center.**

Esempio labbro:
- tracker sul dettaglio stabile/ad alto contrasto;
- centro estetico dello zoom al centro della bocca;
- offset/reframe calcolato separatamente.

Questa separazione resta valida anche se Studio rende il tracking completamente automatico.
