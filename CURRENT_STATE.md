# CURRENT STATE

Ultimo aggiornamento: sessione 2026-09-04.

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

### ARPHE_MCP_BRIDGE_CREATIVE_03 — IMPLEMENTED / OFFLINE TESTED

Build modulare aggiunta per E09 MioDottore Review Social Creative. Mantiene `ping`,
`resolve_status` e `create_safe_working_timeline`, aggiunge primitive semantiche per
project/timeline, Fusion, review card, motion, asset e preview, senza tool generiche o delete.

Default release:
- `CAP_PROJECT=true`, `CAP_TIMELINE=true` per Gate A;
- `CAP_FUSION=false`, `CAP_REVIEW=false`, `CAP_MOTION=false`, `CAP_ASSETS=false`,
  `CAP_RENDER=false` fino ai gate reali;
- Gate A `create_project` / `create_timeline` / `get_creative_status`: `SUPPORTED` con evidenza
  reale; le altre primitive project/timeline e i Gate B-G restano `PENDING`.

Codice: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/`.
Spec/gate/rollback: `docs/11_CREATIVE_BRIDGE_AND_E09.md`.

Gate A, primo tentativo reale 2026-09-04: `create_project` PASS senza overwrite;
`create_timeline` ha creato una V1 separata ma Resolve ha rifiutato resolution/FPS impostati
dopo la creazione, lasciandola 1920x1080/24. La sequenza si è fermata con `ok=false`, senza
cancellazioni. Dopo la correzione `Project.SetSetting` pre-creazione, il retest V2 è **PASS**:
progetto `ARPHE_E09_MIODOTTORE_REVIEWS_V2`, timeline `ARPHE_E09_VERTICAL_V2`, 1080x1920/30,
conferma API e visiva, nessun overwrite. Selezione/versioning/save restano PENDING.

Decisione creativa successiva: il master E09 sarà 16:9, non una Story verticale. Creati e
verificati senza overwrite il progetto `ARPHE_E09_MIODOTTORE_REVIEWS_16X9` e la timeline
`ARPHE_E09_16X9_V1`, 1920x1080/30, attualmente vuota e corrente in Resolve. La V2 verticale
resta conservata come evidenza Gate A. Prossimo punto di ripartenza: Gate B Fusion sul master
16:9, abilitando soltanto `CAP_FUSION`.

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

### Track A0 — infrastruttura Windows, DEPLOYED / READ VALIDATED

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

Stato 2026-09-04: `ARPHE_WINDOWS_BRIDGE_RUNTIME_V1` è installato sul solo `PC_SEGRETERIA`.
La runtime API key è protetta con DPAPI per-user e il tunnel parte tramite Task Scheduler
`At logon`, usando `pythonw.exe` senza PowerShell persistente. Dopo un riavvio completo e nuovo
login sono passati `/readyz` HTTP 200, ChatGPT `ping` e `resolve_status` sul Resolve reale.

Durante il deployment sono stati corretti due problemi Windows: alias Python `WindowsApps`
non eseguibile da Task Scheduler e BOM UTF-8 prodotto da Windows PowerShell 5.1.

Stato gate: **AUTOSTART + READ VALIDATED**. Restano prima del PASS completo della checklist:
- `create_safe_working_timeline` tramite runtime persistente;
- chiusura/riapertura Resolve senza reinstallazione;
- terminazione volontaria del tunnel e verifica restart/backoff;
- audit finale di config e log per assenza di segreti.

### Track A1 — prodotto ChatGPT / Resolve
1. `ARPHE_MCP_BRIDGE_CREATIVE_03` installato e raggiungibile dal PC segreteria.
2. Gate A PASS; master 16:9 creato in `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`.
3. Ripartire dal Gate B sul master `ARPHE_E09_16X9_V1`, abilitando solo `CAP_FUSION`.
4. Validare Gate B-G uno alla volta, aggiornando i flag solo dopo il gate precedente.
5. Mantenere `ARPHE_MCP_BRIDGE_SAFE_WRITE_02` come rollback immediato.
6. In parallelo continuare il percorso editoriale `list_media` / transcript / edit plan senza
   confonderlo con la validazione E09.

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
