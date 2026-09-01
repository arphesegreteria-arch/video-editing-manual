# 08 — ChatGPT + MCP + Resolve Studio Architecture

## Stato

**TARGET ARCHITECTURE — fattibilità locale confermata; integrazione ChatGPT/tunnel end-to-end ancora da validare.**

Data verifica: 2026-09-01.

La direzione del prodotto è cambiata rispetto al precedente concetto di una GUI desktop ARPHE separata.

## Obiettivo prodotto

L'interfaccia principale per la segreteria deve essere **ChatGPT**.

L'operatore deve poter lavorare in linguaggio naturale, per esempio:

> Prendi questo estratto, trascrivilo, proponimi i tagli secondo le regole ARPHE, fammi approvare le decisioni e poi applicale in Resolve.

La segreteria non deve usare direttamente Python, JSON, un pannello tecnico MCP o una GUI ARPHE separata.

## Architettura target

```text
Segreteria
   |
   v
ChatGPT
   |
   | custom MCP app: ARPHE Resolve
   v
Secure MCP Tunnel
   |
   v
ARPHE MCP Bridge locale (Python)
   |
   +--> media broker / cartelle consentite
   +--> faster-whisper locale
   +--> transcript + word timestamps
   +--> audio / VAD / waveform
   +--> validatore edit plan
   |
   v
DaVinci Resolve Studio external scripting API
   |
   v
nuova timeline / render / risultato
```

**ChatGPT è il cervello editoriale e l'interfaccia conversazionale.**

**Il bridge locale è infrastruttura.** Non è il prodotto che la segreteria deve imparare a usare.

## Cosa MCP rende possibile

Una custom MCP app può esporre a ChatGPT strumenti controllati. Il server MCP decide quali operazioni esistono, quali parametri accettano e quali risultati restituiscono.

Esempi ARPHE:

### Read tools

- `resolve_status`
- `get_current_project`
- `get_current_timeline`
- `list_media`
- `get_transcript_metadata`
- `get_transcript_chunk`
- `get_edit_preview`

### Write tools

- `transcribe_media`
- `create_safe_working_timeline`
- `apply_edit_plan`
- `import_media`
- `apply_punch_in`
- `place_broll`
- `create_captions`
- `render_preview`

Le write tool devono essere poche, esplicite e validate. Non esporre mai un generico `run_python`, `run_shell` o accesso arbitrario al filesystem.

## Vincolo ChatGPT attuale

Al 2026-09-01 il supporto MCP completo in ChatGPT, incluse azioni di modifica/scrittura, è in beta per **ChatGPT Business, Enterprise ed Edu** sul web.

Gli utenti Pro possono collegare custom MCP in developer mode con permessi read/fetch, ma il full MCP con write non è attualmente disponibile sul piano Pro.

Questa è una dipendenza di prodotto importante: prima del test end-to-end con scrittura bisogna verificare il piano/workspace ChatGPT destinato ad ARPHE.

## Server locale e Secure MCP Tunnel

ChatGPT non si connette direttamente a un MCP server che ascolta solo su localhost o nella rete privata.

Per il nostro caso il percorso previsto è **Secure MCP Tunnel**:

- il bridge MCP resta sul PC ARPHE;
- `tunnel-client` apre connessioni HTTPS in uscita verso OpenAI;
- non è necessario esporre pubblicamente il server MCP;
- il tunnel può inoltrare verso un MCP locale via `stdio` oppure HTTP;
- ChatGPT collega la custom app al tunnel autorizzato.

Questo sostituisce il vecchio progetto di una GUI che interroga una coda GitHub.

## SDK MCP

Per il prototipo Python usare l'SDK MCP ufficiale v2.

Requisiti correnti:
- Python 3.10+;
- pacchetto `mcp[cli]`;
- server con tool tipizzati;
- MCP Inspector utile per il test locale, ma non necessario nel workflow finale.

## Sicurezza applicativa ARPHE

Principi obbligatori:

- allowlist di tool, non esecuzione arbitraria;
- cartelle locali esplicitamente consentite;
- validazione rigorosa dei path;
- nessuna timeline originale sovrascritta;
- ogni montaggio crea una nuova timeline;
- write operation distruttive solo dopo validazioni e, quando ChatGPT lo richiede, conferma utente;
- output strutturato e log locale per ogni operazione;
- contenuti sensibili/reputazionali: `FLAG ONLY`, non auto-cut;
- separare decisione editoriale da esecuzione deterministica.

## Costi / responsabilità del modello

Nell'architettura target non serve che `ARPHE MCP Bridge` chiami l'OpenAI API per fare il ragionamento editoriale.

Il ragionamento avviene nella conversazione ChatGPT; il bridge riceve una tool call strutturata e la esegue localmente.

Quindi:

```text
ChatGPT decide
    -> MCP tool call
        -> Python locale valida/esegue
            -> Resolve Studio opera
```

Un'integrazione separata via OpenAI API rimane un possibile fallback futuro, ma non è l'obiettivo primario.

## Workflow editoriale target — podcast excerpt

1. L'operatore mette/seleziona una `SOURCE_EXCERPT` autonoma.
2. L'estratto parte da `00:00`; nessun mapping col podcast originale durante il benchmark.
3. ChatGPT chiama `transcribe_media`.
4. faster-whisper genera localmente transcript + word timestamps.
5. ChatGPT legge il transcript e propone decisioni editoriali secondo il profilo ARPHE.
6. Segreteria e ChatGPT discutono/approvano i casi dubbi.
7. ChatGPT costruisce un edit plan strutturato.
8. Il bridge valida intervalli, speech repair e regole di sicurezza.
9. Audio/waveform decide il placement fisico dei bordi dove necessario.
10. ChatGPT chiama `apply_edit_plan`.
11. Resolve Studio crea una **nuova timeline**.
12. ChatGPT restituisce un riepilogo; la timeline viene revisionata.

## Gate di validazione

### Gate 0 — Workspace ChatGPT — NEXT
Verificare che il workspace usato per il test disponga di developer mode e delle autorizzazioni MCP necessarie. Per le write action serve full MCP.

### Gate 1 — Resolve external WRITE — PASSED
`ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02` ha creato una timeline vuota, incrementato il timeline count e riportato Resolve su `Timeline 1` con exit code 0.

Primitive confermate:
- `MediaPool.CreateEmptyTimeline()`;
- `Project.SetCurrentTimeline()`.

### Gate 2 — MCP locale READ — PASSED
`ARPHE_MCP_BRIDGE_READ_01` ha negoziato il protocollo MCP, esposto `ping` e `resolve_status` e letto correttamente progetto/timeline/FPS/track/item di Resolve senza modifiche.

### Gate 3 — Secure MCP Tunnel READ — NEXT
Collegare il server locale a ChatGPT tramite Secure MCP Tunnel e chiedere in una normale chat lo stato reale di Resolve.

### Gate 4 — ChatGPT -> MCP -> Resolve WRITE innocua
Esporre `create_safe_working_timeline`, chiedere a ChatGPT di creare una timeline vuota di test e verificare manualmente il risultato.

### Gate 5 — Transcription tool
Esporre `list_media` + `transcribe_media` sulla cartella di test e ottenere il transcript direttamente dalla conversazione.

### Gate 6 — Edit plan
Applicare un edit plan minimo a un clip di test, sempre creando una timeline separata.

Solo dopo Gate 4 si può dire che **ChatGPT controlla realmente Resolve Studio in scrittura**.

## Prossima procedura operativa

Usare `docs/09_MCP_TUNNEL_ROLLOUT_CHECKLIST.md` come guida click-by-click per:
- workspace/piano;
- tunnel Platform;
- runtime key;
- `tunnel-client`;
- readiness;
- custom app ChatGPT;
- READ gate;
- primo WRITE gate.

## Fonti tecniche esterne

Da considerare riferimenti correnti, ma da validare nel nostro ambiente:

- OpenAI Help — Developer mode and MCP apps in ChatGPT.
- OpenAI Secure MCP Tunnel / `openai/tunnel-client`.
- Model Context Protocol Python SDK v2.

Le osservazioni sull'API Resolve restano subordinate ai test eseguiti sulla nostra installazione di Resolve Studio.
