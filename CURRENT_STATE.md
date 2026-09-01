# CURRENT STATE

Ultimo aggiornamento: sessione 2026-09-01.

## Obiettivo del progetto

Automatizzare il montaggio video in DaVinci Resolve Studio con **ChatGPT come interfaccia primaria per la segreteria**.

Architettura corrente validata:

`Segreteria -> ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio API`

Il bridge locale è infrastruttura: espone solo tool allowlisted, valida gli input e traduce le decisioni approvate in operazioni deterministiche. La segreteria non deve usare Python, JSON o una GUI ARPHE separata.

## Workstation — stato ufficiale

### PC_SEGRETERIA — CURRENT / VALIDATED

**Tutti i test end-to-end del 2026-09-01 descritti sotto sono stati eseguiti sul PC della segreteria, non sul PC personale.**

Root locale corrente:

`C:\ARPHE\MCP\`

Il tunnel usato nei test è `ARPHE-RESOLVE-HOME`; il nome è legacy/fuorviante perché il runtime è sul PC segreteria. Quando possibile rinominarlo in `ARPHE-RESOLVE-SEGRETERIA`, oppure mantenere il nome legacy documentando il mapping.

### PC_PERSONALE — PENDING REPLICA

Il PC personale non è ancora configurato né validato.

La replica dovrà usare:
- stesso codice/versioni controllate tramite repository;
- tunnel dedicato;
- runtime API key dedicata;
- config locale dedicata;
- nuovi gate READ + SAFE WRITE end-to-end.

Non copiare la runtime API key del PC segreteria sul PC personale.

Dettagli: `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`.

## ✅ MILESTONE PRINCIPALE — END-TO-END VALIDATO

### ChatGPT -> Resolve READ
Da una normale conversazione ChatGPT, tramite la app DEV `ARPHE Resolve`, è stata chiamata realmente `resolve_status`.

Risultato restituito dal Resolve aperto:
- Resolve Studio `21.0.4.5`;
- progetto `blabla`;
- timeline `Timeline 1`;
- FPS `30.0`;
- video tracks `1`;
- audio tracks `1`;
- clip V1 `130`;
- clip A1 `130`.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> MCP locale -> Resolve Studio READ è VALIDATED end-to-end.**

### ChatGPT -> Resolve SAFE WRITE
Bridge: `ARPHE_MCP_BRIDGE_SAFE_WRITE_02`.
App DEV: `ARPHE Resolve WRITE Test`.
Tool: `create_safe_working_timeline`.

Risultato della chiamata eseguita direttamente da ChatGPT:
- progetto `blabla`;
- timeline originale `Timeline 1`;
- timeline count prima `3`;
- creata timeline vuota `ARPHE_CHATGPT_WRITE_TEST_20260901_185749`;
- timeline count dopo `4`;
- incremento verificato `true`;
- ritorno automatico alla timeline originale `true`;
- timeline finale `Timeline 1`;
- clip edit `0`;
- timeline delete `0`;
- tool result `ok=true`.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python -> Resolve Studio SAFE WRITE è VALIDATED end-to-end** per la primitiva non distruttiva testata.

Questo è il primo controllo reale di Resolve in scrittura dalla chat.

## ✅ INFRASTRUTTURA VALIDATA

### Resolve Studio external scripting
Ambiente:
- Windows;
- Resolve Studio `21.0.4.5`;
- Preferences -> System -> General -> `External scripting using = Local`;
- Python esterno.

Validato:
- import `DaVinciResolveScript`;
- connessione a Resolve;
- lettura progetto/timeline/FPS/tracce/item;
- `MediaPool.CreateEmptyTimeline()`;
- `Project.SetCurrentTimeline()`.

### MCP locale
`ARPHE_MCP_BRIDGE_READ_01`:
- protocollo MCP OK;
- tool discovery OK;
- `ping` OK;
- `resolve_status` OK;
- nessuna modifica in modalità READ.

### Secure MCP Tunnel
- tunnel attuale sul PC segreteria: `ARPHE-RESOLVE-HOME` (nome legacy);
- runtime Windows: `tunnel-client-runtime-cloudflared`;
- runtime API key Restricted con Tunnels Read + Use;
- MCP locale collegato via `MCP_COMMAND` stdio;
- health listener `127.0.0.1:8080`;
- `/readyz` -> `HTTP/1.1 200 OK`, body `ready`.

Nota: la build `runtime-cloudflared` non espone `/ui`; `/readyz` è il gate usato.

## Sicurezza corrente

Principi obbligatori:
- tool allowlisted, mai shell/Python arbitrario;
- cartelle esplicitamente consentite;
- path validation;
- mai sovrascrivere la timeline originale;
- ogni montaggio crea una nuova timeline;
- write action piccole e verificabili;
- contenuti sensibili/reputazionali: **FLAG ONLY**, mai auto-cut;
- separare decisione editoriale da esecuzione deterministica;
- una runtime API key per workstation;
- nessun segreto nella repository.

## ⚠️ NON ANCORA VALIDATO END-TO-END

Restano da provare singolarmente via bridge esterno/MCP:
- import media;
- rebuild/cut da edit plan;
- TimelineItem transforms;
- Fusion create/read/write;
- tracking Studio / IntelliTrack;
- captions/subtitles;
- render/export.

Un'operazione non diventa `SUPPORTED` solo perché esiste nella documentazione API: deve essere testata nel nostro ambiente.

## 📊 TRACK EDITORIALE

Benchmark umano su `blabla.mp4` contro `ARPHE_LONGFORM_SAFE_EDIT_PLAN_V3`:
- Precision `0.522`;
- Recall `0.430`;
- F1 `0.472`;
- false positive `197.5 s`;
- false negative `286.1 s`;
- boundary matched `48 / 246`;
- mean boundary error `625 ms`;
- median boundary error `373 ms`.

Lezione: il collo di bottiglia principale è la **decisione editoriale**, non soltanto il placement fisico della lama. Waveform/audio serve per `dove`, ChatGPT/profilo editoriale serve per `cosa`.

### ARPHE Editorial Profile v0.1
- pause: accorciare quelle eccessive preservando ritmo naturale;
- `ehm/eeee/mmm`: non rimuovere sempre;
- filler linguistici: rimuovere solo quando non svolgono funzione;
- false partenze: preferire speech repair precisa conservando il prefisso buono;
- ripetizioni: preferire la formulazione più chiara/completa;
- tagli concettuali: livello editoriale separato;
- contenuto sensibile/reputazionale: **FLAG ONLY**.

## PROSSIMO PERCORSO

### Track A0 — infrastruttura Windows, PRIORITÀ IMMEDIATA

Ora che READ e SAFE WRITE end-to-end sono validati, il prossimo step è rimuovere la dipendenza dalla PowerShell aperta manualmente sul PC segreteria.

Implementare `ARPHE_WINDOWS_BRIDGE_RUNTIME_V1` come processo background nella sessione utente, avviato tramite Windows Task Scheduler `At logon`, con:
- secret storage Windows;
- tunnel runtime automatico;
- health check `/readyz`;
- restart con backoff;
- log redatti;
- install/uninstall/status;
- nessuna GUI di montaggio;
- nessuna write Resolve eseguita autonomamente allo startup.

Questo task è adatto a Codex. Specifica: `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`.

### Track A1 — prodotto ChatGPT / Resolve
1. Consolidare le tool validate in un unico bridge/app DEV.
2. Aggiungere `list_media` limitato a una cartella allowlisted.
3. Aggiungere `transcribe_media` con faster-whisper locale.
4. Permettere a ChatGPT di leggere transcript/chunk e proporre decisioni editoriali.
5. Implementare `apply_edit_plan` minimale su una sorgente di test, sempre creando una nuova timeline.
6. Validare rebuild/cut via MCP end-to-end.
7. Solo dopo ampliare a transform, Fusion, captions, render e tracking.

### Track A2 — replica PC personale
Dopo il PASS del runtime persistente sul PC segreteria:
1. installare lo stesso stack sul PC personale;
2. creare tunnel `ARPHE-RESOLVE-PERSONALE`;
3. creare runtime API key dedicata;
4. installare autostart;
5. collegare app ChatGPT dedicata;
6. ripetere READ + SAFE WRITE;
7. dichiarare il PC personale validato solo dopo entrambi i gate.

### Track B — Benchmark 02 editoriale
1. Usare un estratto podcast autonomo di circa 8–15 minuti.
2. Trattarlo da `00:00` come unica sorgente canonica.
3. Generare transcript.
4. Congelare il candidate automatico prima del montaggio umano.
5. Montare manualmente lo stesso estratto.
6. Esportare reference e confrontare.
7. Classificare mismatch e aggiornare le regole solo dopo il report.

## Direzione scartata

La vecchia GUI desktop ARPHE + polling GitHub (`ARPHE Remote Agent V1`) è **SUPERSEDED**. ChatGPT è la UI primaria; il componente locale deve restare un bridge MCP/Resolve.

Dettagli persistenti:
- `EXPERIMENT_LOG.md`;
- `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`;
- `docs/09_MCP_TUNNEL_ROLLOUT_CHECKLIST.md`;
- `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`;
- `docs/RESOLVE_STUDIO_CAPABILITIES.md`;
- `docs/07_EDITORIAL_BENCHMARK.md`.
