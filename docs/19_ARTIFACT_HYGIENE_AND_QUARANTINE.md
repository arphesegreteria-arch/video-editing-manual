# 19 — Igiene artefatti e quarantena

Stato codice: implementato e verificato automaticamente. Rollout live:
`PC_PERSONALE PENDING`; `PC_SEGRETERIA NON TOCCATO / PENDING`.

## Perimetro

La manutenzione riguarda esclusivamente artefatti tecnici creati e registrati dal bridge. Non
scansiona Desktop, Documenti o Download e non elimina file sconosciuti. Sorgenti, asset, config,
segreti, stato, audit, log attivo, master, file pubblicabili e oggetti Resolve sono protetti.

| Categoria | Attesa prima della quarantena |
|---|---:|
| catture diagnostiche | 24 ore |
| report temporanei | 24 ore |
| preview tecniche | 7 giorni |
| staging `VERIFIED`, `CANCELLED`, `FAILED_PREPARE` | 24 ore dallo snapshot terminale |
| staging `FAILED_RENDER`, `FAILED_VERIFY` | 7 giorni dallo snapshot terminale |
| log ruotati | 7 giorni |

Ogni elemento resta poi in quarantena per altri 7 giorni completi. Soltanto dopo può essere
eliminato. I test usano un orologio controllato; nessuna prova live viene retrodatata.

## Regole di sicurezza

- Uno staging in stato non terminale è sempre protetto, indipendentemente dall'età.
- Il manifest dello staging viene congelato soltanto dopo uno stato terminale; contenuti inattesi
  bloccano la quarantena.
- Hash, dimensione, identità workstation e radice gestita vengono ricontrollati prima di ogni move.
- Symlink, reparse point, path escape, collisioni di restore e registry di un altro PC falliscono
  chiusi.
- Un'operazione pendente viene riconciliata dal write-ahead record dopo un riavvio.
- I file non registrati sono solo `UNCLASSIFIED`: vengono mostrati, mai spostati.

## Comandi ChatGPT/MCP

- `inspect_artifact_hygiene` è read-only e funziona anche con il gate spento.
- `run_artifact_maintenance` applica solo la policy fissa; è distruttivo ma idempotente e richiede
  `CAP_ARTIFACT_MAINTENANCE=true`.
- `restore_quarantined_artifact` accetta soltanto un ID opaco, mai un percorso.

Il runner lazy attende cinque secondi dall'avvio e tenta al massimo un ciclo ogni 24 ore. Un errore
nel thread non blocca il bridge, il tunnel o Resolve.

## Log runtime

Il runtime non usa più backup numerati che si sovrascrivono. Ogni rotazione produce una directory
univoca `rotated/runtime.<UTC>.<id>/` con `runtime.log` già redatto e `artifact.json` contenente
workstation, hash, dimensione e timestamp. Solo unità complete e conformi vengono importate; quelle
incomplete o contraffatte restano visibili come errore.

## Isolamento workstation

Config Creative, registry artefatti e log sono risolti nel profilo della workstation. L'installer
aggiunge i campi mancanti senza sovrascrivere un valore esplicito del gate e lo lascia spento per
default. Un registry marcato per l'altro PC blocca l'installazione prima delle scritture.

`CAP_CLEANUP` resta accettato nelle vecchie config ma non espone più la rimozione generica di
progetti, timeline o percorsi. La gestione di progetti/timeline Resolve sarà un modulo distinto,
archive-first, con export `.drp` verificato e approvazione esplicita.

## Evidenza al 2026-10-08

- Creative: 154 test eseguiti, 153 PASS, 1 SKIP ambientale per privilegio symlink Windows.
- Windows: 45 test eseguiti, 44 PASS, 1 SKIP DPAPI per profilo CurrentUser non disponibile nel
  token di test.
- `PC_PERSONALE`: rollout e gate con file disposable ancora PENDING.
- `PC_SEGRETERIA`: nessun file, task, tunnel, config o progetto modificato; gate PENDING.

## Gate live personale

1. Installare il commit approvato soltanto nel profilo `PC_PERSONALE`, inizialmente con gate spento.
2. Eseguire l'inventario e verificare che non compaiano sorgenti, master o pubblicabili.
3. Abilitare il gate personale e creare un artefatto disposable apposito.
4. Dopo 24 ore reali: quarantena, restore, controllo hash, nuova quarantena.
5. Dopo 7 giorni reali dalla seconda quarantena: purge e verifica registry.

Il purge live non può essere marcato PASS prima che siano trascorsi sette giorni reali.
