# Inventario protetto e manutenzione offline

Data verifica: 24 ottobre 2026.

Questa estensione resta sul branch offline `codex/artifact-hygiene-offline`. Non è installata nel
runtime, non abilita `CAP_ARTIFACT_MAINTENANCE` e non ha spostato, messo in quarantena o cancellato
alcun file.

Il criterio generale per i futuri producer è descritto in
`docs/25_REUSABLE_MEDIA_TRANSFORMATION_BRIDGE.md`: intento naturale, analisi read-only, selezione
verificata, esecuzione non distruttiva e verifica con review umana. L'inventario conserva la
provenienza di questo flusso ma non decide il trattamento creativo.

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
- La migrazione legacy produce soltanto proposte validate. Non crea né aggiorna il registro. I
  manifest senza identità workstation o fingerprint sorgente completo restano in review manuale.

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

Configurazione isolata del gate audio V5 (snapshot precedente all'ultimo hardening):

- 179 elementi visibili come sconosciuti protetti, 95.987.863 byte complessivi nelle radici
  configurate;
- la prima migrazione dry-run aveva proposto 1 sorgente audio, 4 derivati e 5 manifest protetti;
- l'hardening successivo richiede anche `workstation_id` e fingerprint sorgente: i manifest legacy
  che non li contengono non vengono più adottati automaticamente e restano protetti come
  sconosciuti fino a review manuale;
- nessuna scrittura del registro è stata eseguita.

Le proposte storiche coprivano sorgenti, derivati di ascolto, altri output di prova e relativi
manifest. Quei nomi e parametri non fanno parte del contratto riusabile e non diventano default.
Confronti A/B, sorgenti, backup Colorist e progetti gate non sono candidati di spazio recuperabile.
Poiché tutto l'inventario legacy resta protetto, lo spazio recuperabile simulato in questa fase è
**0 byte**.

## Limiti

- Il branch non retro-registra automaticamente gli artefatti già esistenti.
- I quattro percorsi bloccati richiedono ispezione manuale prima di qualunque decisione.
- Il backup pre-gate non ha una radice configurata nel profilo ed è quindi indicato come
  `REFERENCE_ONLY_UNCONFIGURED`, mai scansionato.
- La registrazione Colorist protegge il ledger e le identità di progetto/timeline/DRX; non esporta né
  gestisce database, progetti o timeline Resolve.
- Nessun beneficio di spazio è promesso finché una futura review umana non identifica record
  disposable realmente terminali e ne approva la quarantena.

## Verifica finale del branch

- Il purge è irraggiungibile anche costruendo in memoria una policy alterata.
- Bundle audio e aggiornamenti Colorist sono registrati sotto lock; la lettura dello stato audio non
  produce scritture.
- La classificazione protetta può promuovere in sicurezza un vecchio record disposable e verifica
  il containment nella radice dichiarata.
- Scansione e simulazione falliscono chiuse con un lock residuo e includono nel conteggio anche gli
  elementi sconosciuti protetti.
- Scansione e simulazione non creano lock né altri file: confrontano un token read-only del registro
  prima e dopo l'osservazione e falliscono con `REGISTRATION_CHANGED` se il contenuto cambia.
- Qualunque job audio o Colorist attivo sospende le proposte di quarantena.
- Il controllo periodico ritenta al ciclo successivo dopo errori transitori di caricamento o audit.
- Suite isolata: 591 test eseguiti, tutti superati; 4 test saltati per dipendenze non disponibili.

La correzione read-only è stata verificata esclusivamente su radici temporanee. Non è stata eseguita
una nuova scansione live e lo snapshot riportato sopra non autorizza classificazioni automatiche.

