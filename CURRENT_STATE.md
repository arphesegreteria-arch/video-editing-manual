# CURRENT STATE

Ultimo aggiornamento: sessione 2026-08-27.

## Obiettivo del progetto

Automatizzare il montaggio di contenuti video in DaVinci Resolve tramite Python:
- cut / remove / reassemble;
- punch-in e zoom ritmici;
- tracking del soggetto;
- B-roll;
- trascrizione e paper edit di longform;
- raffinamento automatico dei punti di taglio sull'audio reale.

## ✅ VALIDATO

### Cut automatici per ricostruzione timeline
`ARPHE_AUTOCUT_TEST_01.py`
- crea una nuova timeline;
- ricompone intervalli della clip sorgente;
- elimina segmenti senza modificare l'originale;
- approccio consigliato: ricostruzione timeline, non blade diretto.

### Fusion Transform + BezierSpline
`ARPHE_NUCLEAR_RESET_YOYO_08.py`
- nuova timeline pulita;
- nuova Fusion Comp;
- `Transform.Size` animato tramite `BezierSpline`;
- effetto yoyo evidente e funzionante.

### Tracking manuale nativo + lettura Python
`ARPHE_MANUAL_TRACK_SETUP_13A_V2.py`
`ARPHE_TRACKED_YOYO_APPLY_13B_V2.py`
- Python prepara Tracker e range;
- operatore esegue il Track Forward nativo in Fusion;
- Python legge `TrackedCenter1`;
- path del tracking può pilotare l'effetto yoyo.

### Trascrizione longform esterna
Workflow con `faster-whisper` testato su `blabla.mp4`:
- JSON `ARPHE_TRANSCRIPT_V1` generato correttamente;
- timestamp a livello segmento e parola;
- durata transcript: circa 2095.339 s;
- il JSON è adatto al paper edit semantico.

### Diagnostica timing longform
Sul test `blabla.mp4`:
- source FPS = 30.0;
- timeline FPS = 30.0;
- frames = 62860;
- durata Resolve ≈ 2095.333 s;
- durata Whisper ≈ 2095.339 s.

Conclusione: nel test non c'è drift progressivo tra transcript e Resolve.

## ⚠️ PARZIALE / DA RIFINIRE

### Longform: paper edit da transcript
Il transcript è valido per decidere **cosa** togliere, ma i timestamp Whisper non devono essere trattati come punti di lama perfetti.

Problemi osservati nei primi rough cut:
- alcune parole tranciate;
- pause residue troppo lunghe;
- stacchi poco naturali sul parlato;
- jump cut visivi da revisionare.

Lezione:
**decisione editoriale ≠ posizione fisica del cut**.

Strategia corrente:
1. ChatGPT decide semanticamente cosa eliminare.
2. Whisper protegge e localizza le parole.
3. Un analizzatore locale legge la waveform reale dell'MP4.
4. Il confine viene spostato in un punto quieto vicino, senza mangiare altro parlato.
5. Resolve ricostruisce una nuova timeline.

### Audio-aligned cut V4.x
- V4.2: approccio conservativo, ma ottimizzare separatamente i due bordi può lasciare troppa aria alla giunzione.
- V4.3: candidato corrente; tratta la giunzione in modo più stretto e riduce il silenzio residuo.
- Stato: **in prova, non ancora promosso a validato**.

### Reframing estetico dopo tracking
Il tracking può essere tecnicamente corretto ma il soggetto può risultare scentrato durante forti zoom.

Lezione:
**punto di tracking ≠ centro estetico dell'effetto**.

Il tracker va posizionato sul dettaglio più stabile; il framing finale deve usare un offset/target separato.

## ❌ NON AFFIDABILE / DA NON USARE COME PRIMITIVA

### Timestamp Whisper usati direttamente come lama
Non usare `start/end` del transcript come cut frame senza margine o allineamento audio.

### Avvio automatico del tracking da FusionScript
I trigger `TrackForward` / `TrackForwardFromCurrentTime` sono esposti, ma i test hanno prodotto path immobili e range anomali.

Decisione:
**non basare il prodotto sul trigger automatico del Tracker nella versione gratuita attuale**.

Strategia tracking corrente:
1. Python prepara tutto.
2. Operatore esegue un singolo Track Forward nativo.
3. Python riprende il controllo.

## PROSSIMO TEST

### Validazione V4.3 longform
1. Partire sempre dalla timeline originale completa.
2. Generare il piano audio-aligned dal video + transcript + edit plan.
3. Creare una nuova timeline `LONGFORM_AUDIO_ALIGNED_CUT_04_3`.
4. Revisionare tutto il longform con priorità a:
   - attacchi delle parole dopo i cut;
   - code delle parole prima dei cut;
   - pause troppo lunghe/corte;
   - eventuale vero offset audio/video;
   - qualità visiva dei jump cut.
5. Solo dopo revisione completa promuovere la V4.3 a `validated`.
