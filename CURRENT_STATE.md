# CURRENT STATE

Ultimo aggiornamento: sessione 2026-09-01.

## Obiettivo del progetto

Automatizzare il montaggio di contenuti video in DaVinci Resolve tramite Python:
- cut / remove / reassemble;
- punch-in e zoom ritmici;
- tracking del soggetto;
- B-roll;
- trascrizione e paper edit di longform;
- rilevamento di pause/disfluenze/false partenze;
- raffinamento automatico dei punti di taglio sull'audio reale;
- benchmark quantitativo contro montaggi umani di riferimento.

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

### Export del reference umano
`ARPHE_EXPORT_REFERENCE_EDIT_02.py`
- legge una timeline montata manualmente;
- esporta kept segments, remove ranges e joins;
- non modifica la timeline;
- usato con successo per creare il reference umano di `blabla.mp4`.

## 📊 BENCHMARK 01 — `blabla.mp4`

Reference umano confrontato con `ARPHE_LONGFORM_SAFE_EDIT_PLAN_V3`.

Risultati:
- Precision: **0.522**
- Recall: **0.430**
- F1: **0.472**
- False positive: **197.5 s**
- False negative: **286.1 s**
- Boundary matched: **48 / 246**
- Mean boundary error: **625 ms**
- Median boundary error: **373 ms**

Interpretazione:
- il collo di bottiglia principale non è più solo il posizionamento della lama;
- mancano molte decisioni editoriali e micro-cut che il montatore umano esegue;
- diversi cut automatici non coincidono con le scelte umane;
- l'audio alignment rimane utile, ma viene dopo la corretta classificazione del tipo di intervento.

## ⚠️ PARZIALE / DA RIFINIRE

### Longform: architettura editoriale
La pipeline non deve essere un semplice `transcript -> remove ranges -> waveform`.

Nuova direzione:
1. audio/VAD per pause e speech regions;
2. transcript con word timestamps;
3. rilevamento disfluenze e false partenze;
4. analisi semantica/editoriale;
5. classificazione del tipo di taglio;
6. waveform per il placement finale della lama;
7. Resolve ricostruisce la timeline.

### ARPHE Editorial Profile v0.1

- Pause: accorciare solo quelle eccessive, preservando ritmo umano.
- `ehm`, `eeee`, `mmm`: non rimuovere sempre; solo se la ricucitura resta naturale.
- `allora`, `cioè`, `quindi`, `praticamente`, ecc.: rimuovere solo quando non svolgono realmente funzione nel discorso.
- False partenze: preferire **speech repair** precise, conservando il prefisso buono e riagganciandolo alla continuazione corretta.
- Ripetizioni: preferire la formulazione più chiara/completa.
- Tagli concettuali: livello editoriale separato dai micro-cut.
- Contenuto sensibile/reputazionale: **FLAG ONLY**, mai auto-cut.

Dettagli in `docs/07_EDITORIAL_BENCHMARK.md`.

### Audio-aligned cut V4.x
- V4.2: approccio conservativo, ma ottimizzare separatamente i due bordi può lasciare troppa aria alla giunzione.
- V4.3: ha corretto in modo utile il problema della giunzione con troppo spazio prima della ripartenza del parlato.
- Non è però sufficiente come soluzione editoriale completa: il benchmark mostra che il problema dominante è anche nella selezione dei tagli.

### Reframing estetico dopo tracking
Il tracking può essere tecnicamente corretto ma il soggetto può risultare scentrato durante forti zoom.

Lezione:
**punto di tracking ≠ centro estetico dell'effetto**.

## ❌ NON AFFIDABILE / DA NON USARE COME PRIMITIVA

### Timestamp Whisper usati direttamente come lama
Non usare `start/end` del transcript come cut frame senza margine o allineamento audio.

### Keyword matching puro per filler
Non trattare parole come `allora`, `cioè`, `quindi`, `praticamente` come stopword da cancellare automaticamente.
Serve contesto sintattico/semantico prima e dopo.

### Avvio automatico del tracking da FusionScript
I trigger `TrackForward` / `TrackForwardFromCurrentTime` sono esposti, ma i test hanno prodotto path immobili e range anomali.

## PROSSIMO TEST — BENCHMARK 02

Produrre un **nuovo video mai usato per calibrare il sistema**.

Regola anti-leakage:
1. conservare MP4 originale;
2. generare transcript;
3. congelare il candidate automatico PRIMA di leggere il montaggio umano;
4. montare manualmente il video come risultato desiderato;
5. esportare il reference con `ARPHE_EXPORT_REFERENCE_EDIT_02.py`;
6. confrontare candidate vs reference;
7. classificare mismatch per categoria;
8. aggiornare le regole soltanto dopo il report.

Per ottimizzare i tempi, il prossimo test può essere un video/campione di circa **8–12 minuti** invece di un longform da 35 minuti, purché contenga parlato naturale, pause, filler, false partenze e qualche decisione editoriale reale.
