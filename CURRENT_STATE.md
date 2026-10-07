# CURRENT STATE

Ultimo aggiornamento: sessione 2026-10-08.

## Ritiro Resolve archive-first — CODICE VALIDATO / ROLLOUT PENDING

Timeline e progetti ARPHÈ possono essere ritirati soltanto dopo salvataggio, export `.drp`
verificato, fingerprint e approvazione tecnica esplicita. L'esecuzione ricontrolla hash,
last-modified, render lock e target esatto; il recovery importa un progetto `ARPHE_RECOVERY_...`
senza overwrite. Retention archivi: tutti per 30 giorni e comunque gli ultimi 3 per progetto;
nessun archivio viene eliminato automaticamente.

Validazione automatica: Creative `165 PASS / 1 SKIP` ambientale; Windows `48 PASS / 1 SKIP`
DPAPI ambientale. `PC_PERSONALE`: installazione, catalogo, runtime ready e inspection read-only
PASS; gate ancora spento. Il progetto disposable `ARPHE_RETIREMENT_PROBE_20261008_0053` è pronto
con due timeline e il progetto precedente è stato ricaricato. Prova distruttiva: `PENDING`
approvazione esplicita.
`PC_SEGRETERIA`: **NON TOCCATO**. Procedura: `docs/20_RESOLVE_RETIREMENT_AND_RECOVERY.md`.

## Igiene artefatti — CODICE VALIDATO / ROLLOUT PERSONALE IN OSSERVAZIONE

Il bridge registra catture diagnostiche, staging render e log ruotati; applica retention fissa,
quarantena recuperabile di sette giorni e purge soltanto su artefatti tecnici conosciuti. File
sconosciuti, sorgenti, master, pubblicabili e oggetti Resolve non vengono rimossi. Il vecchio
cleanup generico di progetti/timeline/path non è più esposto.

Validazione automatica complessiva aggiornata: Creative `165 PASS / 1 SKIP` ambientale symlink;
Windows `48 PASS / 1 SKIP` DPAPI ambientale. Sul `PC_PERSONALE` installazione, riavvio, readiness,
inventario e manutenzione a vuoto sono PASS. I 68 elementi storici (`37.092.166` byte) restano
`UNCLASSIFIED` e intatti. La sonda registrata `290944e3-f62f-4a44-bc93-fa1bc43e756e` è
correttamente `ACTIVE` fino al 2026-10-08 22:43:07 UTC; quarantena/restore e purge restano
`PENDING` fino alle rispettive scadenze reali. `PC_SEGRETERIA`: **NON TOCCATO**, gate separato
`PENDING`.

Procedura: `docs/19_ARTIFACT_HYGIENE_AND_QUARANTINE.md`.

## Workflow editoriali e render batch — CODICE VALIDATO / ROLLOUT PENDING

Quattro linee editoriali esplicite sostituiscono i default impliciti. Il bridge imposta e legge
project/timeline/playback FPS, prepara job isolati, richiede approvazione, avvia solo gli ID del
batch, verifica i media in staging e promuove soltanto output conformi. I vecchi entry point MCP
di avvio immediato restituiscono ora una risposta di migrazione.

Validazione automatica finale: Creative `112/112` PASS; Windows `35` PASS e `1` SKIP DPAPI noto. Le prove live
`PC_PERSONALE` e `PC_SEGRETERIA` sono `PENDING` e separate. Nessun Resolve, task o tunnel è stato
modificato; il lavoro attualmente aperto sul PC segreteria non è stato toccato.

Procedura: `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`.

## Isolamento workstation — CODICE MIGRATO / ROLLOUT PENDING

La repository usa ora profili espliciti per separare config runtime e Creative, stato, audit,
Python, tunnel, log e backup di `PC_PERSONALE` e `PC_SEGRETERIA`. Il codice condiviso resta su
un'unica linea; i dati operativi non vengono condivisi tra le macchine.

Validazione automatica del 2026-10-07 dopo integrazione di `origin/main`: Creative `67/67` PASS;
Windows `35` PASS e `1` SKIP DPAPI
per indisponibilità del profilo CurrentUser nel token di test. Nessun task, tunnel, segreto o
Resolve reale è stato modificato durante questa migrazione. Preflight, installazione, READ e SAFE
WRITE restano `PENDING` separatamente su ciascun PC.

## Shortform caption mobile — PARTIAL / render verificato

Sul `PC_PERSONALE` è stato completato un probe reale sulla timeline verticale
`ARPHE_SHORTFORM_MASTER_V4`: creazione subtitle nativa, conversione logica in un unico layer
Fusion con 12 Text+ temporizzati, stile Satoshi Bold bianco su bordeaux, size 0.050, fascia bassa
68–82% con centro al 76%, render 1080×1920/30 e controllo visivo di caption, volti, frasi lunghe
e gap.

Risultati principali:
- `CreateSubtitlesFromAudio` funziona dopo `resolve.OpenPage("edit")`;
- la API pubblica osservata non offre lo styling nativo necessario;
- `SetName` sul caption item non corregge il testo;
- Background alpha zero + espressione sul Blend dei Merge produce overlay trasparente e timing
  corretto;
- la regola di posizionamento vieta qualsiasi sovrapposizione al volto e conserva almeno il 15%
  inferiore per l'interfaccia social;
- render/export da Python esterno è stato completato e verificato.

Stato: `PARTIAL`, non ancora primitiva MCP validata. Dettagli e gate:
`docs/16_CAPTION_ENGINE_AND_MOBILE_SUBTITLES.md`.

## Avviso operativo - isolamento workstation

Il 2026-09-21 il runtime del PC personale e quello del PC segreteria sono risultati collegati allo
stesso tunnel legacy `ARPHE-RESOLVE-HOME`. Un test remoto parallelo ha prodotto risultati
incoerenti e il log personale ha ricevuto solo una delle due richieste. Il bridge personale e
Resolve funzionano localmente; la causa più probabile è il prelievo delle richieste da due client
differenti sullo stesso tunnel.

La separazione del tunnel personale è stata completata successivamente. Per la migrazione profili
del 2026-10-07 resta però valida una regola analoga: non eseguire write remote finché la singola
workstation non ha superato il proprio preflight, rollout e gate READ. Vedere
`docs/15_MULTI_WORKSTATION_ISOLATION_AND_2026-09-21_INCIDENT.md`.

## E09 — standard recensioni Instagram validato

La prova verticale `ARPHE_E09_REELS_MIODOTTORE_V3` è stata creata e verificata sul PC segreteria:
1080×1920/30, canvas beige, card cream, Satoshi, intro editoriale, cinque recensioni originali,
CTA burgundy e durata 810 frame / 27 secondi. Le capacità Review, Fusion e Motion sono state
usate end-to-end. Il procedimento riusabile è `docs/16_INSTAGRAM_REVIEW_REEL_STANDARD.md`; il
piano senza contenuti reali è `plans/ARPHE_INSTAGRAM_REVIEW_REEL_TEMPLATE.json`. Il MOV esportato
manualmente è risultato troppo compresso (~2,5 Mb/s); anche i test MP4 controllati V4/V6 hanno
prodotto solo ~0,8 Mb/s e non sono consegne valide. Il master V7 QuickTime ProRes 422 HQ è stato
renderizzato sul Desktop e verificato: 1080×1920/30, 27 secondi, ~30,5 Mb/s (104 MB). Questo è il
nuovo riferimento di qualità prima della consegna Instagram. La copia compatibile V8 MP4/H.264
è stata ricavata dal master, non dal preset H.264 di Resolve, e confrontata frame-per-frame con
V7: SSIM 0,9979 e PSNR 57,6 dB.

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

### PC_PERSONALE — TUNNEL DEDICATO / NUOVO PROFILO PENDING

Il PC personale ha ora Resolve Studio `21.0.4.5`, Python `3.12.10`, runtime automatico `ready` e
collegamento locale read-only a Resolve verificato sul progetto `New Project 4`.

Il tunnel dedicato `ARPHE-RESOLVE-PERSONALE` e la relativa app sono stati configurati e il `ping`
remoto ha restituito `workstation_id: PC_PERSONALE`. La nuova migrazione di profilo del
2026-10-07 non è però ancora stata applicata né rivalidata su questa macchina; READ e SAFE WRITE
vanno ripetuti dopo il rollout.

Il codice è ora portabile: runtime e Creative Bridge accettano l'identità `PC_PERSONALE`, esiste
un installer coordinato e la procedura completa è in `docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md`.
Restano necessariamente locali la creazione del tunnel, la chiave Restricted e la registrazione
della app nel workspace ChatGPT Business.

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
- Fusion create/read/write oltre le primitive Creative 03 validate e il probe caption singolo;
- tracking Studio / IntelliTrack;
- captions/subtitles tramite tool MCP parametrica e ripetibile;
- render/export tramite Creative 03/MCP (il percorso Python esterno diretto è invece SUPPORTED).

Un'operazione non diventa `SUPPORTED` solo perché esiste nella documentazione API: deve essere testata nel nostro ambiente.

### ARPHE_MCP_BRIDGE_CREATIVE_03 — GATE A/B PASS / GATE C STATIC PASS / GATE D PASS

Build modulare aggiunta per E09 MioDottore Review Social Creative. Mantiene `ping`,
`resolve_status` e `create_safe_working_timeline`, aggiunge primitive semantiche per
project/timeline, Fusion, review card, motion, asset e preview, senza tool generiche o delete.

Default release:
- `CAP_PROJECT=true`, `CAP_TIMELINE=true` per Gate A;
- `CAP_FUSION=false`, `CAP_REVIEW=false`, `CAP_MOTION=false`, `CAP_ASSETS=false`,
  `CAP_RENDER=false` fino ai gate reali;
- Gate A `create_project` / `create_timeline` / `get_creative_status`: `SUPPORTED` con evidenza
  reale; le capability parziali sono ora dichiarate `PARTIAL`, senza confonderle con `SUPPORTED`.

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
resta conservata come evidenza Gate A.

Gate B è `SUPPORTED`: composizione, canvas e Text+ sono stati ripetuti con grafo pulito nel V5.
Gate C V2-V4 non è
un PASS grafico: ha rivelato connessioni da verificare, proxy `SetInput` che restituisce `None`
anche quando applica la modifica, e soprattutto l'uso errato di `Width`/`Height` al posto di
`LayoutWidth`/`LayoutHeight` per il frame Text+. Il bridge ora usa gli input osservati dal vivo,
fa read-back e rimuove i nodi creati dalla chiamata se la primitive fallisce.
Gate C V5 ha superato API/read-back e verifica visiva: testo contenuto, cinque stelle, label,
card, bordi e shadow corretti. La review card statica è PASS; highlight/end card restano PENDING,
quindi `CAP_REVIEW` complessiva è `PARTIAL`. Il layout è ancora un prototipo da affinare.

Gate D ha superato il test reale sulla timeline separata `ARPHE_E09_16X9_GATE_D_V1`:
composition `ARPHE_COMP_BCB45B060D`, card `ARPHE_CARD_48A11B058C`, preset
`ARPHE_SOFT_DROP`, keyframe `0`, `15`, `18` e grafo Fusion di 19 nodi. Tutti gli stati dal
frame `0` al frame `18` sono stati acquisiti e mostrati in ordine come 19 immagini, in batch
`8 + 8 + 3`, con ripristino del playhead. Tutte le chiamate hanno restituito `ok:true`.
`CAP_MOTION` è attiva nella configurazione locale del test e diventa `PARTIAL`: ingresso card
SUPPORTED, stack multi-card Gate E ancora PENDING.

Il content-use check è chiuso per il workflow E09: si usano recensioni reali selezionate e già
approvate da ARPHE, senza nomi dei pazienti. I testi arrivano esclusivamente come input runtime e
non vengono hardcoded, salvati nei log o versionati nella repository pubblica. La pubblicazione
resta un passaggio umano esplicito: il bridge non pubblica autonomamente.

Il server installato e l'app ChatGPT Creative 03 pubblicata espongono ora 28 azioni MCP, incluse
`inspect_fusion_graph` e `capture_timeline_frames`. Lo snapshot è stato aggiornato in-place senza
creare una nuova app. Le annotazioni MCP dichiarano letture read-only, tutte le azioni closed-world
e non distruttive, scritture e idempotenza separate. La risposta di `capture_timeline_frames` usa
contenuti MCP nativi invece di serializzare gli helper `Image`: dalla chat sono stati acquisiti e
mostrati correttamente i frame `0`, `75` e `149`, con ripristino del playhead.

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

Il 2026-09-08 Smart App Control ha bloccato il client tunnel non firmato (Code Integrity,
WinError 4551). È stato disabilitato sul PC segreteria e il runtime è tornato HTTP 200 ready.
Questa è una mitigazione globale e resta debito di sicurezza: preferire in seguito un binario
firmato/approvato con versione e hash controllati.

Stato gate: **AUTOSTART + READ VALIDATED**. Restano prima del PASS completo della checklist:
- `create_safe_working_timeline` tramite runtime persistente;
- chiusura/riapertura Resolve senza reinstallazione;
- terminazione volontaria del tunnel e verifica restart/backoff;
- audit finale di config e log per assenza di segreti.

### Track A1 — prodotto ChatGPT / Resolve
1. `ARPHE_MCP_BRIDGE_CREATIVE_03` installato e raggiungibile dal PC segreteria.
2. Gate A PASS; master 16:9 creato in `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`.
3. Gate B e review card statica Gate C V5 PASS; highlight/end card restano PENDING.
4. Snapshot ChatGPT a 28 azioni; diagnostica grafo e frame MCP validata end-to-end.
5. Gate D `ARPHE_SOFT_DROP` PASS sulla timeline separata `ARPHE_E09_16X9_GATE_D_V1`, con
   19 nodi Fusion e acquisizione completa dei frame `0`-`18`.
6. Svolgere Gate E su una nuova timeline, usando cinque recensioni reali approvate e
   anonimizzate come input esclusivamente runtime.
7. Mantenere `ARPHE_MCP_BRIDGE_SAFE_WRITE_02` come rollback immediato.
8. In parallelo continuare il percorso editoriale `list_media` / transcript / edit plan senza
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
1. Transcript completo locale di `Angolo delle recensioni (degli altri) ep 2.mp4`: **COMPLETATO**
   (`ARPHE_TRANSCRIPT_V1`, 1375 segmenti, 7278 parole, 3091,876 s).
2. Generare un indice temporale compatto e selezionare un estratto autonomo di circa 8–15 minuti.
3. Trattare l'estratto da `00:00` come unica sorgente canonica.
4. Congelare il candidate automatico prima del montaggio umano.
5. Montare manualmente lo stesso estratto.
6. Esportare reference e confrontare.
7. Classificare mismatch e aggiornare le regole solo dopo il report.

Il transcript resta in `%LOCALAPPDATA%\ARPHE\Longform04\transcripts` ed è escluso da Git. Il bridge
longform dovrà esporre trascrizione asincrona, stato e lettura a chunk per evitare timeout e carichi
di contesto inutili.

Stato implementazione 2026-09-15: lettura media/transcript, validazione e applicazione del piano
sono implementate dietro `CAP_LONGFORM`; il job di trascrizione asincrono resta il passo successivo.
La build è installata su `PC_SEGRETERIA`, `CAP_LONGFORM` è attiva, runtime e tunnel sono HTTP 200 e
l'app ChatGPT è aggiornata a 35 azioni. Il piano unico di 11 estratti è approvato e validato
(33180 frame, 18:26 totali, massimo 2:57). Nessuna write Resolve è ancora stata eseguita.

Prossimo gate: in un nuovo contesto che carichi il catalogo a 35 azioni, validare nuovamente il
piano e applicarlo creando soltanto progetto `ARPHE_ANGOLO_RECENSIONI_EP2_CUTS`, master
`ARPHE_EP2_PUBLISHABLE_MASTER_V1` e 11 timeline individuali. In seguito rifinire i confini con
controllo parola/audio/frame prima di dichiarare definitivi i tagli.

Il piano approvato completo è versionato in `plans/ARPHE_EP2_PUBLISHABLE_V1.json`; non deve essere
ricostruito dalla memoria della chat. Lo stato `APPROVED_ROUGH_BOUNDARIES` indica che contenuti e
finestre sono approvati, mentre i punti di lama finali richiedono ancora il gate audiovisivo.

## Direzione scartata

La vecchia GUI desktop ARPHE + polling GitHub (`ARPHE Remote Agent V1`) è **SUPERSEDED**. ChatGPT è la UI primaria; il componente locale deve restare un bridge MCP/Resolve.

Dettagli persistenti:
- `EXPERIMENT_LOG.md`;
- `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`;
- `docs/09_MCP_TUNNEL_ROLLOUT_CHECKLIST.md`;
- `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`;
- `docs/RESOLVE_STUDIO_CAPABILITIES.md`;
- `docs/07_EDITORIAL_BENCHMARK.md`.
