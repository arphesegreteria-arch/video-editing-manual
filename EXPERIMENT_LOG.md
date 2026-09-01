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

Stato: **READ + SAFE WRITE VALIDATED**.

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

Script: `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02.py`.

Risultato osservato:
- progetto: `blabla`;
- timeline originale: `Timeline 1`;
- timeline count prima: `2`;
- creata timeline vuota `ARPHE_API_WRITE_TEST_20260901_145018`;
- timeline count dopo: `3`;
- ritorno all'originale: `True`;
- timeline finale: `Timeline 1`;
- exit code: `0`.

Conclusione:
**Python esterno -> Resolve Studio WRITE non distruttiva è VALIDATED.**

Sono supportate nel nostro ambiente almeno:
- `MediaPool.CreateEmptyTimeline()`;
- `Project.SetCurrentTimeline()`.

Il test non dimostra ancora che tutte le altre operazioni write siano affidabili: import, cut/rebuild, transform, Fusion, tracking, captions e render restano da provare singolarmente.

## E07 — ChatGPT MCP Bridge

Stato: **END-TO-END READ + SAFE WRITE VALIDATED**.

### Architettura

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

### Secure MCP Tunnel — 2026-09-01

Configurazione locale:
- bridge in `C:\ARPHE\MCP\...`;
- runtime `tunnel-client-runtime-cloudflared` su Windows;
- runtime API key Restricted con permessi Tunnels Read + Use;
- tunnel `ARPHE-RESOLVE-HOME`;
- `MCP_COMMAND` con path Windows normalizzato usando `/`;
- stdio MCP command avviato;
- control-plane poller avviato;
- metadata tunnel recuperati;
- health listener su `127.0.0.1:8080`;
- `GET /readyz` -> `HTTP/1.1 200 OK`, body `ready`.

Conclusione:
**Secure MCP Tunnel runtime -> MCP locale è VALIDATED.**

Nota: la build `runtime-cloudflared` non espone `/ui`; `/readyz` è il gate di salute usato.

### ChatGPT custom app READ

Workspace ChatGPT Business.

App draft DEV:
- nome: `ARPHE Resolve`;
- connessione: Tunnel;
- tunnel: `ARPHE-RESOLVE-HOME`;
- autenticazione MCP: None.

Test dalla conversazione:
- ChatGPT ha chiamato realmente `resolve_status`;
- risposta: Resolve `21.0.4.5`, progetto `blabla`, timeline `Timeline 1`, 30 fps, 1 traccia video, 1 audio, 130 clip V1, 130 clip A1.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> MCP locale -> Resolve Studio READ è VALIDATED end-to-end.**

### ChatGPT custom app SAFE WRITE

Bridge: `ARPHE_MCP_BRIDGE_SAFE_WRITE_02`.
App draft DEV: `ARPHE Resolve WRITE Test`.
Tool write allowlisted:
- `create_safe_working_timeline`.

Preflight:
- bridge SAFE WRITE avviato tramite lo stesso tunnel;
- `/readyz` -> `HTTP/1.1 200 OK`, body `ready`;
- `ping` da ChatGPT: `mode=SAFE_WRITE`, `write_tools_enabled=true`.

Test dalla conversazione:
- ChatGPT ha chiamato `create_safe_working_timeline` con prefisso `ARPHE_CHATGPT_WRITE_TEST`;
- progetto: `blabla`;
- timeline originale: `Timeline 1`;
- timeline count prima: `3`;
- creata timeline vuota: `ARPHE_CHATGPT_WRITE_TEST_20260901_185749`;
- timeline count dopo: `4`;
- incremento count verificato: `true`;
- ritorno automatico all'originale: `true`;
- timeline finale: `Timeline 1`;
- clip edit eseguiti: `0`;
- timeline cancellate: `0`;
- risultato tool: `ok=true`.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python -> Resolve Studio SAFE WRITE è VALIDATED end-to-end.**

Questa validazione dimostra il controllo reale da ChatGPT in scrittura per una primitiva non distruttiva allowlisted; NON valida ancora import media, cut/rebuild, transform, Fusion, tracking, captions o render.

### Gate successivi E07

1. Consolidare le tool validate in un unico bridge/app DEV mantenendo allowlist e protezione originali.
2. Aggiungere `list_media` su cartella esplicitamente consentita.
3. Aggiungere `transcribe_media` con faster-whisper locale.
4. Esporre preview/lettura transcript a ChatGPT.
5. Implementare `apply_edit_plan` minimale su una sorgente di test creando sempre una nuova timeline.
6. Validare il rebuild/cut via MCP end-to-end.
7. Pubblicare nel workspace solo dopo una policy chiara per le write action e dopo i test fondamentali.

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
