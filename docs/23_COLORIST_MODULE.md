# Modulo Colorist ARPHE

## Stato

`CODICE OFFLINE VALIDATO / GATE NATIVO PENDING`

Il modulo è presente soltanto nel mirror sorgente. Non è installato nel runtime, non è stato pubblicato nell'app MCP e non è stato provato sul progetto Resolve attualmente aperto. `CAP_COLORIST` è `false` per default.

## Provenienza verificata

- Il checkout Git verificato ha origin
  `https://github.com/arphesegreteria-arch/video-editing-manual.git`.
- Quel checkout contiene effettivamente il sorgente bridge esaminato e modificato in
  `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03`; non è stato quindi assunto dal nome del
  repository, ma verificato nel worktree e nel remote Git.
- Non è emersa una seconda repository GitHub dedicata al bridge. Resta però non dimostrato che il
  runtime installato di `ARPHE Resolve Personale` sia stato distribuito esattamente da questo commit:
  servirà confrontarne manifest/versione quando il runtime potrà essere ispezionato senza interferire
  con il montaggio.

## API Resolve 21 verificate dalla documentazione installata

La distribuzione locale di DaVinci Resolve Studio 21.1.1 espone nel file `DaVinciResolveScript.pyi`:

- `TimelineItem.GetCurrentVersion`, `GetVersionNameList`, `AddVersion` e `LoadVersionByName` per versioni colore locali;
- `TimelineItem.SetCDL` con `NodeIndex`, `Slope`, `Offset`, `Power` e `Saturation`;
- `TimelineItem.CopyGrades` per copiare il node-stack layer corrente verso target espliciti;
- `TimelineItem.GetNodeGraph` e `Graph.ApplyGradeFromDRX` per look DRX;
- `Timeline.GetCurrentClipThumbnailImage` e `Project.ExportCurrentFrameAsStill`, non usati dalla v1 perché richiederebbero spostamenti di pagina/playhead o scritture su file durante la preview.

L'API pubblica non offre controlli completi equivalenti a tutte le primary wheels, né espone un comando automatico affidabile per white balance o camera match. La v1 traduce quindi correzioni numeriche limitate in ASC-CDL. Temperatura/tinta e contrasto sono approssimazioni deterministiche da calibrare visivamente nel gate nativo.

## Workflow pubblico

1. `inspect_colorist_context` legge clip ID, versioni colore correnti, API disponibili e preset.
2. `prepare_colorist_plan` crea un piano locale immutabile per clip espliciti; non scrive in Resolve.
3. `inspect_colorist_plan` mostra stato, fingerprint e parametri.
4. `approve_colorist_plan` richiede fingerprint esatto e ruolo `ALESSIO` o `COLORIST`; non scrive in Resolve.
5. `apply_colorist_plan` richiede `CAP_COLORIST=true`, ricontrolla contesto e versioni, poi crea una nuova versione locale per ogni clip.
6. `preview_colorist_version` carica soltanto la versione `before` o `after` registrata per un clip del piano.
7. `restore_colorist_preview` richiede il clip esplicito e ripristina soltanto la versione che era
   attiva su quel clip prima della preview.
8. `submit_colorist_review` registra accettazione o rifiuto umano senza salvare il progetto e senza eliminare versioni.

## Correzioni tecniche

Input pubblici consentiti:

- `temperature`: da `-1.0` a `1.0`;
- `tint`: da `-1.0` a `1.0`;
- `exposure_stops`: da `-2.0` a `2.0`;
- `contrast`: da `-1.0` a `1.0`;
- `saturation`: da `0.0` a `2.0`.

Il bridge genera internamente il CDL di node 1 (`NodeIndex` è un intero, come richiesto dagli stub
Resolve 21). Nessun tool accetta un CDL libero, un node index, un LUT path o un DRX path.

## Preset ARPHE

Il registro `colorist_presets.json` contiene `ARPHE_CLEAN_NEUTRAL`, `ARPHE_WARM_PRESENCE` e `ARPHE_SOFT_LUXURY`. Sono preset sperimentali e non ancora look di produzione. I DRX opzionali sono dichiarati nello stesso registro come percorsi relativi all'`asset_root`; la configurazione iniziale non ne abilita alcuno. Durante la preparazione il piano lega percorso relativo, dimensione e SHA-256 del DRX. Qualunque modifica prima dell'apply blocca l'operazione prima di una write Resolve.

## Matching multicamera

Quando `reference_clip_id` è presente, il bridge crea una nuova versione locale su riferimento e target, applica CDL e DRX soltanto al riferimento, usa `CopyGrades` verso i target espliciti e verifica con read-back che ogni target sia ancora sulla nuova versione. Non effettua analisi automatica delle camere: la scelta del riferimento resta umana.

## Non distruttività e failure

- Le versioni esistenti non vengono rinominate, sovrascritte, resettate o cancellate.
- Un nome `ARPHE_` non costituisce autorizzazione: progetto e timeline devono essere presenti nel
  registry locale o nelle allowlist esplicite.
- Una collisione di nome ferma tutto prima della prima write.
- Progetto, timeline, identità timeline, clip ID e versioni correnti devono coincidere col piano approvato.
- Prima della prima write il job passa persistentemente da `APPROVED` ad `APPLYING`; un errore viene
  registrato come `FAILED_RECOVERABLE` se il restore è completo o `FAILED_MANUAL` se non lo è,
  evitando un retry cieco di un piano apparentemente approvato.
- Con DRX selezionato, node graph e `ApplyGradeFromDRX` vengono verificati su tutti i target diretti
  prima di creare versioni.
- In caso di errore dopo una write parziale, il bridge tenta di ricaricare per ogni clip la versione attiva registrata prima dell'apply e restituisce l'elenco delle nuove versioni rimaste.
- L'evidenza di apply deve contenere esattamente un record per clip e versioni `after` deterministiche;
  record duplicati, incompleti o alterati vengono rifiutati.
- La preview registra persistentemente la versione attiva prima del cambio e il restore agisce su un
  solo clip; non forza più tutti i clip del piano sulla versione `after`.
- Una review non può essere accettata o rifiutata finché esiste una preview non ripristinata.
- Il modulo non salva il progetto, non renderizza e non cambia pagina o playhead.

## Gate nativo futuro

Da eseguire soltanto con consenso, editor fermo e progetto usa-e-getta:

1. installare il codice su `PC_PERSONALE` senza attivare il flag;
2. aggiornare lo schema dell'app MCP e confermare che inspect/prepare non scrivano;
3. creare un progetto ARPHE disposable con chart e due clip camera sintetici;
4. attivare `CAP_COLORIST` soltanto per il gate;
5. verificare AddVersion, CDL, optional DRX, CopyGrades, collisione, stale context e recovery;
6. confrontare prima/dopo in Color page con scopes e revisione umana;
7. riportare `CAP_COLORIST=false`, ripristinare progetto iniziale e documentare l'evidenza.

Verifica offline nel worktree isolato: 532 test complessivi superati, con 2 skip; i 26 test
Colorist passano e il gruppo focalizzato con feature flag totalizza 27/27. La venv isolata usa le
dipendenze dichiarate dal bridge e non modifica il runtime attivo.

Nessun test nativo è stato ancora eseguito. Il gate è autorizzato soltanto su una copia del progetto
test, con Resolve libero dal lavoro audio, coordinamento preventivo e rollback/read-back. Anche un job rimasto
`APPLYING` dopo un errore di persistenza richiede ispezione e recupero umano: non viene rieseguito
automaticamente.

