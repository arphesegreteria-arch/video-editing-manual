# 10 — Windows Bridge Autostart + Workstation Deployment

Data: 2026-09-01

## Decisione

Dopo la validazione end-to-end READ e SAFE WRITE, il prossimo blocco infrastrutturale è rendere il bridge ARPHE persistente sul PC senza richiedere una PowerShell aperta manualmente.

ChatGPT resta l'interfaccia utente. Il componente Windows è infrastruttura tecnica e NON deve diventare una seconda applicazione di montaggio.

## Workstation: stato ufficiale

### PC_SEGRETERIA — CURRENT / VALIDATED

Tutti i test end-to-end del 2026-09-01 sono stati eseguiti sul **PC della segreteria**, non sul PC personale.

Su questa workstation sono stati validati:
- DaVinci Resolve Studio `21.0.4.5`;
- External scripting = Local;
- Python esterno -> Resolve READ;
- Python esterno -> Resolve SAFE WRITE;
- MCP locale -> Resolve READ;
- Secure MCP Tunnel runtime;
- `/readyz` HTTP 200;
- ChatGPT -> MCP -> Resolve READ;
- ChatGPT -> MCP -> Resolve SAFE WRITE con `create_safe_working_timeline`.

Root locale corrente:

`C:\ARPHE\MCP\`

Il tunnel usato durante il test è stato chiamato `ARPHE-RESOLVE-HOME`. Il nome è fuorviante perché il runtime è in realtà sul PC segreteria. Quando possibile, rinominarlo in `ARPHE-RESOLVE-SEGRETERIA`; se il rename non è pratico, mantenere il nome legacy ma documentare esplicitamente il mapping.

### PC_PERSONALE — PENDING REPLICA

Il PC personale deve ricevere una installazione separata dello stesso stack, ma NON deve condividere alla cieca segreti o identità runtime con il PC segreteria.

Obiettivo:

`ChatGPT -> app/tunnel PC_PERSONALE -> bridge locale personale -> Resolve Studio personale`

Stato: **NON ANCORA CONFIGURATO / NON ANCORA VALIDATO**.

## Regola multi-workstation

Per evitare routing ambiguo e per poter revocare una singola macchina:

- un tunnel per workstation;
- una runtime API key per workstation;
- configurazione locale per workstation;
- nessuna API key nella repository;
- nessuna copia della runtime key del PC segreteria sul PC personale;
- i file di codice/config non segreti invece devono essere condivisi tramite repository.

Naming consigliato:

- `ARPHE-RESOLVE-SEGRETERIA`;
- `ARPHE-RESOLVE-PERSONALE`.

Per la fase di sviluppo è preferibile avere anche app ChatGPT distinte o chiaramente nominate, ad esempio:

- `ARPHE Resolve Segreteria`;
- `ARPHE Resolve Personale`.

In futuro si potrà valutare un routing più trasparente, ma non prima di avere entrambe le workstation validate separatamente.

## Obiettivo immediato: ARPHE Resolve Bridge Runtime v1

Non costruire una GUI di montaggio.

Costruire un runtime Windows che:

1. parte automaticamente al login dell'utente Windows;
2. gira nella sessione utente, senza finestra PowerShell permanente;
3. recupera la runtime API key da storage sicuro Windows;
4. imposta `CONTROL_PLANE_API_KEY` solo nel processo figlio;
5. imposta il tunnel ID della workstation;
6. imposta `MCP_COMMAND` verso il bridge ARPHE validato;
7. avvia `tunnel-client-runtime-cloudflared.exe run`;
8. controlla `http://127.0.0.1:8080/readyz`;
9. scrive log locali redatti, mai segreti;
10. riavvia il runtime se termina inaspettatamente;
11. usa backoff per evitare loop di restart aggressivi;
12. consente stop/restart amministrativo semplice;
13. non modifica Resolve autonomamente: le write restano solo tool MCP allowlisted chiamate da ChatGPT.

## Perché v1 NON deve essere un Windows Service puro

DaVinci Resolve gira nella sessione desktop dell'utente. Un Windows Service classico gira normalmente in Session 0 e può introdurre problemi di accesso a processi/IPC della sessione interattiva.

Per v1 preferire:

**Windows Task Scheduler -> trigger `At logon` -> processo background nella sessione utente.**

Solo dopo aver verificato che il bridge è stabile in questa modalità valutare un servizio Windows vero e proprio.

## Gestione segreti

La runtime API key non deve essere:
- hard-coded in Python;
- salvata in `.bat`;
- salvata in JSON in chiaro;
- committata;
- stampata nei log.

Per v1 usare uno storage Windows per-user, preferibilmente:
- Windows Credential Manager, oppure
- DPAPI (`CryptProtectData`) con blob locale legato all'utente Windows.

Il tunnel ID NON è trattato come segreto e può stare nella configurazione locale, ma resta specifico della workstation.

## Struttura consigliata repository

Codex può creare una cartella tipo:

`scripts/windows_bridge/`

con almeno:

- `arphe_bridge_runtime.py` — supervisor del tunnel runtime;
- `bridge_config.example.json` — esempio SENZA segreti;
- `secret_store.py` — adapter Credential Manager/DPAPI;
- `health.py` — check `/readyz`;
- `install_autostart.ps1` — crea Scheduled Task `At logon`;
- `uninstall_autostart.ps1` — rimuove Scheduled Task;
- `start_bridge.ps1` — start manuale/debug;
- `stop_bridge.ps1` — stop controllato;
- `status_bridge.ps1` — stato runtime/readyz;
- `README.md` — installazione click-by-click;
- test unitari dove possibile.

Non mettere nella repo:
- runtime API key;
- file secret reali;
- log di produzione con token;
- tunnel id personale se non serve alla documentazione.

## Config locale consigliata

Esempio concettuale NON segreto:

```json
{
  "workstation_id": "PC_SEGRETERIA",
  "tunnel_id": "tunnel_...",
  "tunnel_client_path": "C:/ARPHE/MCP/tunnel client/tunnel-client-runtime-cloudflared.exe",
  "mcp_command": "py -3 C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_SAFE_WRITE_02/ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py",
  "ready_url": "http://127.0.0.1:8080/readyz",
  "log_dir": "C:/ARPHE/MCP/logs"
}
```

Il file reale deve restare locale o essere generato dall'installer; l'esempio in repo deve usare placeholder per tunnel id e percorsi adattabili.

## Acceptance test — PC_SEGRETERIA

Il runtime v1 è PASS solo se:

1. riavvio/login Windows;
2. nessuna PowerShell da aprire manualmente;
3. il processo tunnel parte automaticamente;
4. `/readyz` diventa HTTP 200;
5. Resolve può essere aperto anche DOPO il bridge;
6. da ChatGPT `ping` funziona;
7. da ChatGPT `resolve_status` legge il Resolve reale;
8. `create_safe_working_timeline` crea una timeline vuota e torna all'originale;
9. chiudendo e riaprendo Resolve, il bridge torna operativo senza reinstallazione;
10. terminando volontariamente il tunnel runtime, il supervisor lo riavvia con backoff;
11. nessun segreto compare in log/config/repo.

## Replica — PC_PERSONALE

Dopo il PASS del runtime sul PC segreteria:

1. installare/aggiornare DaVinci Resolve Studio;
2. impostare `Preferences -> System -> General -> External scripting using = Local`;
3. installare Python compatibile e MCP SDK;
4. clonare/scaricare la repository ARPHE;
5. creare `C:\ARPHE\MCP\`;
6. installare/copiare `tunnel-client-runtime-cloudflared`;
7. copiare dal repo il bridge e il runtime Windows, NON i segreti;
8. creare un nuovo tunnel `ARPHE-RESOLVE-PERSONALE`;
9. creare una nuova runtime API key Restricted con `Tunnels Read + Use`;
10. salvare la key nello storage sicuro del PC personale;
11. generare config locale con `workstation_id = PC_PERSONALE`;
12. installare il Scheduled Task di autostart;
13. verificare `/readyz`;
14. creare/collegare una app ChatGPT dedicata al tunnel personale;
15. ripetere gate READ;
16. ripetere SAFE WRITE su timeline vuota;
17. solo dopo dichiarare `PC_PERSONALE = VALIDATED`.

## Importante: cosa si copia e cosa NO

Si copia tramite repository:
- codice bridge;
- launcher/supervisor;
- script installazione;
- documentazione;
- config template;
- test.

NON si copia tra macchine:
- runtime API key;
- secret store;
- process state;
- log;
- tunnel identity se si vuole mantenere separazione per workstation.

## Codex — task immediato

Questo blocco è adatto a Codex perché richiede lavoro di repository, più file, refactor, script PowerShell, test e documentazione.

Codex deve implementare SOLO l'infrastruttura di avvio persistente e deployment multi-workstation. NON deve aggiungere nuove capacità editoriali o nuove write tool Resolve in questo task.

### Vincoli Codex

- preservare le tool validate `ping`, `resolve_status`, `create_safe_working_timeline`;
- nessuna shell arbitraria esposta a ChatGPT;
- nessuna API key nel repo;
- niente GUI desktop di montaggio;
- autostart via Task Scheduler nella sessione utente per v1;
- log redatti;
- health check `/readyz`;
- restart con backoff;
- install/uninstall/status documentati click-by-click;
- non modificare timeline Resolve durante startup;
- mantenere il PC segreteria come ambiente di riferimento corrente;
- preparare replica pulita sul PC personale con tunnel/key separati.

## Definition of Done

`ARPHE_WINDOWS_BRIDGE_RUNTIME_V1` è completato quando il PC segreteria può essere riavviato e, dopo il login, ChatGPT riesce a raggiungere Resolve senza che l'operatore apra manualmente PowerShell o lanci comandi tunnel.

`ARPHE_PERSONAL_WORKSTATION_REPLICA_V1` sarà completato solo quando lo stesso stack sarà installato sul PC personale con tunnel/key dedicati e supererà nuovamente READ + SAFE WRITE end-to-end.
