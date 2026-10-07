# 20 — Ritiro timeline/progetti Resolve e recovery

Stato: **CODICE VALIDATO / ROLLOUT LIVE PENDING**.

Questo modulo serve a togliere dal database Resolve timeline o progetti ARPHÈ non più utili senza
affidarsi a una cancellazione cieca. È distinto dalla manutenzione dei file tecnici descritta nel
capitolo 19.

## Flusso obbligatorio

1. `prepare_resolve_retirement` salva il progetto, esporta un `.drp` con still/LUT, calcola
   dimensione e SHA-256 e registra una proposta. Non rimuove nulla.
2. Un operatore `technical` o Alessio usa `approve_resolve_retirement`; l'approvazione è legata al
   fingerprint immutabile della proposta.
3. `execute_resolve_retirement` ricontrolla archivio, workstation, target, last-modified e render
   lock. Se il progetto è cambiato, la proposta scade e va rifatta.
4. Dopo la rimozione il bridge verifica che il solo target approvato sia assente. Il `.drp` resta.
5. `recover_resolve_retirement` importa il `.drp` come nuovo progetto
   `ARPHE_RECOVERY_...`; non sovrascrive il progetto originale né un recovery esistente.

Una timeline corrente è sempre protetta: prima del ritiro occorre selezionarne un'altra. Per un
progetto, `CloseProject` viene chiamato soltanto dopo l'archivio e tutti i controlli; Resolve
richiede infatti che il progetto non sia caricato per eseguire `DeleteProject`.

## Confini e isolamento

- Sono ammessi solo nomi `ARPHE_` registrati o allowlisted.
- Un render lock attivo blocca prepare ed execute.
- I tool non accettano percorsi: archive root e registry provengono dal profilo locale.
- `CAP_RESOLVE_RETIREMENT` è separato, `false` per default e non viene ereditato dall'altro PC.
- Il registry include `workstation_id`; mismatch PC blocca installer e runtime.
- Un crash usa lo stato persistente `EXECUTING`: se il target è già assente finalizza senza una
  seconda cancellazione; se è ancora presente ricontrolla anche il last-modified.

## Retention archivi

`inspect_resolve_retirements` conserva tutti gli archivi degli ultimi 30 giorni e comunque gli
ultimi 3 per progetto. Gli altri sono marcati `CANDIDATE`, ma non vengono eliminati o spostati
automaticamente. Una futura rimozione degli archivi richiederà proposta, approvazione e almeno 7
giorni di quarantena: il backup che rende reversibile il ritiro non entra nel cleanup tecnico.

## Evidenza codice al 2026-10-08

- Creative: 166 test eseguiti, 165 PASS, 1 SKIP ambientale symlink Windows.
- Windows: 49 test eseguiti, 48 PASS, 1 SKIP DPAPI ambientale.
- Test coperti: export verificato senza delete, timeline corrente, render lock, ruolo tecnico,
  progetto mutato, archivio alterato, delete esatto/idempotente, crash-reconciliation, close/delete
  progetto, recovery senza overwrite, retention 30 giorni + ultimi 3 e isolamento installer.
- `PC_PERSONALE`: installazione e inspection read-only PENDING.
- `PC_SEGRETERIA`: non toccato; progetto aperto non coinvolto.

Il test live distruttivo va eseguito soltanto su un progetto e una timeline disposable dedicati.
