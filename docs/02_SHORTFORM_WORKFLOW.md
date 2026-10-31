# 02 — Shortform Workflow

## Architettura consigliata

`video sorgente → edit plan → Python → nuova timeline Resolve`

L'originale non deve essere modificato.

## Primitive validate

### CUT
Non usare come requisito un vero blade/split sull'item esistente.
Ricostruire una nuova timeline con i soli intervalli da tenere.

### VOICE-OVER CTA — COPY / SPLIT / READ-BACK

Per spostare una frase conclusiva del voice-over sulla CTA non modificare la timeline corrente.
Usare la primitiva chiusa `move_voiceover_tail_to_cta`: duplica una timeline ARPHÈ consentita,
sostituisce una sola clip audio della traccia indicata con il corpo iniziale e la coda, e colloca
la coda a un frame CTA esplicito. La frase e i due frame sono sempre verificati dall'operatore;
il bridge non riconosce o interpreta automaticamente il parlato. Il risultato restituisce il
read-back dei quattro confini e la timeline sorgente rimane invariata.

Non esiste una primitiva generica per spostare, tagliare o cancellare clip audio.

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

### CAPTIONS FUSION ARPHÈ — SUPPORTED / APPROVATO

Il probe reale del 2026-10-02 ha confermato che `CreateSubtitlesFromAudio` crea la traccia
nativa, ma lo styling completo Track Style/Inspector non è esposto in modo affidabile dalla API
pubblica osservata. Per ADV verticali con stile ARPHÈ usare l'azione generica `CAPTIONS` del
workflow Vertical Social, soltanto dopo picture lock:

`traccia subtitle nativa → timing/testo → Text+ Fusion → render burn-in`

La composizione deve partire da un Background con alpha zero; ogni caption usa un Merge con
`Blend.SetExpression("iif(time >= start and time < end, 1, 0)")`. Non affidarsi a un
`BezierSpline` assegnato direttamente a Blend: nel test non è rimasto attivo.

Preset mobile approvato: frase intera in Satoshi Bold maiuscolo, bianco, fondo bordeaux
`#680C09` soltanto dietro la parola pronunciata, Text+ size `0.050` standard e `0.065`
evidenza Bold Italic. È ammessa al massimo una parola in evidenza e un massimo di due righe.
Se la frase non entra, dividerla temporalmente: non usare fitting dinamico o misure intermedie.
Padding card `0.016`, distanza minima fra parole/card `0.014`, formato 1080×1920/30.
La fascia bassa è il default: box entro il 68–82% dell'altezza, centro al 76%
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
