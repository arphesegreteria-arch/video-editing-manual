# CHANGELOG

## 2026-09-01 — Benchmark editoriale + profilo v0.1

### Benchmark 01
- creato reference umano da timeline Resolve tramite `ARPHE_EXPORT_REFERENCE_EDIT_02.py`;
- confronto contro `ARPHE_LONGFORM_SAFE_EDIT_PLAN_V3`;
- Precision 0.522;
- Recall 0.430;
- F1 0.472;
- false positive 197.5 s;
- false negative 286.1 s;
- 48 boundary matched su 246;
- mean boundary error 625 ms;
- median boundary error 373 ms.

### Lezione principale
Il collo di bottiglia non è soltanto il posizionamento della lama.
Prima del waveform alignment bisogna migliorare la selezione editoriale e il rilevamento di micro-cut/speech repair.

### ARPHE Editorial Profile v0.1
- pause: accorciare quelle eccessive senza azzerare il ritmo;
- vocalizzi (`ehm`, `eeee`, `mmm`): non eliminarli sempre, solo quando la ricucitura resta naturale;
- filler linguistici: rimuovere solo quando non svolgono realmente funzione nel discorso;
- false partenze: preferire ricuciture precise conservando il prefisso buono;
- ripetizioni: preferire la formulazione più chiara/completa;
- tagli concettuali: livello editoriale separato dai micro-cut;
- contenuto sensibile/reputazionale: FLAG ONLY, mai auto-cut.

### Nuovo protocollo di sviluppo
- congelare il candidate automatico prima di leggere il reference umano;
- usare un secondo video mai visto per misurare la generalizzazione;
- classificare mismatch per categoria;
- ottimizzare una categoria alla volta;
- per iterazioni rapide usare campioni di circa 8–12 minuti invece di 35 minuti quando possibile.

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
