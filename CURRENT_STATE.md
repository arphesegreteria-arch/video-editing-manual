# CURRENT STATE

Ultimo aggiornamento: sessione 2026-09-01.

## Obiettivo del progetto

Automatizzare il montaggio video in DaVinci Resolve Studio con **ChatGPT come interfaccia primaria per la segreteria**.

Architettura target:

`Segreteria -> ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio API`

Il bridge locale non deve diventare una seconda interfaccia da imparare: serve soltanto a esporre tool controllati a ChatGPT e a tradurre decisioni approvate in operazioni deterministiche.

Funzioni obiettivo:
- selezione media consentiti;
- trascrizione locale;
- cut / remove / reassemble;
- speech repair;
- punch-in e zoom;
- tracking;
- B-roll;
- captions;
- render/export;
- benchmark quantitativo contro montaggi umani.

## ✅ VALIDATO

### DaVinci Resolve Studio — scripting esterno READ
Ambiente testato:
- Resolve Studio `21.0.4.5`;
- Preferences -> System -> General -> `External scripting using = Local`;
- Python eseguito **fuori** da Resolve.

`ARPHE_STUDIO_EXTERNAL_API_TEST_01.py` ha restituito exit code 0 e ha letto correttamente:
- progetto `blabla`;
- timeline `Timeline 1`;
- FPS `30.0`;
- video tracks `1`;
- audio tracks `1`;
- clip V1 `130`;
- clip A1 `130`.

Conclusione:
**Python esterno -> Resolve Studio è funzionante in lettura.** Non siamo più vincolati a `Workspace -> Scripts -> Utility` come architettura principale.

### DaVinci Resolve Studio — scripting esterno SAFE WRITE
`ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02.py` eseguito con successo.

Risultato:
- progetto `blabla`;
- timeline originale `Timeline 1`;
- timeline count prima `2`;
- creata timeline vuota `ARPHE_API_WRITE_TEST_20260901_145018`;
- timeline count dopo `3`;
- `SetCurrentTimeline(original) = True`;
- timeline finale `Timeline 1`;
- exit code `0`.

Conclusione:
**Python esterno -> Resolve Studio WRITE non distruttiva è funzionante.**

Sono validate almeno le primitive:
- `MediaPool.CreateEmptyTimeline()`;
- `Project.SetCurrentTimeline()`.

Questo non promuove automaticamente tutte le operazioni write: import media, rebuild/cut, transform, Fusion, tracking, captions e render vanno ancora testati singolarmente.

### MCP locale -> Resolve Studio READ
`ARPHE_MCP_BRIDGE_READ_01` eseguito con successo.

Tool MCP validate:
- `ping`;
- `resolve_status`.

Risultato:
- protocollo MCP negoziato;
- tool discovery riuscita;
- `ping` OK in modalità `READ_ONLY`;
- `resolve_status` ha letto Resolve `21.0.4.5`, progetto `blabla`, `Timeline 1`, FPS 30, 1 traccia video, 1 audio, 130 clip V1 e 130 clip A1;
- exit code 0;
- nessuna modifica fatta in Resolve.

Conclusione:
**MCP locale -> tool -> bridge Python -> Resolve Studio READ è funzionante.**

Non è ancora validato il tratto `ChatGPT -> Secure MCP Tunnel -> MCP locale`.

Dettagli: `docs/RESOLVE_STUDIO_CAPABILITIES.md` e `EXPERIMENT_LOG.md`.

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

Questo workaround appartiene alla fase Free/manuale: con Studio il tracking automatico deve essere rivalutato da zero prima di conservarlo.

### Trascrizione longform esterna
Workflow con `faster-whisper` testato su `blabla.mp4`:
- JSON `ARPHE_TRANSCRIPT_V1` generato correttamente;
- timestamp a livello segmento e parola;
- durata transcript circa 2095.339 s;
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
- l'audio alignment rimane utile, ma viene dopo la corretta classificazione dell'intervento.

## 🎯 DIREZIONE PRODOTTO — CHATGPT + MCP

ChatGPT è la UI primaria.

Percorso target:

`Segreteria -> ChatGPT -> custom MCP app -> Secure MCP Tunnel -> ARPHE MCP Bridge locale -> Resolve Studio API`

Il bridge locale:
- espone solo tool allowlisted e tipizzati;
- non espone shell/Python arbitrario;
- accede solo a cartelle configurate;
- impone nuova timeline / originale intatto;
- esegue deterministicamente il piano approvato.

### Vincoli ancora da verificare
- piano/workspace ChatGPT effettivamente disponibile per full MCP write;
- Secure MCP Tunnel configurato e raggiungibile;
- ChatGPT -> MCP -> Resolve READ reale;
- write tool MCP innocua e protetta.

## ⚠️ PARZIALE / DA RIFINIRE

### Longform: architettura editoriale
La pipeline non deve essere un semplice `transcript -> remove ranges -> waveform`.

Direzione:
1. audio/VAD per pause e speech regions;
2. transcript con word timestamps;
3. rilevamento disfluenze e false partenze;
4. analisi semantica/editoriale;
5. classificazione del tipo di taglio;
6. waveform per il placement finale della lama;
7. bridge/Resolve ricostruisce una nuova timeline.

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
- V4.2: approccio conservativo, ma i due bordi indipendenti potevano lasciare troppa aria.
- V4.3: ha corretto utilmente il problema della giunzione con troppo spazio prima della ripartenza del parlato.
- Non è sufficiente come soluzione editoriale completa: il benchmark mostra che il problema dominante è anche nella selezione dei tagli.

## ❌ NON USARE COME DIREZIONE PRODOTTO

### GUI desktop ARPHE + coda GitHub
Il precedente design `ARPHE Remote Agent V1` con GUI Tkinter visibile e polling di una coda GitHub è **SUPERSEDED**.

Motivo: la decisione corrente è usare ChatGPT direttamente come interfaccia; il componente locale deve essere un bridge MCP/Resolve, non una seconda UI.

I vecchi documenti sono conservati con un avviso `SUPERSEDED` per memoria progettuale.

### Timestamp Whisper usati direttamente come lama
Non usare `start/end` del transcript come cut frame senza margine o allineamento audio.

### Keyword matching puro per filler
Non trattare parole come `allora`, `cioè`, `quindi`, `praticamente` come stopword da cancellare automaticamente.

## PROSSIMI TEST — DUE TRACK PARALLELI

### Track A — infrastruttura ChatGPT / Resolve
1. Configurare Secure MCP Tunnel verso il server MCP locale read-only già validato.
2. Collegare la custom app a ChatGPT.
3. Validare `ChatGPT -> MCP -> Resolve READ` chiamando `resolve_status` dalla conversazione.
4. Solo dopo esporre `create_safe_working_timeline` e validare `ChatGPT -> MCP -> Resolve WRITE`.
5. Poi testare singolarmente import media, rebuild/cut, transform, Fusion, tracking, captions e render.

### Track B — Benchmark 02 editoriale
1. Prendere un estratto podcast autonomo di circa 8–15 minuti.
2. Trattarlo da `00:00` come unica sorgente canonica.
3. Generare transcript.
4. Congelare il candidate automatico PRIMA del montaggio umano.
5. Montare manualmente lo stesso estratto.
6. Esportare reference e confrontare.
7. Classificare i mismatch per categoria e aggiornare le regole solo dopo il report.
