# CHANGELOG

## 2026-08-27 — Longform transcript + audio alignment

### Validato
- trascrizione esterna con `faster-whisper` in JSON `ARPHE_TRANSCRIPT_V1`;
- timestamp a livello segmento e parola utili per paper edit;
- diagnostica timing su `blabla.mp4`: sorgente 30 fps, timeline 30 fps, 62860 frame, durata Resolve e Whisper coerenti;
- il problema delle parole troncate non era drift FPS nel test;
- ricostruzione timeline resta la primitiva corretta per applicare i cut senza toccare l'originale.

### Osservato nei rough cut
- usare direttamente i timestamp Whisper come edit point produce cut troppo vicini alle parole;
- restano pause lunghe se non vengono trattate separatamente;
- un bordo video/audio apparentemente allineato può comunque contenere troppo silenzio prima del parlato: non è necessariamente vero fuori-sync.

### Nuova architettura
- ChatGPT decide semanticamente **cosa** togliere;
- Whisper localizza/protegge le parole;
- un analizzatore locale legge la waveform reale e raffina i confini;
- Resolve applica gli intervalli raffinati ricostruendo una nuova timeline.

Principio:
**decisione editoriale ≠ posizione fisica della lama**.

### V4.x
- V4.2: primo audio align conservativo; osservata troppa aria in alcune giunzioni.
- V4.3: candidato corrente con giunzioni più compatte; ancora da revisionare integralmente prima della promozione a validato.

### Regole aggiunte
- non promuovere V4.3 a `validated` finché il longform non è stato guardato per intero;
- distinguere vero offset A/V da semplice silenzio contenuto nella clip;
- revisione umana obbligatoria anche quando l'audio cut è corretto, perché il jump cut visivo può restare brutto;
- la futura interfaccia per segreteria deve nascondere la complessità tecnica dietro pochi passaggi o un solo pulsante.

## 2026-08-25 — Sessione iniziale

### Validato
- esecuzione script Python dentro Resolve;
- lettura progetto/timeline;
- ricostruzione timeline per cut;
- zoom statico via TimelineItem;
- Fusion Transform;
- `BezierSpline` per yoyo;
- creazione Tracker da script;
- tracking manuale nativo + lettura path da Python.

### Scartato come base di produzione
- simulare yoyo con micro-tagli;
- usare il Tracker in serie verso MediaOut;
- affidarsi al trigger automatico `TrackForward` via FusionScript nella build corrente.

### Regole aggiunte
- mai modificare l'originale;
- tracking sempre limitato al range utile;
- tracking anchor separato dal centro estetico;
- ogni passaggio manuale spiegato click-per-click.
