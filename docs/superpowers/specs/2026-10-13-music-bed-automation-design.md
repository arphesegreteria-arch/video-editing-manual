# Music Bed Automation — Design

## Obiettivo

Consentire a ChatGPT di sostituire o impostare una base musicale su una timeline ARPHE in DaVinci Resolve senza controllo manuale dell'interfaccia.

## Risultato utente

L'operatore indica una traccia musicale già scaricata da una fonte autorizzata. Il bridge la colloca su una traccia musica dedicata, la adatta alla durata del montato e lascia invariati video, voce e clip non gestite dal bridge.

## Contratto proposto

Tool MCP: `set_timeline_music_bed`.

Input:
- `music_asset_id`: identificativo di un asset musicale già approvato e presente in una cartella consentita;
- `gain_db`: valore compreso tra -36 e -12 dB; default -24 dB;
- `fade_in_frames` e `fade_out_frames`: 0–60, default 12;
- `target_timeline`: timeline ARPHE registrata/allowlisted.

Comportamento:
1. valida capability, timeline, asset e intervalli;
2. importa l'asset senza restituire path assoluti;
3. usa una traccia audio dedicata del bridge;
4. rimuove soltanto una precedente musica con ownership del bridge;
5. adatta la clip alla durata video effettiva;
6. applica gain e fade;
7. registra ownership, durata, gain e audit;
8. non modifica V1, non silenzia né elimina A1, non accetta URL né comandi arbitrari.

## Sicurezza e limiti

- Nessun download da Meta né automazione di autenticazione: l'asset deve essere già locale e autorizzato.
- Nessun path arbitrario: risoluzione tramite asset registry e allowlist.
- Il tool non può rimuovere clip audio estranee o precedenti al bridge.
- La prima write reale avviene su una timeline di prova ARPHE; la capability resta disattivata fino al gate visuale/audio sul PC personale.

## Implementazione prevista

- `bridge/safety.py`: allowlist e validazione asset audio.
- `bridge/asset_tools.py`: import, placement, trim, fade e ownership della base.
- `bridge/registry.py`: record idempotente della musica gestita.
- `bridge/server.py`: schema MCP stretto per `set_timeline_music_bed`.
- test unitari e gate Resolve su timeline disposable.
- aggiornamento di `CURRENT_STATE.md`, `EXPERIMENT_LOG.md` e `CHANGELOG.md` dopo validazione.
