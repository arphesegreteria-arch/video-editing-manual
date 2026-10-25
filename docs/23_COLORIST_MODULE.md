# Modulo Colorist ARPHE

## Stato

`GATE NATIVO E CONFRONTO PRIMA/DOPO PASS / ACCETTAZIONE UMANA E CATALOGO NUOVA CHAT PENDING`

Il modulo è installato sul solo `PC_PERSONALE` ed è stato provato in un progetto Resolve
usa-e-getta. Al termine del gate `CAP_COLORIST` è stato riportato a `false` e il progetto iniziale
è stato ripristinato. Viewer, node graph e RGB parade sono stati osservati sulle versioni prima/dopo;
l'accettazione estetica dell'operatore e la verifica dell'esposizione dei nuovi tool in una sessione
app aperta dopo il rollout restano obbligatorie prima dell'uso di produzione.

## Provenienza verificata

- Il checkout Git verificato ha origin
  `https://github.com/arphesegreteria-arch/video-editing-manual.git`.
- Quel checkout contiene effettivamente il sorgente bridge esaminato e modificato in
  `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03`; non è stato quindi assunto dal nome del
  repository, ma verificato nel worktree e nel remote Git.
- Non è emersa una seconda repository GitHub dedicata al bridge. Il 2026-10-24 il runtime
  `ARPHE Resolve Personale` è stato aggiornato dal source head
  `b8b25186acb664365ba0efcba4d0e3637d3dad18`, poi integrato su `main` come commit squash
  `b87238120c3f295cdfe9eccc9bf5fd9df80a1ceb`. Prima dell'installazione è stato creato il backup
  recuperabile `C:\ARPHE\MCP\backups\PC_PERSONALE\pre_colorist_gate_20261024_135602`.
  La correzione helper asset successiva è versionata nello stesso commit Git che contiene questa
  evidenza, così non viene attribuita impropriamente al source head iniziale.

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

### Piano tecnico V2 per clip

La V2 distingue `UNIFORM_MANUAL`, per un singolo clip o materiale già omogeneo, da
`PER_CLIP_MEASURED`, in cui ogni clip riceve correzioni e CDL propri. Nel secondo caso il
fingerprint comprende osservazioni da scope o still registrati: origine, da uno a tre frame
campione e almeno una misura fra RGB neutro, percentili di luminanza o saturazione media.

Il bridge conserva queste misure come evidenza ma non promette un white balance automatico
oggettivo. Nei piani V2 `SetCDL` viene chiamato direttamente su ogni nuova versione locale e
l'evidenza contiene strategia e SHA-256 del CDL specifico di ogni clip.

## Preset ARPHE

Il registro `colorist_presets.json` contiene `ARPHE_CLEAN_NEUTRAL`, `ARPHE_WARM_PRESENCE` e `ARPHE_SOFT_LUXURY`. Sono preset sperimentali e non ancora look di produzione. I DRX opzionali sono dichiarati nello stesso registro come percorsi relativi all'`asset_root`; la configurazione iniziale non ne abilita alcuno. Durante la preparazione il piano lega percorso relativo, dimensione e SHA-256 del DRX. Qualunque modifica prima dell'apply blocca l'operazione prima di una write Resolve.

Backlog approvato: dopo la validazione delle correzioni tecniche V2, individuare e sottoporre a
review una piccola famiglia di preset ADV signature ARPHÈ coerenti con il Graphic Kit. Nessun look
signature viene mescolato alla normalizzazione tecnica in questa fase.

## Matching multicamera

Nei nuovi piani V2 `reference_clip_id` indica soltanto la camera rispetto alla quale valutare le
altre. Ogni clip riceve direttamente il proprio CDL e l'eventuale DRX allowlisted; `CopyGrades` non
è usato e il sistema non descrive come matching una semplice copia dello stesso grade. I job V1
già applicati restano leggibili, confrontabili e revisionabili col fingerprint originale. Un V1
ancora `PREPARED` o `APPROVED` deve invece essere annullato e ricreato come V2.

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
- Il gate nativo usa uno script separato che salva esplicitamente il solo progetto disposable e può
  aprire la pagina Color per l'ispezione; queste azioni non fanno parte dei tool Colorist pubblici.

## Gate nativo

Procedura da ripetere soltanto con consenso, editor fermo e progetto usa-e-getta:

1. installare il codice su `PC_PERSONALE` senza attivare il flag;
2. aggiornare lo schema dell'app MCP e confermare che inspect/prepare non scrivano;
3. creare un progetto ARPHE disposable con chart e due clip camera sintetici;
4. attivare `CAP_COLORIST` soltanto per il gate;
5. verificare AddVersion, CDL, optional DRX, CopyGrades, collisione, stale context e recovery;
6. confrontare prima/dopo in Color page con scopes e revisione umana;
7. riportare `CAP_COLORIST=false`, ripristinare progetto iniziale e documentare l'evidenza.

### Evidenza PC_PERSONALE — 2026-10-24

- Resolve Studio `21.1.1.10`; progetto usa-e-getta
  `ARPHE_COLORIST_GATE_20261024_1401`, timeline `ARPHE_COLORIST_GATE_TIMELINE`.
- Due chart sintetiche con cast diversi hanno prodotto clip ID stabili. Su entrambi Resolve ha
  confermato `GetCurrentVersion`, `GetVersionNameList`, `AddVersion`, `LoadVersionByName`,
  `SetCDL`, `GetNodeGraph` e `CopyGrades`.
- Con `CAP_COLORIST=false`, inspect e prepare hanno funzionato senza write Resolve; apply è stato
  rifiutato con `CAP_COLORIST non attiva nella config locale`.
- Con il flag temporaneamente attivo, il job `colorist_f57a0d5be0a4416c` ha creato le versioni
  `ARPHE_COLOR_F57A0D5BE0A4416C_01` e `_02`. Il CDL è stato applicato direttamente soltanto al
  riferimento; il secondo clip ha ricevuto il grade tramite `CopyGrades`.
- Preview `before` e `after` hanno caricato soltanto le versioni registrate; il restore ha riportato
  la versione attiva precedente e `preview_restore_versions` è tornato vuoto.
- Una collisione preinserita è stata rifiutata in preflight con zero nuove versioni. Un piano
  eseguito da una timeline registrata ma diversa è stato rifiutato come `Timeline Colorist stale`,
  ancora con zero nuove versioni.
- Nel probe di failure parziale il primo clip ha creato una versione, il secondo ha simulato
  `AddVersion=false`; il recovery ha ricaricato esattamente su entrambi le versioni precedenti e ha
  restituito `recoverable=true`, `manual_recovery_required=false`.
- Nessun DRX è stato provato: il registro installato non dichiara preset DRX. Non è quindi una
  capability validata dal gate.
- La prima ricostruzione visuale ha rivelato che il vecchio helper asset dichiarava riuscito un
  append senza creare la traccia richiesta né verificare il range restituito. L'helper ora crea V2
  quando manca, richiede un solo `TimelineItem` di ritorno e confronta `GetStart`/`GetEnd` col range
  richiesto. Se append o read-back falliscono, elimina gli item restituiti e le sole tracce appena
  create; un rollback incompleto richiede esplicitamente verifica manuale. Il wrapper pubblico
  mantiene il lock Resolve per l'intera operazione e ogni `AddTrack` deve incrementare il count
  esattamente di uno. Otto test di
  regressione coprono traccia mancante, creazione parziale delle tracce, range discordante e append
  senza item.
- Resolve 21.1.1 applica ai PNG la preferenza locale di durata still (150 frame) anche se il payload
  chiede una durata sorgente diversa. Il gate usa quindi due intervalli verificati da 150 frame e
  fallisce esplicitamente se il read-back non coincide, invece di dichiarare un range non ottenuto.
- La timeline finale `ARPHE_COLORIST_VISUAL_REVIEW_20261024_145724` contiene due clip su V2,
  durata complessiva 300 frame. Il job `colorist_ea377703fe404a78` ha creato
  `ARPHE_COLOR_EA377703FE404A78_01` e `_02`, applicando il CDL al riferimento e `CopyGrades` al
  secondo clip. Il progetto disposable è stato salvato esplicitamente.
- Il confronto UI ha mostrato entrambe le versioni sul viewer; la pagina Color ha mostrato un nodo
  attivo e RGB parade differenti. La versione `after` riduce esposizione e saturazione, raffredda il
  cast caldo e mantiene le patch leggibili. Questa è evidenza tecnica/visiva del funzionamento, non
  un'accettazione estetica a nome dell'utente.
- Il catalogo tool della chat già aperta era stato memorizzato prima del rollout. I nuovi entrypoint
  sono stati verificati contro il modulo installato e i flag tramite il connettore, ma la loro
  esposizione pubblica deve essere ricontrollata da una nuova sessione app.
- La review del job resta `APPLIED` con `review_accepted=null`: viewer e scopes sono stati
  controllati, ma l'utente deve ancora accettare o rifiutare il look prima di calibrare le
  approssimazioni di temperatura, tinta e contrasto per la produzione.
- Chiusura verificata: `CAP_COLORIST=false`; progetto
  `ARPHE_PEELING_ADV_TEST_20261023` e timeline
  `__ARPHE_VERTICAL_VERTICAL_9957F4FFC8BC43E0B5B333FF4B4BFC03` ripristinati. Il progetto gate
  e gli asset sintetici sono stati conservati come evidenza e non sono stati cancellati.
- Lo script gate rifiuta una config che non dichiari `PC_PERSONALE`; l'azione `finish` disattiva e
  rilegge `CAP_COLORIST=false` in un blocco `finally`, anche se il ripristino di preview/progetto
  fallisce. Non opera su `PC_SEGRETERIA`.

Verifica finale del follow-up: suite Creative `570` test superati e `3` skip legati a privilegi
Windows per symlink; suite runtime Windows `58` test superati e `1` skip DPAPI nel token di test.
I controlli di catalogo sono inclusi nella suite Creative e gli otto test helper asset sono verdi. La
venv isolata usa le dipendenze dichiarate dal bridge.

Il gate tecnico sopra non sostituisce la revisione visiva. Anche un job rimasto `APPLYING` dopo un
errore di persistenza richiede ispezione e recupero umano: non viene rieseguito automaticamente.

