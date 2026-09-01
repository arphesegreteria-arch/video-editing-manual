# EXPERIMENT LOG

Scopo: tenere un registro persistente degli esperimenti, dei file coinvolti, dell'ipotesi testata, del risultato e del prossimo passo. Questo file deve impedire di perdere il filo quando arrivano nuovi MP4, transcript, edit plan, reference JSON e report.

## Regola generale

Ogni nuovo esperimento deve avere:
- ID esperimento;
- sorgente/video;
- file input;
- candidate automatico congelato prima del reference umano quando si tratta di benchmark editoriale;
- reference umano;
- report di confronto;
- risultato;
- decisione: validated / partial / rejected;
- prossimo passo.

## E01 — Auto-cut shortform

Stato: VALIDATED.

Risultato:
- ricostruzione timeline con `AppendToTimeline` funziona;
- originale preservato;
- preferire ricostruzione a blade diretto.

## E02 — Yoyo / Fusion / Tracking

Stato: PARTIAL / proof of concept.

Risultato:
- Transform + BezierSpline validati;
- tracking manuale nativo + lettura path da Python funziona;
- auto TrackForward via FusionScript non affidabile nella build Free;
- tracking anchor e centro estetico devono restare separati.

## E03 — Longform transcript + rough cut

Sorgente: `blabla.mp4`.

Passaggi:
- trascrizione `faster-whisper` con word timestamps;
- timing diagnostic: source e timeline 30 fps, nessun drift rilevante;
- V1/V2 rough cut: troppo aggressivi / parole troncate;
- V3 safe cut: migliorato ma ancora incompleto;
- V4.2 waveform alignment: riduce parole troncate ma lascia troppa aria in alcune giunzioni;
- V4.3: corregge meglio la giunzione, ma non risolve il problema editoriale principale.

Decisione:
- waveform = strumento per `dove tagliare`, non per `cosa tagliare`.

## E04 — Benchmark umano 01

Sorgente: `blabla.mp4`.
Reference: `ARPHE_REFERENCE_EDIT_Timeline_1.json`.
Candidate: `ARPHE_LONGFORM_SAFE_EDIT_PLAN_V3`.

Metriche:
- Precision 0.522
- Recall 0.430
- F1 0.472
- False positive 197.5 s
- False negative 286.1 s
- Boundary matched 48 / 246
- Mean boundary error 625 ms
- Median boundary error 373 ms

Interpretazione:
- molti tagli umani non vengono rilevati;
- diversi tagli automatici non coincidono con la scelta umana;
- il boundary placement resta da migliorare ma non è il collo di bottiglia principale.

Profilo editoriale emerso:
- pause: accorciare ma preservare ritmo naturale;
- `ehm/eeee/mmm`: non rimuovere sempre;
- filler: rimuovere solo se non portano a nulla;
- false partenze: preferire speech repair precisa, conservando il prefisso buono e ricucendo alla continuazione corretta;
- tagli concettuali: livello editoriale separato;
- contenuto sensibile: FLAG ONLY, mai auto-cut.

## E05 — Podcast excerpt benchmark

Stato: NEXT / PARALLEL TRACK.

Workflow:
1. Individuare un intervallo podcast utile, idealmente 8–15 minuti.
2. Esportarlo come MP4 autonomo **prima** del montaggio editoriale.
3. Da quel momento ignorare il timecode del podcast completo.
4. `SOURCE_EXCERPT` parte da `00:00` ed è l'unica sorgente canonica.
5. Generare transcript.
6. Generare e congelare il candidate automatico PRIMA del reference umano.
7. Montare manualmente la stessa SOURCE_EXCERPT.
8. Esportare reference con `ARPHE_EXPORT_REFERENCE_EDIT_02.py`.
9. Confrontare con `ARPHE_COMPARE_CUTS_01.py`.
10. Classificare mismatch e aggiornare le regole solo dopo il report.

Naming consigliato:
- `E05_SOURCE_EXCERPT.mp4`
- `E05_TRANSCRIPT.json`
- `E05_CANDIDATE_V1.json`
- `E05_REFERENCE.json`
- `E05_REPORT.txt`

## E06 — DaVinci Resolve Studio external API

Stato: **READ API VALIDATED / WRITE TEST NEXT**.

### Test 01 — lettura esterna

Ambiente:
- DaVinci Resolve Studio `21.0.4.5`;
- `External scripting using = Local`;
- Python esterno.

Risultato:
- import `DaVinciResolveScript`: OK;
- connessione: OK;
- progetto: `blabla`;
- timeline: `Timeline 1`;
- FPS: `30.0`;
- video tracks: `1`;
- audio tracks: `1`;
- clip V1: `130`;
- clip A1: `130`;
- exit code: `0`.

Conclusione:
**Python esterno -> Resolve Studio READ è VALIDATED.**

### Test 02 — scrittura esterna non distruttiva

Stato: da eseguire.

`ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02` deve:
- creare una timeline vuota con nome univoco;
- verificare l'incremento del numero timeline;
- tornare automaticamente alla timeline originale;
- non toccare clip o timeline originale.

## E07 — ChatGPT MCP Bridge

Stato: **LOCAL MCP -> RESOLVE READ VALIDATED / TUNNEL NEXT**.

### Ricerca 2026-09-01

Direzione prodotto:
`Segreteria -> ChatGPT -> custom MCP app -> Secure MCP Tunnel -> ARPHE MCP Bridge locale -> Resolve Studio API`

ChatGPT resta la UI primaria; il bridge locale è infrastruttura e non una seconda applicazione per l'operatore.

### Test locale MCP READ 01

Pacchetto: `ARPHE_MCP_BRIDGE_READ_01`.

Tool esposte:
- `ping`;
- `resolve_status`.

Risultato osservato:
- protocollo MCP negoziato correttamente;
- tool discovery: `ping`, `resolve_status`;
- `ping`: OK, mode `READ_ONLY`, write tools disabilitate;
- `resolve_status`: OK;
- Resolve `21.0.4.5`;
- progetto `blabla`;
- timeline `Timeline 1`;
- timeline FPS `30.0`;
- playback FPS `30`;
- video tracks `1`;
- audio tracks `1`;
- clip V1 `130`;
- clip A1 `130`;
- exit code `0`;
- nessuna modifica fatta in Resolve.

Conclusione:
**MCP locale -> tool -> bridge Python -> Resolve Studio READ è VALIDATED.**

Questo test valida l'MCP locale e la traduzione tool -> Resolve, ma NON ancora il tratto ChatGPT/cloud -> tunnel -> MCP locale.

### Gate successivi E07

1. Completare E06 Write Test 02.
2. Configurare Secure MCP Tunnel verso `ARPHE_MCP_BRIDGE_READ_01`.
3. Collegare la custom app a ChatGPT.
4. Chiamare `resolve_status` direttamente da ChatGPT e validare `ChatGPT -> MCP -> Resolve READ`.
5. Solo dopo aggiungere una write tool innocua `create_safe_working_timeline`.
6. Validare `ChatGPT -> MCP -> Resolve WRITE` su timeline nuova e originale intatto.
7. Successivamente aggiungere tool allowlisted per media, trascrizione, edit plan, benchmark e render.

## Architettura superata

Il precedente `ARPHE Remote Agent V1` basato su GUI Tkinter + polling GitHub è **SUPERSEDED**.

Alcune idee di sicurezza restano valide (allowlist, path guard, log strutturati, protezione originali), ma il trasporto/UI vengono sostituiti da ChatGPT + MCP + Secure MCP Tunnel.

## Principio di continuità

La chat non deve essere l'unico posto in cui vive lo stato del progetto. Prima di iniziare un nuovo esperimento controllare:
- `CURRENT_STATE.md`;
- `EXPERIMENT_LOG.md`;
- `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`;
- `docs/RESOLVE_STUDIO_CAPABILITIES.md`;
- per benchmark editoriali, `docs/07_EDITORIAL_BENCHMARK.md`.
