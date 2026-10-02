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

### CAPTION MOBILE — PARTIAL

Il probe reale del 2026-10-02 ha confermato che `CreateSubtitlesFromAudio` crea la traccia
nativa, ma lo styling completo Track Style/Inspector non è esposto in modo affidabile dalla API
pubblica osservata. Per ADV verticali con stile ARPHÈ usare, finché il bridge non offre una
primitiva dedicata, il fallback verificato:

`traccia subtitle nativa → timing/testo → Text+ Fusion → render burn-in`

La composizione deve partire da un Background con alpha zero; ogni caption usa un Merge con
`Blend.SetExpression("iif(time >= start and time < end, 1, 0)")`. Non affidarsi a un
`BezierSpline` assegnato direttamente a Blend: nel test non è rimasto attivo.

Preset mobile testato: Satoshi Bold, bianco, fondo bordeaux `#680C09`, Text+ size `0.050`,
1080×1920/30. La fascia bassa è il default: box entro il 68–82% dell'altezza, centro al 76%
(`Center.Y = 0.24` in Fusion), con almeno il 15% libero in basso. Se collide con un volto o con
un elemento essenziale usare la fascia alta 8–20%; mai sovrapporre testo, padding o fondo a un
volto. Mantenere la stessa fascia per una scena, evitando salti a ogni battuta.

La traccia nativa resta conservata ma disabilitata; `ExportSubtitle` deve essere false per evitare
doppioni, perché il Text+ è già impresso nel video.

Procedura, limiti e gate di promozione: `docs/16_CAPTION_ENGINE_AND_MOBILE_SUBTITLES.md`.

## Regola estetica

Il punto migliore da tracciare può non essere il punto migliore da mettere al centro.

Separare sempre:
- **tracking anchor** = dettaglio stabile;
- **aesthetic target** = dove deve apparire il soggetto nell'inquadratura;
- **zoom curve** = ritmo dell'effetto.
