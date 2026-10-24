# Inventario protetto e manutenzione offline

Data verifica: 24 ottobre 2026.

Questa estensione resta sul branch offline `codex/artifact-hygiene-offline`. Non è installata nel
runtime, non abilita `CAP_ARTIFACT_MAINTENANCE` e non ha spostato, messo in quarantena o cancellato
alcun file.

## Comportamento proposto

- I nuovi WAV, manifest audio, registri Colorist e dipendenze di review sono registrati come
  `PROTECTED`, con SHA-256 e dipendenze opache.
- Un job attivo, una review umana pendente, una preview Colorist attiva, un hash cambiato o un lock
  residuo da crash bloccano la proposta.
- Lo scan e la simulazione sono funzioni read-only separate. Gli elementi sconosciuti diventano
  `UNCLASSIFIED_PROTECTED`; nome, estensione ed età non autorizzano l'adozione.
- Il controllo periodico usa un solo thread daemon nel processo Creative e la cadenza UTC già
  registrata. Non crea task Windows e non richiede rete.
- La quarantena esistente rimane recuperabile. La policy dichiara `purge_enabled=false`; anche dopo
  sette giorni un record resta `QUARANTINED` e viene riportato come `PURGE_DISABLED`.
- La migrazione legacy produce soltanto proposte validate. Non crea né aggiorna il registro.

## Radici

`render_root` e `runtime_log_root` restano le sole radici con categorie disposable. `audio_root` e
`audio_jobs_root` vengono inventariate come radici protette. `profile_root`, `asset_root`, tutte le
`media_root`, `resolve_archive_root` e i backup sono reference-only. I progetti e le timeline Resolve
non sono filesystem cleanup targets: sono dipendenze logiche protette.

## Inventario read-only

Profilo Creative attivo:

- 173 elementi sconosciuti protetti, 72.713.068 byte;
- 4 percorsi bloccati da symlink/reparse o containment, lasciati intatti per review manuale;
- registro nuovo non presente, quindi nessun artefatto è stato adottato.

Configurazione isolata del gate audio V5:

- 179 elementi visibili come sconosciuti protetti, 95.987.863 byte complessivi nelle radici
  configurate;
- migrazione dry-run valida: 1 sorgente audio, 4 derivati e 5 manifest proposti come protetti;
- nessun errore di fingerprint e nessuna scrittura del registro.

Le proposte coprono l'originale A, il V5, la variante `PIU_NATURALE`, gli altri output di prova e i
manifest corrispondenti. A/B, sorgenti, backup Colorist e progetti gate non sono candidati di spazio
recuperabile. Poiché tutto l'inventario legacy resta protetto, lo spazio recuperabile simulato in
questa fase è **0 byte**.

## Limiti

- Il branch non retro-registra automaticamente gli artefatti già esistenti.
- I quattro percorsi bloccati richiedono ispezione manuale prima di qualunque decisione.
- Il backup pre-gate non ha una radice configurata nel profilo ed è quindi indicato come
  `REFERENCE_ONLY_UNCONFIGURED`, mai scansionato.
- La registrazione Colorist protegge il ledger e le identità di progetto/timeline/DRX; non esporta né
  gestisce database, progetti o timeline Resolve.
- Nessun beneficio di spazio è promesso finché una futura review umana non identifica record
  disposable realmente terminali e ne approva la quarantena.

