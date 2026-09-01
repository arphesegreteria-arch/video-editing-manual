# 09 — MCP Tunnel Rollout Checklist

Data: 2026-09-01

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

## FASE 5 — Creare il profilo locale stdio

Il nostro MCP server locale usa stdio, quindi il percorso ufficiale più semplice è un profilo `sample_mcp_stdio_local`.

Concetto:

`tunnel-client init --sample sample_mcp_stdio_local --profile arphe-resolve --tunnel-id <TUNNEL_ID> --mcp-command "python C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_READ_01.py"`

Nota Windows:
- usare il percorso reale di `python.exe` se `python` non è nel PATH;
- quotare correttamente i path con spazi;
- non inserire la runtime key nel comando salvato nel repository.

Impostare la runtime key nella sessione/ambiente locale come `CONTROL_PLANE_API_KEY`.

## FASE 6 — Eseguire `doctor` PRIMA di ChatGPT

Comando concettuale:

`tunnel-client doctor --profile arphe-resolve --explain`

Non procedere se `doctor` segnala:
- runtime key assente;
- tunnel non autorizzato;
- MCP server non avviabile;
- problemi di readiness.

## FASE 7 — Avviare il tunnel in foreground

Per il primo test:

`tunnel-client run --profile arphe-resolve`

NON installare ancora servizi Windows, startup automatico o daemon nascosto.

Per sviluppo vogliamo vedere chiaramente log e stato.

Il processo deve restare aperto durante il test ChatGPT.

## FASE 8 — Verificare health e readiness locali

`tunnel-client` espone superfici locali di diagnostica:

- `/healthz`;
- `/readyz`;
- `/metrics`;
- `/ui`.

Ordine di controllo:

1. `/readyz` deve risultare pronto;
2. `/ui#overview` deve mostrare tunnel e MCP target corretti;
3. se qualcosa fallisce, guardare `/ui#logs` prima di modificare codice.

Non considerare il tunnel funzionante solo perché il processo è aperto.

## FASE 9 — Collegare ChatGPT

Con il tunnel ancora in esecuzione:

1. Aprire ChatGPT web.
2. Aprire Settings.
3. Entrare nella sezione Apps/Connectors prevista dal workspace.
4. Abilitare Developer Mode se richiesto e consentito dal workspace.
5. Creare/aggiungere la custom app ARPHE.
6. Scegliere `Connection: Tunnel`.
7. Selezionare `ARPHE-RESOLVE-HOME-DEV` oppure incollare il relativo `tunnel_id`.
8. Verificare che ChatGPT scopra le tool `ping` e `resolve_status`.

Se il tunnel non appare:
- controllare workspace scope del tunnel;
- controllare permesso Tunnels Read + Use;
- controllare che `tunnel-client` sia ancora running e `/readyz` sia OK;
- attendere circa 30 secondi se il tunnel è appena stato creato.

## GATE 3 — Test end-to-end READ

Preparazione:

1. Aprire Resolve Studio.
2. Aprire un progetto non sensibile di test.
3. Aprire una timeline.
4. Lasciare `External scripting using = Local`.
5. Lasciare `tunnel-client run --profile arphe-resolve` attivo.

Prompt di test in ChatGPT:

`Usa ARPHE Resolve e dimmi quale progetto e timeline sono aperti in Resolve. Non modificare nulla.`

Risultato PASS:

- ChatGPT chiama `resolve_status`;
- la risposta coincide con ciò che è realmente aperto in Resolve;
- nessuna modifica viene effettuata;
- log tunnel mostrano una tool call riuscita.

Solo a questo punto segnare:

`ChatGPT -> Secure MCP Tunnel -> MCP -> Resolve READ = SUPPORTED`

## FASE 10 — Programmare MCP WRITE v1

Solo dopo Gate 3.

Nuova tool:

`create_safe_working_timeline(name_prefix: str = "ARPHE_CHATGPT_TEST")`

Regole obbligatorie:

- non accetta codice arbitrario;
- non accetta un project path arbitrario;
- opera solo sul progetto corrente esplicitamente aperto;
- conserva un riferimento alla timeline originale;
- crea soltanto una timeline vuota con nome ARPHE;
- verifica l'incremento del timeline count;
- torna automaticamente alla timeline originale;
- restituisce un risultato strutturato;
- in caso di errore non prova operazioni distruttive di recovery.

Output previsto:

```json
{
  "ok": true,
  "original_timeline": "Timeline 1",
  "created_timeline": "ARPHE_CHATGPT_TEST_...",
  "returned_to_original": true
}
```

## GATE 4 — ChatGPT -> Resolve WRITE innocua

Prompt di test:

`Crea una nuova timeline vuota di test ARPHE e poi torna alla timeline originale. Non modificare nessuna clip.`

PASS solo se:

- compare una nuova timeline;
- nessuna clip dell'originale cambia;
- timeline attiva finale = originale;
- il risultato della tool coincide con la UI Resolve;
- eventuale conferma ChatGPT viene mostrata e approvata quando prevista.

## FASE 11 — Tool da aggiungere dopo il WRITE gate

Ordine di sviluppo consigliato:

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
- non automatizzare startup Windows finché il test end-to-end non è stabile;
- non provare subito cut reali sul progetto `blabla` come primo test MCP write.

## Checklist rapida quando si riprende la sessione

- [x] Resolve external READ
- [x] Resolve external SAFE WRITE
- [x] MCP locale READ
- [ ] verificare piano/workspace ChatGPT
- [ ] creare tunnel Platform
- [ ] creare runtime key Tunnels Read + Use
- [ ] installare `tunnel-client`
- [ ] creare profilo `arphe-resolve`
- [ ] `doctor --explain` PASS
- [ ] `run` + `/readyz` PASS
- [ ] collegare custom app ChatGPT
- [ ] ChatGPT chiama `resolve_status`
- [ ] programmare `create_safe_working_timeline`
- [ ] ChatGPT crea timeline vuota in Resolve
- [ ] aggiungere transcription/media tools
- [ ] eseguire E05 podcast excerpt benchmark

## Definition of Done — prima milestone

La milestone `CHATGPT_RESOLVE_BRIDGE_V1_READ` è completata quando da una normale conversazione ChatGPT possiamo leggere realmente lo stato del Resolve Studio locale attraverso Secure MCP Tunnel.

La milestone `CHATGPT_RESOLVE_BRIDGE_V1_WRITE` è completata quando da ChatGPT possiamo creare una nuova timeline vuota ARPHE e tornare all'originale senza modificare contenuto esistente.
