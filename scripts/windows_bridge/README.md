# ARPHE Windows Bridge Runtime v1 — PC_SEGRETERIA

Implementazione limitata a `ARPHE_WINDOWS_BRIDGE_RUNTIME_V1` per il PC della segreteria. Non contiene GUI, non modifica Resolve allo startup e non aggiunge tool MCP. Avvia esclusivamente il tunnel già validato, che a sua volta esegue il bridge indicato da `MCP_COMMAND`.

## Sicurezza e comportamento

- Task Scheduler `At logon`, nella sessione dell'utente e con privilegi limitati.
- Azione diretta `pythonw.exe`/`pyw.exe`: nessuna finestra PowerShell permanente.
- API key cifrata con Windows DPAPI per-user in `%LOCALAPPDATA%\ARPHE\WindowsBridgeRuntimeV1\runtime_api_key.dpapi`.
- La key entra solo nell'environment del processo tunnel come `CONTROL_PLANE_API_KEY`.
- Config e stato non contengono la key. Output del tunnel redatto prima della rotazione dei log.
- Health gate fisso `http://127.0.0.1:8080/readyz`: richiede HTTP 200 e body `ready`.
- Sei fallimenti consecutivi causano un restart. Uscite inattese usano backoff esponenziale 2–60 secondi.
- Un Job Object con `KILL_ON_JOB_CLOSE` impedisce processi tunnel/bridge orfani.
- Mutex per-user: una sola istanza del supervisor.

## Prerequisiti sul PC segreteria

1. Python 3 con `python.exe` + `pythonw.exe`, oppure Windows launcher `py.exe` + `pyw.exe`.
2. Il binario `tunnel-client-runtime-cloudflared.exe` già validato.
3. Il bridge validato `ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py` e le sue dipendenze.
4. Tunnel ID del PC segreteria e relativa Runtime API key Restricted (`Tunnels Read + Use`).

Prima dell'installazione, verificare i percorsi. Questi comandi sono di sola lettura:

```powershell
Test-Path 'C:\ARPHE\MCP\tunnel client\tunnel-client-runtime-cloudflared.exe'
Test-Path 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_SAFE_WRITE_02\ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py'
Get-Command py.exe, pyw.exe -ErrorAction SilentlyContinue
```

## Installazione

Aprire PowerShell come lo stesso utente Windows che usa Resolve. Dalla root di questa repository:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows_bridge\install_autostart.ps1 `
  -TunnelId 'tunnel_SOSTITUIRE_CON_ID_SEGRETERIA' `
  -TunnelClientPath 'C:\ARPHE\MCP\tunnel client\tunnel-client-runtime-cloudflared.exe' `
  -McpCommand 'py -3 C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_SAFE_WRITE_02/ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py'
```

L'installer mostra due prompt mascherati per la Runtime API key. La key non va aggiunta al comando. Per ispezionare anticipatamente le modifiche senza applicarle, aggiungere `-WhatIf`.

Se Python non è rilevato automaticamente, aggiungere percorsi espliciti:

```powershell
  -PythonPath 'C:\Users\NOME\AppData\Local\Programs\Python\Python313\python.exe' `
  -PythonwPath 'C:\Users\NOME\AppData\Local\Programs\Python\Python313\pythonw.exe'
```

Reinstallando il codice, usare `-KeepExistingSecret` per conservare il blob DPAPI. La config è in `%LOCALAPPDATA%`; i moduli runtime sono copiati in `C:\ARPHE\MCP\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1`.

## Start, stop e stato

```powershell
.\scripts\windows_bridge\start_bridge.ps1
.\scripts\windows_bridge\status_bridge.ps1
.\scripts\windows_bridge\stop_bridge.ps1
```

`status_bridge.ps1` restituisce exit code `0` solo quando il task esiste e `/readyz` è pronto. Per un restart amministrativo:

```powershell
.\scripts\windows_bridge\stop_bridge.ps1
.\scripts\windows_bridge\start_bridge.ps1
```

Log redatti: `C:\ARPHE\MCP\logs\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1\runtime.log`.

## Test di accettazione PC_SEGRETERIA

1. Eseguire `status_bridge.ps1`; attendere `Readyz : True`.
2. Da ChatGPT eseguire `ping`, poi `resolve_status` con Resolve aperto.
3. Chiudere Resolve, riaprirlo e ripetere `resolve_status` senza reinstallare.
4. Eseguire `create_safe_working_timeline` e verificare ritorno alla timeline originale.
5. Verificare il backoff terminando **solo il processo tunnel indicato da `TunnelPid`**:

   ```powershell
   $s = Get-Content "$env:LOCALAPPDATA\ARPHE\WindowsBridgeRuntimeV1\runtime_state.json" -Raw | ConvertFrom-Json
   Stop-Process -Id $s.tunnel_pid
   Start-Sleep -Seconds 5
   .\scripts\windows_bridge\status_bridge.ps1
   ```

6. Fare logout/login (o riavviare Windows), senza aprire PowerShell, poi verificare `/readyz` e i gate ChatGPT.
7. Cercare indicatori di segreti nei file locali (non stampa il blob DPAPI):

   ```powershell
   $secretPattern = 'CONTROL_PLANE_API_KEY\s*[=:]\s*(?!\[REDACTED\])\S+|Authorization:\s*Bearer\s+(?!\[REDACTED\])\S+|\bsk-[A-Za-z0-9_-]{12,}\b'
   Select-String -Path 'C:\ARPHE\MCP\logs\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1\*.log' -Pattern $secretPattern
   Select-String -Path "$env:LOCALAPPDATA\ARPHE\WindowsBridgeRuntimeV1\*.json" -Pattern $secretPattern
   ```

Il test del restart è circoscritto al PID tunnel. Non terminare processi Resolve e non cancellare task/file per provarlo.

## Disinstallazione

La modalità normale ferma il runtime e rimuove solo lo Scheduled Task, preservando codice distribuito, config, blob DPAPI, stato e log:

```powershell
.\scripts\windows_bridge\uninstall_autostart.ps1
```

La cancellazione permanente dei dati locali è separata e richiede conferma esplicita:

```powershell
.\scripts\windows_bridge\uninstall_autostart.ps1 -PurgeLocalData
```

`-PurgeLocalData` elimina config, secret cifrato, stato e codice distribuito; conserva i log. Non usarlo per un normale aggiornamento.
