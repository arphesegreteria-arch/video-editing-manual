# EXPERIMENT LOG

## 2026-09-04 — ARPHE_WINDOWS_BRIDGE_RUNTIME_V1 / deployment PC_SEGRETERIA

### Risultato

Runtime Windows installato realmente sul PC segreteria:

- runtime API key salvata tramite DPAPI per-user;
- task `ARPHE Resolve Bridge Runtime V1 - PC_SEGRETERIA` registrato `At logon`;
- azione background con percorso reale `pythonw.exe`;
- supervisor e tunnel attivi senza PowerShell persistente;
- stato locale: supervisor `ready`, `/readyz` HTTP 200 `ready`;
- riavvio Windows e nuovo login completati;
- ChatGPT `ping` PASS dopo il riavvio;
- ChatGPT `resolve_status` PASS sul Resolve reale dopo il riavvio.

### Problemi trovati e corretti

1. Il rilevamento automatico aveva selezionato l'alias `pyw.exe` sotto `Microsoft\WindowsApps`;
   Task Scheduler terminava con codice `1`. L'installer ora rifiuta gli alias WindowsApps e
   richiede/usa il percorso reale dell'interprete.
2. Windows PowerShell 5.1 aveva scritto `bridge_config.json` con BOM UTF-8; il runtime falliva
   con `JSONDecodeError: Unexpected UTF-8 BOM`. Il lettore ora usa `utf-8-sig` e l'installer
   scrive UTF-8 senza BOM.

### Stato

**AUTOSTART + READ VALIDATED** su `PC_SEGRETERIA`.

Ancora pending: SAFE WRITE tramite runtime persistente, close/reopen Resolve, kill controllato
del tunnel con verifica backoff/restart e audit finale dei log. Nessuna attività sul PC personale.

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

## E08 — Windows Bridge Runtime + replica workstation

Stato: **NEXT / PRIORITÀ IMMEDIATA**.

Ambiente di riferimento:
- `PC_SEGRETERIA` = CURRENT / VALIDATED;
- `PC_PERSONALE` = PENDING REPLICA.

Correzione importante:
**tutti i test E06/E07 del 2026-09-01 sono stati eseguiti sul PC segreteria, non sul PC personale.**

Problema da risolvere:
- oggi il tunnel resta attivo solo finché il processo `tunnel-client-runtime-cloudflared.exe run` resta aperto;
- l'operatore non deve aprire PowerShell ogni volta.

Decisione:
- costruire `ARPHE_WINDOWS_BRIDGE_RUNTIME_V1`;
- ChatGPT resta la UI;
- nessuna GUI desktop di montaggio;
- autostart v1 via Windows Task Scheduler `At logon` nella sessione utente;
- NON usare inizialmente un Windows Service Session 0, per ridurre il rischio di problemi di interazione/IPC con Resolve nella sessione desktop;
- secret storage Windows per la runtime API key;
- health check `/readyz`;
- restart con backoff;
- log redatti;
- install/uninstall/status;
- nessuna operazione Resolve eseguita autonomamente allo startup.

Regola multi-workstation:
- un tunnel per workstation;
- una runtime API key per workstation;
- non copiare la runtime key del PC segreteria sul PC personale;
- condividere codice e template tramite repository.

Naming consigliato:
- `ARPHE-RESOLVE-SEGRETERIA`;
- `ARPHE-RESOLVE-PERSONALE`.

Nota: il tunnel corrente `ARPHE-RESOLVE-HOME` è in realtà collegato al PC segreteria e va considerato nome legacy/fuorviante.

Task adatto a Codex:
- multi-file repository work;
- supervisor Python;
- PowerShell install/autostart/status;
- secret storage;
- test;
- documentazione.

Spec completa:
`docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`.

PASS PC_SEGRETERIA quando:
1. login Windows;
2. nessuna PowerShell manuale;
3. tunnel runtime parte;
4. `/readyz` HTTP 200;
5. ChatGPT `resolve_status` funziona;
6. SAFE WRITE timeline vuota funziona;
7. restart automatico testato;
8. nessun segreto nei log/repo.

PASS PC_PERSONALE solo dopo replica separata e nuovi gate READ + SAFE WRITE.

## E09 — MioDottore Review Social Creative / Fusion

Stato: **BRIDGE IMPLEMENTED / OFFLINE TESTED / GATE A PASS / GATES B-G PENDING / REAL CONTENT BLOCKED**.

Obiettivo:
validare un primo workflow social reale in cui ChatGPT/bridge/Resolve costruiscono una creatività
master 16:9 a partire da un testo recensione, usando Fusion come motion-design layer e mantenendo
il montaggio non distruttivo. La variante 9:16 resta un adattamento successivo, non il master.

Prerequisito prima di usare recensioni reali:
- verificare policy/condizioni MioDottore e requisiti applicabili al riutilizzo promozionale dei testi delle recensioni;
- definire regola definitiva per attribuzione e anonimizzazione/oscuramento del nome;
- fino a quel momento usare esclusivamente testo fittizio nel test tecnico.

Test tecnico proposto:
1. creare una timeline master 16:9 separata;
2. usare un testo recensione fittizio;
3. costruire un primo template Fusion `ARPHE_REVIEW_01` con stelle, text reveal, enfasi della frase chiave e end card ARPHÈ;
4. parametrizzare almeno testo, durata, CTA e background/B-roll;
5. provare almeno una transizione Fusion riutilizzabile;
6. verificare che il template possa essere richiamato/adattato via scripting senza modificare l'originale;
7. produrre una preview, non pubblicarla automaticamente;
8. valutare qualità visiva, robustezza con testi di lunghezze diverse e possibilità di promuovere il risultato nella libreria ARPHÈ.

Estensione successiva, dopo validazione del template base:
- variante `ARPHE_REVIEW_BROLL`;
- famiglie SHORT/MEDIUM per diverse lunghezze di testo;
- test di composizione automatica dei preset;
- modalità ADV sperimentale: Fusion dinamico come collante creativo per asset generati con Runway;
- gli effetti dinamici riusciti vengono revisionati e, se approvati, promossi a preset deterministici della libreria ARPHÈ.

Principio operativo:
**standard social = preset Fusion approvati e parametrizzati; ADV speciali = pipeline ibrida Resolve + Fusion dinamico + eventuale Runway, sempre con preview/approvazione prima del render/pubblicazione finale.**

### Build preparata — 2026-09-04

Creata `ARPHE_MCP_BRIDGE_CREATIVE_03` come build affiancata, senza modificare i bridge
READ_01/SAFE_WRITE_02 e senza cambiare il runtime Windows installato.

Include:
- project/timeline con prefisso, collision guard, registry e no-overwrite;
- Fusion composition, background e Text+ semantici;
- review card, highlight, end card e timing;
- preset `ARPHE_SOFT_DROP`, `ARPHE_PAPER_STACK`, `ARPHE_ELEGANT_REVEAL`, `ARPHE_CTA_SETTLE`;
- asset root e render root allowlisted;
- feature flags progressive, con Render false;
- audit metadata-only senza input, path o segreti;
- installazione affiancata e switch/rollback del solo `MCP_COMMAND`.

Test offline iniziali: 20 PASS, poi estesi a 21 PASS con la correzione delle impostazioni timeline.
Gate A è stato validato con write reali controllate; Gate B-G restano `PENDING`. Gate e criteri
sono definiti in `docs/11_CREATIVE_BRIDGE_AND_E09.md`. Fino al content-use check MioDottore, i
gate tecnici devono usare esclusivamente recensioni fittizie.

### Gate A — primo tentativo reale 2026-09-04

- `create_project`: PASS; creato e selezionato `ARPHE_E09_MIODOTTORE_REVIEWS`, senza overwrite;
- `create_timeline`: PARTIAL/FAIL SAFE; creata `ARPHE_E09_VERTICAL_V1`, ma
  `Timeline.SetSetting` ha rifiutato resolution/FPS dopo la creazione e la timeline è rimasta
  1920x1080/24;
- `get_creative_status`: non eseguito, correttamente, perché la fase precedente aveva `ok=false`;
- nessuna timeline cancellata e nessun progetto/timeline preesistente modificato.

Correzione preparata: applicare e verificare `Project.SetSetting` prima di
`MediaPool.CreateEmptyTimeline`, esclusivamente su un progetto creato/allowlisted dal bridge.
Il retest deve usare nuovi nomi `ARPHE_E09_MIODOTTORE_REVIEWS_V2` e
`ARPHE_E09_VERTICAL_V2`; il primo tentativo resta come evidenza diagnostica.

### Gate A — retest V2 PASS 2026-09-04

- `create_project`: PASS, creato/selezionato `ARPHE_E09_MIODOTTORE_REVIEWS_V2`;
- `create_timeline`: PASS, creata/selezionata `ARPHE_E09_VERTICAL_V2`;
- `Project.SetSetting`: true per width, height e frame rate prima della creazione;
- verifica API: actual 1080x1920, 30 fps, `settings_match=true`;
- `get_creative_status`: PASS su Resolve Studio 21.0.4.5;
- verifica visiva Resolve: timeline `ARPHE_E09_VERTICAL_V2`, 1080x1920, 30.000 fps;
- nessun overwrite e nessuna modifica/cancellazione della V1 o di timeline preesistenti.

Gate A: **PASS** per `create_project`, `create_timeline` e `get_creative_status`.
`set_current_project`, `set_current_timeline`, `duplicate_timeline_version` e `save_project`
restano da validare separatamente; il gruppo capability complessivo non è ancora interamente
`SUPPORTED`.

### Master E09 16:9 — stato di ripartenza

Su decisione creativa dell'utente, il formato principale passa da verticale a 16:9. Il
2026-09-04 sono stati creati tramite le primitive controllate Creative 03:

- progetto `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`;
- timeline `ARPHE_E09_16X9_V1`;
- settings richiesti ed effettivi 1920x1080, 30 fps;
- `settings_match=true`, current timeline impostata, `overwrite=false`;
- read-back Resolve: 1 traccia video, 1 audio, 0 clip.

La timeline verticale V2 non è stata modificata o cancellata. Prossima azione: Gate B sul master
16:9, usando testo fittizio e abilitando esclusivamente `CAP_FUSION`.

## Architettura superata

Il precedente `ARPHE Remote Agent V1` basato su GUI Tkinter + polling GitHub è **SUPERSEDED**.

Alcune idee di sicurezza restano valide (allowlist, path guard, log strutturati, protezione originali), ma il trasporto/UI vengono sostituiti da ChatGPT + MCP + Secure MCP Tunnel.

## Principio di continuità

La chat non deve essere l'unico posto in cui vive lo stato del progetto. Prima di iniziare un nuovo esperimento controllare:
- `CURRENT_STATE.md`;
- `EXPERIMENT_LOG.md`;
- `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`;
- `docs/09_MCP_TUNNEL_ROLLOUT_CHECKLIST.md`;
- `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`;
- `docs/RESOLVE_STUDIO_CAPABILITIES.md`;
- per benchmark editoriali, `docs/07_EDITORIAL_BENCHMARK.md`.
