# Resolve retirement archive-first — design

## Obiettivo

Ridurre timeline e progetti di prova in Resolve senza dipendere da cancellazioni irreversibili o
da default impliciti. Il modulo è separato dall'igiene dei file tecnici e non opera mai sul PC di
un'altra workstation.

## Contratto operativo

Ogni ritiro segue quattro fasi persistenti: `PREPARED`, `APPROVED`, `EXECUTED`, `RECOVERED`.

1. Il bridge accetta soltanto nomi `ARPHE_` già registrati o allowlisted.
2. Salva il progetto, esporta un `.drp` univoco con still/LUT e verifica presenza, dimensione e
   SHA-256 prima di creare la proposta.
3. La proposta contiene workstation, tipo (`timeline` o `project`), identità del progetto,
   eventuale timeline, last-modified Resolve, archivio e fingerprint immutabile.
4. Un tecnico approva esplicitamente quel fingerprint.
5. L'esecuzione ricontrolla gate, workstation, fingerprint, hash `.drp`, last-modified, target e
   assenza di render lock. Qualunque divergenza blocca senza eliminare.
6. Dopo la rimozione il bridge verifica che il target non esista più e conserva il `.drp`.

Una timeline corrente non viene rimossa: l'editor deve selezionarne un'altra. Un progetto corrente
viene chiuso solo nell'ultima fase, dopo tutti i controlli; se `DeleteProject` fallisce, il bridge
prova a ricaricarlo. La API Resolve non offre un cestino per timeline/progetti: il rollback è quindi
un import del `.drp` come nuovo progetto `ARPHE_RECOVERY_...`, mai una sovrascrittura.

## Archivi e retention

Gli archivi risiedono in una radice per-workstation esterna alla libreria Resolve. Si conservano
tutti gli export degli ultimi 30 giorni e comunque gli ultimi 3 per progetto. Gli archivi fuori da
entrambe le condizioni sono soltanto candidati: questo modulo non li elimina automaticamente.
Una futura quarantena file richiederà proposta e approvazione proprie, con almeno 7 giorni prima
del purge. Questa scelta impedisce che la pulizia tecnica cancelli l'unico rollback Resolve.

## Superficie MCP

- `prepare_resolve_retirement(kind, project_name, timeline_name)` — scrive archivio e proposta,
  ma non rimuove nulla.
- `approve_resolve_retirement(retirement_id, operator_role)` — approva il fingerprint; ruolo
  richiesto `technical`.
- `execute_resolve_retirement(retirement_id)` — distruttivo, idempotente, gate separato.
- `inspect_resolve_retirements()` — sola lettura, senza percorsi assoluti.
- `recover_resolve_retirement(retirement_id)` — importa l'archivio con nome recovery univoco.

Il gate `CAP_RESOLVE_RETIREMENT` è `false` per default e indipendente da
`CAP_ARTIFACT_MAINTENANCE`. `PC_PERSONALE` e `PC_SEGRETERIA` hanno registri e archivi distinti.

## Rollout

Prima suite con fake Resolve e failure injection. Poi installazione solo `PC_PERSONALE`, gate
spento. Il test distruttivo live richiede un progetto/timeline disposable dedicato e Resolve
disponibile; non usa mai il lavoro aperto sul PC segreteria.
