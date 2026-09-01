# 09 — MCP Tunnel Rollout Checklist

Data: 2026-09-01

## STATUS POST-ROLLOUT

**COMPLETATO sul `PC_SEGRETERIA` fino al Gate 4 incluso.**

Sono ora VALIDATED end-to-end:
- ChatGPT -> Secure MCP Tunnel -> Resolve READ;
- ChatGPT -> Secure MCP Tunnel -> Resolve SAFE WRITE con `create_safe_working_timeline`.

Le fasi sotto restano come documentazione riproducibile del rollout manuale. La vecchia regola “non automatizzare startup Windows finché l'end-to-end non è stabile” è ora soddisfatta e quindi superata.

**Prossimo documento operativo:** `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`.

Nota workstation: i test descritti in questo documento sono stati eseguiti sul **PC segreteria**, non sul PC personale.

## Obiettivo

Arrivare dal prototipo locale già validato a questo percorso reale:

`ChatGPT -> Secure MCP Tunnel -> ARPHE MCP Bridge locale -> DaVinci Resolve Studio`

La segreteria usa ChatGPT. Il bridge e il tunnel sono infrastruttura tecnica e non una seconda interfaccia operativa.

## Stato di partenza già VALIDATO

Su Resolve Studio `21.0.4.5` abbiamo già provato con successo:

- Python esterno -> Resolve READ;
- Python esterno -> Resolve SAFE WRITE;
- creazione timeline vuota tramite `MediaPool.CreateEmptyTimeline()`;
- ritorno automatico alla timeline originale tramite `Project.SetCurrentTimeline()`;
- MCP locale con tool `ping` e `resolve_status`;
- MCP locale -> bridge Python -> Resolve READ.

Quindi NON dobbiamo più ridimostrare questi passaggi prima di configurare il tunnel.

## Tempo realistico del prossimo blocco

Se account, permessi e tunnel sono disponibili senza problemi:

- verifica piano/workspace e Developer Mode: 5-10 minuti;
- creazione tunnel + runtime key: 10-20 minuti;
- installazione/configurazione `tunnel-client`: 10-20 minuti;
- health/ready check locale: 5-10 minuti;
- collegamento custom app in ChatGPT + primo `resolve_status`: 10-20 minuti.

Prima milestone end-to-end READ: indicativamente **40-80 minuti**.

Se mancano permessi Business/Enterprise/Edu, ruoli Tunnels o il tunnel non compare nel workspace ChatGPT, il tempo dipende dall'amministrazione dell'account e non dal codice ARPHE.

## FASE 0 — Verificare il piano ChatGPT

### Obiettivo

Capire subito fino a dove possiamo arrivare.

### Regola corrente OpenAI

- Full MCP con write/modify: beta per ChatGPT Business, Enterprise ed Edu sul web.
- Pro: custom MCP in developer mode con read/fetch, ma non full write al momento.

### Risultato atteso

Annotare:

`CHATGPT_WORKSPACE_PLAN = Business | Enterprise | Edu | Pro | altro`

Se Business/Enterprise/Edu:
- puntare a READ e poi WRITE.

Se Pro:
- validare comunque `ChatGPT -> MCP -> Resolve READ`;
- tenere WRITE come gate bloccato dal piano finché il supporto non cambia.

## FASE 1 — Sistemare il bridge in una cartella stabile

Non usare Downloads come posizione definitiva.

Creare per esempio:

`C:\ARPHE\MCP\`

Dentro mantenere almeno:

- `ARPHE_MCP_BRIDGE_READ_01.py`;
- eventuale virtual environment/config in una fase successiva;
- log locali;
- nessuna API key hard-coded.

La copia nei Downloads può essere eliminata una volta che il bridge è nella posizione stabile o ricostruibile dalla repository.

## FASE 2 — Creare Secure MCP Tunnel da OpenAI Platform

Percorso consigliato: usare la UI Platform, non l'admin CLI, per il primo test.

Aprire la pagina Tunnels dell'organizzazione OpenAI e creare un tunnel dedicato, nome consigliato:

`ARPHE-RESOLVE-HOME-DEV`

Il tunnel deve essere associato al workspace ChatGPT che userà l'app.

Salvare il valore:

`CONTROL_PLANE_TUNNEL_ID = tunnel_...`

### Importante

`tunnel_id` e runtime API key sono due valori diversi.

Non mettere nessuno dei due nella repository.

## FASE 3 — Creare una Runtime API Key minima

Creare una **Runtime API key Restricted** per il daemon `tunnel-client`.

Permessi minimi richiesti dal percorso corrente:

- Tunnels Read;
- Tunnels Use.

Nome consigliato:

`ARPHE Resolve Tunnel Runtime`

Salvare temporaneamente la chiave in modo sicuro.

NON:
- committarla;
- scriverla in README;
- inserirla nel bridge Python;
- usare una Admin key per il daemon permanente.

## FASE 4 — Installare `tunnel-client`

Scaricare una build supportata dalla pagina Tunnels di OpenAI Platform oppure dall'ultima release pubblica ufficiale `openai/tunnel-client`.

Prima di creare configurazioni manuali, verificare il binario:

`tunnel-client help quickstart`

`tunnel-client help doctor`

`tunnel-client help plugin`

Se questi comandi non funzionano, fermarsi qui e correggere l'installazione.

Nota del test reale: sul PC segreteria è stata usata la build `tunnel-client-runtime-cloudflared`; questa variante non espone `/ui`, ma supporta health/readiness e il runtime MCP necessario.

## FASE 5 — Creare il profilo locale stdio

Il nostro MCP server locale usa stdio, quindi il percorso ufficiale più semplice è un profilo `sample_mcp_stdio_local`.

Concetto:

`tunnel-client init --sample sample_mcp_stdio_local --profile arphe-resolve --tunnel-id <TUNNEL_ID> --mcp-command "python C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_READ_01.py"`

Nota Windows:
- usare il percorso reale di `python.exe` se `python` non è nel PATH;
- quotare correttamente i path con spazi;
- non inserire la runtime key nel comando salvato nel repository.

Nel test con `runtime-cloudflared` sono state usate direttamente le variabili:
- `CONTROL_PLANE_API_KEY`;
- `CONTROL_PLANE_TUNNEL_ID`;
- `MCP_COMMAND`.

Per `MCP_COMMAND` su Windows si è dimostrato robusto usare `/` nei path, ad esempio:

`py -3 C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_READ_01/ARPHE_MCP_BRIDGE_READ_01.py`

## FASE 6 — Eseguire diagnostica PRIMA di ChatGPT

Con il full client usare `doctor --explain` quando disponibile.

Con la variante runtime usata nel test, il gate pratico verificato è stato:
- processo avviato senza `can't open file`;
- poller control-plane avviato;
- `GET http://127.0.0.1:8080/readyz` -> HTTP 200 `ready`.

## FASE 7 — Avviare il tunnel in foreground — STORICO

Per il primo test è stato corretto tenere il runtime in foreground per vedere log e stato.

Questa fase è ora **VALIDATED e non è più il target operativo finale**.

Il prossimo step è automatizzare l'avvio nella sessione utente come definito in `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`.

## FASE 8 — Verificare health e readiness locali

La superficie validata nel runtime usato è:

- `/healthz`;
- `/readyz`;
- `/metrics` dove disponibile.

La variante `runtime-cloudflared` usata sul PC segreteria non espone `/ui`.

Gate reale usato:

1. `/readyz` deve restituire HTTP 200;
2. body `ready`;
3. i log non devono mostrare uscita immediata del comando MCP.

## FASE 9 — Collegare ChatGPT

Con il tunnel ancora in esecuzione:

1. Aprire ChatGPT web.
2. Aprire Workspace Settings -> Apps.
3. Creare una custom app.
4. Scegliere `Connection: Tunnel`.
5. Selezionare il tunnel della workstation.
6. Authentication: `None` per il bridge attuale.
7. Confermare l'avviso di rischio custom MCP.
8. Creare la draft DEV.
9. Dalla chat connettere la app.

Risultato reale PC segreteria:
- app DEV `ARPHE Resolve` creata;
- tool READ `ping`, `resolve_status` disponibili;
- app DEV `ARPHE Resolve WRITE Test` creata per il gate SAFE WRITE.

## GATE 3 — Test end-to-end READ — PASS

Prompt di test:

`Usa ARPHE Resolve e dimmi quale progetto e timeline sono aperti in Resolve. Non modificare nulla.`

Risultato osservato:
- `resolve_status` chiamata realmente dalla conversazione;
- Resolve `21.0.4.5`;
- progetto `blabla`;
- timeline `Timeline 1`;
- 30 fps;
- 1 video track, 1 audio track;
- 130 clip V1, 130 clip A1.

Stato:

`ChatGPT -> Secure MCP Tunnel -> MCP -> Resolve READ = SUPPORTED`

## FASE 10 — MCP WRITE v1 — PASS

Tool:

`create_safe_working_timeline(name_prefix: str = "ARPHE_CHATGPT_TEST")`

Regole implementate:
- non accetta codice arbitrario;
- opera sul progetto corrente;
- conserva la timeline originale;
- crea soltanto una timeline vuota con nome ARPHE;
- verifica incremento timeline count;
- torna automaticamente alla timeline originale;
- restituisce risultato strutturato;
- non modifica clip e non cancella timeline.

## GATE 4 — ChatGPT -> Resolve WRITE innocua — PASS

Prompt:

`Crea una nuova timeline vuota di test ARPHE e poi torna alla timeline originale. Non modificare nessuna clip.`

Risultato osservato:
- timeline count `3 -> 4`;
- creata `ARPHE_CHATGPT_WRITE_TEST_20260901_185749`;
- timeline finale `Timeline 1`;
- clip edit `0`;
- timeline delete `0`;
- `ok=true`.

Stato:

`ChatGPT -> Secure MCP Tunnel -> MCP -> Resolve SAFE WRITE = SUPPORTED` per la primitiva testata.

## FASE 11 — Tool da aggiungere dopo il WRITE gate

Ordine di sviluppo consigliato, **dopo il runtime Windows persistente**:

1. `list_media`
2. `transcribe_media`
3. `get_transcript_chunk`
4. `create_safe_working_timeline`
5. `apply_edit_plan`
6. `get_edit_report`
7. `render_preview`

NON implementare insieme 15 tool prima di averne validate 3-4 end-to-end.

## FASE 12 — Primo workflow editoriale vero

Input:

`E05_SOURCE_EXCERPT.mp4` autonomo da 8-15 minuti, timeline/timecode da 00:00.

Flusso:

1. ChatGPT seleziona/individua l'excerpt consentito.
2. `transcribe_media` -> faster-whisper locale.
3. ChatGPT legge transcript e applica ARPHE Editorial Profile.
4. Contenuto sensibile = FLAG ONLY.
5. Segreteria approva/modifica decisioni.
6. ChatGPT produce edit plan strutturato.
7. Bridge valida il piano.
8. Waveform/refinement locale posiziona i bordi.
9. `apply_edit_plan` crea una nuova timeline.
10. Revisione umana.
11. Export reference umano.
12. Benchmark candidate vs reference.

## Cosa NON fare ora

- non costruire una GUI separata;
- non costruire una coda GitHub;
- non rendere il bridge un remote shell;
- non esporre tool `run_python`, `run_command`, `delete_file` generiche;
- non mettere chiavi nella repo;
- non provare cut reali sul progetto `blabla` senza un gate dedicato;
- non usare un unico tunnel/key indistinto per PC segreteria e PC personale.

La precedente regola “non automatizzare startup Windows finché il test end-to-end non è stabile” è **SUPERATA**, perché READ e SAFE WRITE sono ora end-to-end VALIDATED.

## Checklist rapida — stato attuale PC_SEGRETERIA

- [x] Resolve external READ
- [x] Resolve external SAFE WRITE
- [x] MCP locale READ
- [x] workspace ChatGPT Business verificato
- [x] tunnel Platform creato
- [x] runtime key Tunnels Read + Use creata
- [x] `tunnel-client-runtime-cloudflared` installato
- [x] MCP stdio collegato via `MCP_COMMAND`
- [x] `/readyz` PASS
- [x] custom app ChatGPT DEV creata
- [x] ChatGPT chiama `resolve_status`
- [x] `create_safe_working_timeline` implementata
- [x] ChatGPT crea timeline vuota in Resolve
- [ ] runtime Windows automatico senza PowerShell manuale — NEXT
- [ ] replica `PC_PERSONALE`
- [ ] aggiungere transcription/media tools
- [ ] eseguire E05 podcast excerpt benchmark

## Definition of Done — milestone tunnel

`CHATGPT_RESOLVE_BRIDGE_V1_READ` = COMPLETED.

`CHATGPT_RESOLVE_BRIDGE_V1_WRITE` = COMPLETED per SAFE WRITE testata.

Il nuovo milestone infrastrutturale è `ARPHE_WINDOWS_BRIDGE_RUNTIME_V1`, definito in `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`.
