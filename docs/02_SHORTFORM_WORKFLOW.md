# 02 — Shortform Workflow

## Architettura consigliata

`video sorgente → edit plan → Python → nuova timeline Resolve`

L'originale non deve essere modificato.

## Primitive validate

### CUT
Non usare come requisito un vero blade/split sull'item esistente.
Ricostruire una nuova timeline con i soli intervalli da tenere.

### ZOOM / YOYO
Usare Fusion:
`MediaIn → Transform → MediaOut`

Animare `Transform.Size` con `BezierSpline`.

### TRACKED YOYO
1. Python prepara Tracker e range.
2. Operatore posiziona il tracker.
3. Operatore esegue Track Forward.
4. Python legge `TrackedCenter1`.
5. Python applica lo yoyo.

## Regola estetica

Il punto migliore da tracciare può non essere il punto migliore da mettere al centro.

Separare sempre:
- **tracking anchor** = dettaglio stabile;
- **aesthetic target** = dove deve apparire il soggetto nell'inquadratura;
- **zoom curve** = ritmo dell'effetto.
