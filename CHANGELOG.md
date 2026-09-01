# CHANGELOG

## 2026-09-01 — ChatGPT -> MCP -> Resolve READ + SAFE WRITE end-to-end validati

### READ end-to-end
- custom app DEV `ARPHE Resolve` collegata al tunnel `ARPHE-RESOLVE-HOME`;
- autenticazione MCP: None;
- chiamata `resolve_status` eseguita direttamente dalla conversazione ChatGPT;
- letti Resolve `21.0.4.5`, progetto `blabla`, `Timeline 1`, 30 fps, 1 traccia video, 1 audio, 130 clip V1 e 130 clip A1.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> MCP locale -> Resolve Studio READ è supportato end-to-end.**

### SAFE WRITE end-to-end
- bridge `ARPHE_MCP_BRIDGE_SAFE_WRITE_02` avviato tramite lo stesso tunnel;
- `/readyz` -> HTTP 200 `ready`;
- app DEV `ARPHE Resolve WRITE Test` collegata;
- `ping` da ChatGPT ha confermato `SAFE_WRITE` e `create_safe_working_timeline` abilitata;
- ChatGPT ha chiamato `create_safe_working_timeline`;
- timeline count: `3 -> 4`;
- creata `ARPHE_CHATGPT_WRITE_TEST_20260901_185749`;
- ritorno automatico a `Timeline 1`: `true`;
- clip edit: `0`;
- timeline delete: `0`;
- tool result: `ok=true`.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python -> Resolve Studio SAFE WRITE è supportato end-to-end** per la primitiva non distruttiva testata.

Prossima priorità: `list_media` allowlisted -> `transcribe_media` locale -> `apply_edit_plan` minimale su nuova timeline.

## 2026-09-01 — External Resolve WRITE validato

### Test `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`
- eseguito da Python esterno con Resolve Studio aperto;
- progetto `blabla`;
- timeline originale `Timeline 1`;
- timeline count prima `2`;
- creata timeline vuota `ARPHE_API_WRITE_TEST_20260901_145018`;
- timeline count dopo `3`;
- ritorno automatico all'originale riuscito (`True`);
- timeline finale `Timeline 1`;
- exit code `0`.

Conclusione:
**Python esterno -> Resolve Studio WRITE non distruttiva è supportato nel nostro ambiente** almeno per `CreateEmptyTimeline` e `SetCurrentTimeline`.

La prossima priorità infrastrutturale diventa il transport gate:
`ChatGPT -> Secure MCP Tunnel -> MCP locale -> Resolve READ`.

## 2026-09-01 — MCP locale -> Resolve READ validato

### Test MCP `ARPHE_MCP_BRIDGE_READ_01`
- installato/usato Python MCP SDK v2 per il prototipo locale;
- protocollo MCP negoziato correttamente;
- tool discovery riuscita: `ping`, `resolve_status`;
- `ping` ha confermato modalità `READ_ONLY` e write tool disabilitate;
- `resolve_status` ha raggiunto DaVinci Resolve Studio attraverso il bridge Python;
- letto Resolve `21.0.4.5`, progetto `blabla`, `Timeline 1`, FPS 30, 1 traccia video, 1 audio, 130 clip V1 e 130 clip A1;
- exit code 0;
- nessuna modifica fatta in Resolve.

Conclusione:
**MCP locale -> tool -> bridge Python -> Resolve Studio READ è supportato nel nostro ambiente.**

Non è ancora validato il tratto cloud `ChatGPT -> Secure MCP Tunnel -> MCP locale`.

## 2026-09-01 — Resolve Studio external API + ChatGPT/MCP pivot

### Resolve Studio
- installato/testato DaVinci Resolve Studio `21.0.4.5`;
- impostato `External scripting using = Local`;
- `ARPHE_STUDIO_EXTERNAL_API_TEST_01` eseguito da Python esterno con exit code 0;
- letti correttamente progetto `blabla`, `Timeline 1`, 30 fps, 1 traccia video, 1 audio, 130 item V1 e 130 item A1;
- conclusione: **external READ API supported** nel nostro ambiente;
- preparato `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02` come probe non distruttivo.

### Nuova direzione prodotto
La segreteria deve usare **ChatGPT come interfaccia primaria**, non una GUI ARPHE separata.

Architettura target:

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio API`

Il bridge è infrastruttura: tool allowlisted, validazione, accesso controllato ai media e operazioni deterministiche su Resolve.

### Ricerca MCP
Verificata la fattibilità concettuale sulle fonti correnti:
- custom MCP app in ChatGPT possono esporre tool e, con full MCP, write/modify;
- full MCP write è attualmente beta su Business, Enterprise ed Edu web;
- Pro può collegare custom MCP in read/fetch ma non full write al momento;
- server MCP locali/private network richiedono Secure MCP Tunnel per essere raggiunti da ChatGPT senza esposizione pubblica;
- `tunnel-client` può inoltrare a MCP locale via stdio/HTTP;
- SDK Python MCP v2 scelto come base del prototipo.

### Cleanup architetturale
- creato `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`;
- creato `docs/RESOLVE_STUDIO_CAPABILITIES.md`;
- aggiornati README, START_HERE, CURRENT_STATE, INDEX, setup, longform, operator guide, roadmap ed EXPERIMENT_LOG;
- vecchio design `ARPHE Remote Agent V1` GUI + GitHub polling dichiarato **SUPERSEDED**;
- mantenuti i suoi principi di sicurezza utili: allowlist, path guard, original timeline protection, log strutturati.

### Podcast benchmark
- usare estratti autonomi di circa 8–15 minuti;
- una volta esportato l'estratto, tutti i timestamp ripartono da `00:00`;
- nessun mapping al timecode del podcast completo durante l'esperimento;
- candidate automatico congelato prima del reference umano.

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
- usare materiale mai visto per misurare la generalizzazione;
- classificare mismatch per categoria;
- ottimizzare una categoria alla volta;
- per iterazioni rapide usare estratti/campioni invece di longform completi.

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

### Nuova architettura editoriale emersa allora
- ChatGPT decide semanticamente **cosa** togliere;
- Whisper localizza/protegge le parole;
- un analizzatore locale legge la waveform reale e raffina i confini;
- Resolve applica gli intervalli raffinati ricostruendo una nuova timeline.

Principio ancora valido:
**decisione editoriale ≠ posizione fisica della lama**.

### V4.x
- V4.2: primo audio align conservativo; osservata troppa aria in alcune giunzioni.
- V4.3: candidato con giunzioni più compatte; ha corretto il problema specifico della troppa aria, ma non risolve da solo la selezione editoriale.

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
- affidarsi al trigger automatico `TrackForward` via FusionScript nella build Free testata.

### Regole aggiunte
- mai modificare l'originale;
- tracking sempre limitato al range utile;
- tracking anchor separato dal centro estetico;
- ogni passaggio manuale spiegato click-per-click.
