# 03 — Tracking e Fusion

## Cosa abbiamo verificato

Il nodo `Tracker` può essere creato da Python.

Input esposti dalla build testata includono:
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

## Problema del trigger automatico

Nonostante gli input siano esposti, l'avvio del tracking via script non è risultato affidabile.

Sintomi osservati:
- `TrackedCenter1` immobile;
- render range anomalo;
- nessun path/modifier generato.

## Soluzione corrente

Fare il tracking con l'interfaccia nativa di Resolve e lasciare a Python:
- setup;
- limitazione range;
- lettura path;
- applicazione effetti.

## REGOLA FONDAMENTALE — RANGE

Mai tracciare l'intera clip se l'effetto interessa solo un tratto.

Prima del Track Forward:
1. determinare start/end;
2. impostare `COMPN_RenderStart`;
3. impostare `COMPN_RenderEnd`;
4. portarsi allo start;
5. tracciare.

Questo evita che il tracker perda il soggetto dopo un cambio scena e si agganci ad altro.

## REGOLA FONDAMENTALE — TRACKING VS FRAMING

**Tracking anchor ≠ aesthetic center.**

Esempio labbro:
- tracker sul bordo superiore se è più contrastato;
- centro estetico dello zoom al centro della bocca;
- eventuale offset calcolato separatamente.
