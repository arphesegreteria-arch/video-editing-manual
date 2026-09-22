# Matrice di validazione per workstation

| Controllo | PC_PERSONALE | PC_SEGRETERIA |
|---|---|---|
| Runtime isolato e `/readyz` | PASS | PASS baseline |
| Gate B composizione + testo | PASS | PASS |
| Gate C grafico/card | PASS | PASS |
| Gate D motion card | prima prova FAIL visiva; correzione installata | non aggiornato da questa sessione |
| Gate E stack motion | da eseguire | da ripetere solo se si aggiorna quel runtime |
| Suite creativa automatica | PASS: 59 test | non rieseguita |
| Suite Windows PowerShell | 4 test bloccati dalla modalità linguaggio ristretto | baseline non rieseguita |

Un PASS su una workstation non viene usato come prova dell'altra. File, task, tunnel e segreti
restano per-workstation.

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
Copy-Item .\scripts\windows_bridge\profiles\pc_personale.example.json `
  .\scripts\windows_bridge\profiles\pc_personale.local.json
```

Modificare esclusivamente la copia `.local.json`: inserire il nuovo `tunnel_id` personale e
verificare i percorsi. Il file locale è escluso da Git. Prima di installare eseguire il preflight,
che non scrive file, task o segreti:

```powershell
.\scripts\install_personal_pc.ps1 `
  -ProfilePath .\scripts\windows_bridge\profiles\pc_personale.local.json `
  -PreflightOnly
```

Solo dopo `Preflight PASS` eseguire lo stesso comando senza `-PreflightOnly`. L'installer crea un
ambiente Python isolato e chiede due volte la Runtime API key in un campo mascherato. Non inserire
mai la chiave nel comando o nel profilo.

Se una config `PC_PERSONALE` esistente usa ancora il tunnel legacy, il cambio viene bloccato per
impostazione predefinita. Dopo aver verificato il nuovo tunnel dedicato, aggiungere una sola volta
`-AllowTunnelChange`.

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

Eseguire `git pull`, poi rilanciare prima il preflight e quindi l'installer con lo stesso profilo
locale e `-KeepExistingSecret`. Le dipendenze vengono aggiornate nell'ambiente isolato del profilo.
Se cambia l'elenco delle azioni MCP, aggiornare e ripubblicare lo schema della app ChatGPT; per
sole correzioni interne non serve creare una nuova app.

## Backup

GitHub contiene codice e manuali. Fare inoltre backup separato di progetti Resolve, media e asset. Non archiviare in GitHub chiavi, file `.dpapi`, config locali, log o materiale clinico/personale.
### Aggiornamento 2026-09-22 — runtime personale e motion

Il runtime personale `PC_PERSONALE` usa una configurazione stabile sotto
`C:\\ARPHE\\MCP\\runtime-configs\\PC_PERSONALE`; non condivide file di stato o runtime con
`PC_SEGRETERIA`. Questo evita la virtualizzazione della copia sotto AppData del pacchetto Codex.

La verifica locale del bridge creativo è verde (59 test). Durante il Gate D è stato isolato un
difetto di animazione: Fusion riceveva la posizione 2D come `BezierSpline` e l'opacità sul
`Transform.Blend`, che non è l'opacità dell'elemento. La correzione usa `Path` per `Center` e il
`Blend` del merge esterno per l'opacità. La copia installata sul solo PC personale è stata
aggiornata; la nuova prova visiva va eseguita alla prossima sessione con crediti disponibili.
