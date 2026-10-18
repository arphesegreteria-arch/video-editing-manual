# Riconciliazione locale PC_PERSONALE — 2026-10-18

## Decisione operativa

Gli Shorts podcast sono sospesi su richiesta dell'utente. Nessuna modifica a
Resolve, alle timeline o alla segreteria fa parte di questa riconciliazione.

La base locale di sviluppo da mantenere è questa checkout, sul ramo
`arphe/v11-caption-extension-personale`, derivata da `main` a `2c4d245`.
Il nome della directory di release non identifica più il suo HEAD: verificare
sempre `git rev-parse HEAD` e lo stato della working tree prima di distribuirla.

## V11 e ultima revisione

Le V11 sono l'estensione sottotitoli del progetto
`ARPHE_BIORIVITALIZZAZIONE_ADV_20261013_PERSONALE`, non un progetto podcast.
La modifica locale più recente autorizza esclusivamente la copia
`ARPHE_BIORIVITALIZZAZIONE_V11_KARAOKE_UPPER_SAMPLE_R6_CAPTION_RECOVERY_20261017`
e il range `[108014, 108574)`. L'utente ha confermato di mantenere l'ultima versione
del lavoro Biorivitalizzazione. Questa nota non certifica un'ispezione visiva né
afferma che R6 sia l'ultima timeline presente nel database Resolve, non interrogato.

Mantenere i commit V11 `63be895`, `ced9108`, `8cc800a` e la modifica R6 con relativo
test. Non rimuovere i riferimenti alle revisioni precedenti: sono guardrail di
compatibilità, non copie di media da eliminare.

## Discrepanze classificate

| Area | Evidenza | Decisione |
| --- | --- | --- |
| GitHub main | `2c4d245` alla verifica del 18 ottobre | Non scambiarlo per il codice locale più recente |
| Riconciliazione render | `c26f123`, già sul ramo remoto dedicato | Conservare nella storia della base locale |
| V11 | Tre commit successivi e modifica R6 non pubblicata | Consolidare localmente, senza rollback del runtime |
| Runtime creativo | `server.py` e `tool_catalog.py` differiscono solo per CRLF/LF; gli altri moduli Python confrontati coincidono | Nessuna sostituzione necessaria |
| Vecchia repo-audit | Lavoro non committato voice-over, calibrazioni e strumenti V6/V7 | Conservare separatamente come storico; non applicare in blocco alla base attuale |
| Checkout storico personale | Base `326d906`; avvio Python isolato e lock Resolve già presenti nella base recente, che contiene anche evoluzioni successive | Non usare per un nuovo deployment; preservare i delta locali |
| Graphic kit | Ramo locale `codex/local-graphic-renderer`, commit `a5a20b1`, checkout pulita | Conservare come aggiornamento separato; non mischiarlo al repository bridge |

Gli script V6/V7 non sono autorizzati dalla conferma della V11: non eseguirli
automaticamente. Il mancato trasferimento dei loro delta non è una cancellazione.
Le parti riutilizzabili richiedono una revisione dedicata prima di essere integrate.

## Verifiche di questa sessione

- Ping del bridge: `PC_PERSONALE`, `CREATIVE_GATED`.
- Ultima lettura del contesto: Resolve connesso, `Untitled Project`, nessuna timeline.
- Test V11: 11 superati, inclusi range R6 e rollback su read-back errato.
- Test renderer grafico: 11 superati.
- Test control plane isolati: 6 superati.
- Suite bridge completa: interrotta due volte con `KeyboardInterrupt`, non verde.
- Esecuzione per moduli: primi 29 moduli superati, poi interruzione durante il
  modulo trascrizione. Non equivale a una suite completa superata.

Non promuovere questa riconciliazione a release completamente validata finché
l'interruzione della suite non viene spiegata e la suite completa non termina.
Non alterare o saltare permanentemente i test per ottenere un risultato verde.

### Difetto preesistente individuato nel controllo PID

`carabellese_transcription._pid_is_running` usa `os.kill(pid, 0)` anche su Windows.
Una verifica con `os.kill` intercettato (nessun segnale reale inviato) conferma la
chiamata; su questo interprete `signal.CTRL_C_EVENT == 0`. Non è un controllo di
esistenza innocuo su Windows: il comportamento documentato è l'invio di un evento
console. I test di trascrizione lo invocano con il PID del processo corrente.
Questo è coerente con le interruzioni osservate e va corretto prima di ripetere la
suite completa. Non è un difetto delle V11. La correzione non è inclusa in questo
consolidamento: serve una query di stato Windows senza segnali, con test dedicati.
Riferimento: https://docs.python.org/3/library/os.html#os.kill.

## Backup locale verificato

Nella workspace della chat, `diagnostics/reconciliation-backup-20261018` contiene:

- bundle Git verificati delle due checkout storiche, del bridge pre-R6 e del kit;
- patch separate dell'indice e della working tree delle checkout storiche;
- 12 file non tracciati della vecchia repo-audit e 2 della checkout storica,
  copiati con struttura relativa e SHA-256 verificato.

Gli originali non sono stati cancellati o ripuliti. Per recuperare le modifiche
storiche, usare una checkout separata del bundle, ripristinare prima `index.patch`
con `git apply --index`, poi `worktree.patch` con `git apply`, e infine i file della
cartella `untracked`. Non applicare queste patch direttamente al runtime operativo.

## Pubblicazione e segreteria

Questa sessione consolida solo lo stato locale. Nessun push, merge o aggiornamento
del PC_SEGRETERIA è implicito. Prima di pubblicare: revisione dei delta e della
documentazione, verifica dati interni, test completi e PR separate per bridge e kit.
Il vecchio handoff conteneva già una nota di pubblicazione bloccata: non aggirarla
pubblicando automaticamente l'archivio dei file locali.

Prima di un futuro rollout: scegliere un commit immutabile, verificare l'assenza di
modifiche pendenti, creare un manifest dei file e un backup del runtime destinazione,
mantenere configurazioni e credenziali specifiche della workstation. Non copiare
segreti o configurazioni personali in segreteria.
