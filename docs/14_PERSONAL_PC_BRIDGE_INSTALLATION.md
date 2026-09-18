# Replica del bridge sul PC personale

Questa è la procedura canonica per ottenere sul PC personale un bridge equivalente a quello della segreteria. Il codice è in Git; tunnel e chiave restano locali e non devono mai essere caricati nella repository.

## Cosa viene replicato

- Creative Bridge 03 e i suoi tool, inclusi long-form e acquisizione frame;
- runtime Windows con avvio automatico, health check e log redatti;
- configurazione sicura identificata come `PC_PERSONALE`.

Non vengono copiati la Runtime API key, il tunnel della segreteria, i file DPAPI, i log, i media o i progetti Resolve. La cifratura DPAPI lega la nuova chiave all'utente Windows del PC personale.

## Prerequisiti

1. Windows, DaVinci Resolve Studio e Git.
2. Python 64 bit con `python.exe` e `pythonw.exe` reali (non gli alias WindowsApps).
3. Un tunnel dedicato al PC personale, il relativo client e una Runtime API key Restricted.
4. Accesso allo stesso workspace ChatGPT Business, oppure permesso di creare una app MCP dedicata.

## Installazione

Aprire PowerShell con il normale utente che usa Resolve:

```powershell
git clone https://github.com/arphesegreteria-arch/video-editing-manual.git C:\ARPHE\video-editing-manual
cd C:\ARPHE\video-editing-manual
Set-ExecutionPolicy -Scope Process Bypass
& 'C:\PERCORSO\python.exe' -m pip install -r .\scripts\experiments\ARPHE_MCP_BRIDGE_CREATIVE_03\requirements.txt
.\scripts\install_personal_pc.ps1 `
  -TunnelId 'tunnel_ID_PERSONALE' `
  -TunnelClientPath 'C:\PERCORSO\tunnel-client-runtime-cloudflared.exe' `
  -PythonPath 'C:\PERCORSO\python.exe' `
  -PythonwPath 'C:\PERCORSO\pythonw.exe'
```

L'ultimo comando chiede due volte la chiave in un campo mascherato. Non inserirla mai nel comando o in un file della repository.

## Collegamento a ChatGPT Business

Nel pannello amministratore creare o aggiornare una app separata, consigliata come **ARPHE Resolve Personal**, collegandola al tunnel personale. Pubblicare/abilitare lo schema degli strumenti. Non far puntare due PC contemporaneamente allo stesso tunnel: lo stato diventerebbe ambiguo.

Il codice locale non può creare da solo tunnel, chiave o registrazione della app nel workspace: sono credenziali e risorse del control plane. La repository rende ripetibile tutta la parte installabile sul PC.

## Verifica

```powershell
cd C:\ARPHE\video-editing-manual
.\scripts\windows_bridge\status_bridge.ps1
```

Attendere `Readyz : True`, poi con Resolve aperto chiamare dalla app personale:

1. `ping`;
2. `resolve_status` o `get_creative_status`;
3. una sola operazione safe-write in un progetto di prova;
4. riavviare Windows e ripetere i primi due controlli.

Le feature flag avanzate partono disabilitate nella config nuova. Vanno abilitate solo dopo i relativi gate.

## Aggiornamenti futuri

Eseguire `git pull`, reinstallare le dipendenze se cambia `requirements.txt`, quindi rilanciare l'installer creativo con `-WorkstationId PC_PERSONALE`. Se cambia l'elenco delle azioni MCP, aggiornare e ripubblicare lo schema della app ChatGPT; per sole correzioni interne non serve creare una nuova app.

## Backup

GitHub contiene codice e manuali. Fare inoltre backup separato di progetti Resolve, media e asset. Non archiviare in GitHub chiavi, file `.dpapi`, config locali, log o materiale clinico/personale.
