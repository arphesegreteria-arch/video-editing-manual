# 18 — Workflow editoriali e consegna render

Stato codice: implementato e verificato automaticamente. Rollout e prove Resolve reali:
`PASS` su `PC_PERSONALE`; `PENDING` separatamente su `PC_SEGRETERIA`.

## Scelta della linea

ChatGPT propone la linea più probabile e chiede una conferma breve. Se la richiesta è ambigua:

1. `ARPHE_PODCAST_REELS_CTA` — estratti source-native a 30 fps con CTA;
2. `ARPHE_VERTICAL_SOCIAL` — recensioni, short o ADV 1080×1920/30;
3. `CARABELLESE_YOUTUBE_CLEANUP` — pulizia pause 1920×1080, FPS sorgente;
4. `ARPHE_LONGFORM_EDITORIAL` — montaggio editoriale completo, guidato dall'editor.

Il bridge non indovina la linea. Prima della prima scrittura il brief deve avere un
`workflow_id` esplicito. Nuove linee si aggiungono al registry, non copiando il motore.

## Nove domande comuni

1. Quale risultato serve?
2. Quali sorgenti o timeline sono incluse?
3. Video completo, estratti o entrambi?
4. Quanto può essere incisivo il montaggio?
5. Cosa va sempre conservato?
6. Servono CTA, caption o grafiche?
7. Quale materiale richiede approvazione?
8. Serve un review render, un master o un file pubblicabile?
9. Chi approva montaggio e render?

La segreteria vede domande semplici. Varianti tecniche, conversioni e recovery sono riservati a
`TECNICO` o `ALESSIO`. Le recensioni devono essere reali e approvate, rese anonime; non si
inventano testi o risultati clinici.

## Contratti di formato

- Podcast ARPHÈ: risoluzione della sorgente primaria, progetto/timeline/playback fissi a 30 fps;
  MP4/H.264 High/AAC 48 kHz.
- Verticale: progetto, timeline, playback e render 1080×1920/30; master ProRes 422 HQ e derivato
  H.264 separati.
- Carabellese: 1920×1080, FPS esatto della sorgente, MP4/H.264 High/AAC 48 kHz.
- Longform: risoluzione e FPS dichiarati nel brief; review render, master e pubblicabile separati.

In ogni linea `playback FPS = project FPS = timeline FPS`. Per Podcast ARPHÈ il valore è sempre
30, anche quando il file sorgente ha un altro rate: Resolve effettua il conform sulla timeline.
“Review render” indica un file;
“playback FPS” indica la riproduzione in Resolve. Sorgenti con FPS differenti richiedono la
conferma della sorgente/frequenza primaria.

In Resolve Studio 21.1.1 `timelinePlaybackFrameRate` è leggibile ma non scrivibile tramite la
API di scripting. Il bridge non tenta quindi di forzarla. Se il valore non coincide con il
contratto, la chat mostra il flag `PLAYBACK_FPS_ACTION_REQUIRED`, il valore trovato, quello
richiesto e l'istruzione `Project Settings > Master Settings`. Fino al read-back conforme non
vengono create né timeline, né directory di staging, né job render.

Impostare manualmente una volta il default di DaVinci in `Project Settings > Master Settings`:
`Timeline frame rate = 30` e `Playback frame rate = 30`, quindi salvare il preset/default prima
di creare altre timeline. Il bridge ripete il read-back a ogni preparazione e applicazione del
workflow; non considera valido un gate 24/24 anche se internamente coerente.

## Sequenza render obbligatoria

1. `validate_editorial_brief` registra il brief e segnala domande irrisolte.
2. `prepare_render_batch` crea esclusivamente nuovi job sotto `staging/<batch_id>`; non avvia.
3. L'operatore controlla riepilogo, nomi, formato, audio e destinazione.
4. `approve_render_batch` lega l'approvazione all'impronta del manifest.
5. `start_render_batch` verifica nuovamente la coda e avvia soltanto gli ID del batch.
6. `get_render_batch_status` controlla i job posseduti.
7. `verify_render_batch` verifica media e promuove i file conformi nella consegna.

Ogni job già presente prima della preparazione resta intatto. Un'aggiunta, rimozione o modifica
della coda dopo l'approvazione rende il batch obsoleto. Non esiste fallback “avvia tutta la coda”.
`render_preview` e `start_longform_exports` sono risposte di migrazione e non avviano più nulla.

## Errori e rollback

- `FAILED_PREPARE`: eliminare soltanto gli ID dimostrati nuovi; job orfani richiedono recovery
  tecnico. Non svuotare mai l'intera coda.
- `FAILED_RENDER`: conservare manifest, staging e job per diagnosi; un retry crea un nuovo attempt.
- `FAILED_VERIFY`: conservare il file in staging; non copiarlo nella consegna.
- `CANCELLED`: prima del render si eliminano soltanto i job del batch; durante il render si ferma
  solo con lock posseduto dal bridge.

Un riavvio rilegge batch e lock dal registry. Non ricrea automaticamente i job.

## Gate live per workstation

Usare un progetto/timeline di prova e un job innocuo creato appositamente; non usare lavori reali.

### PC_PERSONALE — PASS (2026-10-07)

- [x] identità, task e percorsi del profilo verificati (`PC_PERSONALE`);
- [x] read-back progetto/timeline/playback 1080×1920/30 dopo correzione UI sul progetto disposable;
- [x] job innocuo preesistente lasciato intatto durante l'avvio selettivo;
- [x] prepare senza start;
- [x] approvazione `ALESSIO` e avvio selettivo;
- [x] verifica media e promozione;
- [x] prova recovery/rollback circoscritta.

Evidenza 2026-10-07: il primo rollout Creative03 è stato interrotto sul progetto disposable
`ARPHE_ROLLOUT_PC_PERSONALE_20261007` prima del gate render e riportato temporaneamente a
SafeWrite02. Dopo la correzione, Creative03 è stato reinstallato sul solo `PC_PERSONALE`: task
`Running`, `/readyz=ready` e codice installato identico al commit verificato. Una chiamata reale
del tool pubblico sul nuovo progetto disposable `ARPHE_ROLLOUT_PLAYBACK_FLAG_PROJECT_20261007`
ha restituito `PLAYBACK_FPS_ACTION_REQUIRED` (attuale 24, richiesto 30) senza creare la timeline.
Il playback è stato poi impostato a 30 tramite Project Settings da controllo remoto; il retry ha
creato la timeline disposable con read-back conforme. Durante il passaggio al render è stato
individuato e corretto l'installer che ometteva i registri workflow/render. Nessun test è stato
eseguito sul progetto di lavoro della segreteria. Il gate ha inoltre confermato che
`GetRenderJobList()` non espone `JobStatus` in Resolve 21.1.1: lo stato viene ora letto con
`GetRenderJobStatus(job_id)`.

Il batch selettivo `2f97060e-f34b-44ba-95ff-68867eea6299` è stato approvato, avviato e completato
senza avviare il batch preesistente. Il file tecnico
`ARPHE_ROLLOUT_SELECTIVE_JOB_20261007.mp4` è stato verificato (MP4/H.264 High, 1080×1920,
30 fps, durata 10,005 s, AAC 48 kHz) e promosso in `renders/creative/publishable/`. La prova di
recovery ha annullato il solo batch preesistente `9ee8ebe1-0fc3-4646-b6b1-7112bad66359` e rimosso
soltanto il relativo job. Controllo finale: task `Running`, `/readyz=ready`, Creative03 attivo e
workstation `PC_PERSONALE`. Il file è un artefatto tecnico marcato **NON PUBBLICARE**.
`PC_SEGRETERIA`, il suo runtime e il suo progetto di lavoro non sono stati toccati.

### PC_SEGRETERIA — PENDING

- [ ] identità e percorsi del profilo;
- [ ] read-back formato e playback FPS;
- [ ] job innocuo preesistente lasciato intatto;
- [ ] prepare senza start;
- [ ] approvazione e avvio selettivo;
- [ ] verifica media e promozione;
- [ ] prova recovery/rollback circoscritta.

Il lavoro attualmente in sospeso sul PC segreteria non deve essere usato per questi gate.

## Gate separato per la selezione editoriale podcast

`CAP_EDITORIAL_SELECTION` è indipendente dal render e parte `false`. Le letture di contratto,
job e metriche restano disponibili; marker, review, tagli, cleanup e profili richiedono il gate.
L'installer conserva il valore locale e i quattro file di stato della workstation senza copiarli
fra personale e segreteria. Il ledger `validation/editorial-selection-ledger.json` richiede prove
separate per marker, review, cut, resume, durata, cleanup e rollback: una macchina non può validare
l'altra.

### Selezione editoriale — PC_PERSONALE PASS (2026-10-09)

La copia installata ha creato un nuovo progetto direttamente a 30/30 e ha superato marker a
coppie, review completa con approvazione/modifica/rifiuto, due tagli verificati, limite durata,
failure controllata e resume senza duplicati, cleanup con marker estraneo preservato e rollback
zero-write. Il progetto e i file sintetici sono stati rimossi; il progetto originale è rimasto
aperto e `CAP_EDITORIAL_SELECTION=false` al termine.

`PC_SEGRETERIA` resta `PENDING`: non è stata installata, abilitata o usata per questo gate.

## Gate separato per la pulizia YouTube Studio Carabellese

## Vertical Social Assistant — pianificazione sicura

`ARPHE_VERTICAL_SOCIAL` usa una card unica: richiesta libera → piano versionato → approvazione
legata all'impronta → timeline provvisoria → autocontrollo → review umana. Le azioni sono
semantiche e chiuse; richieste non supportate restano bloccate con un motivo, senza accesso
arbitrario a Resolve. Caption e sottotitoli restano post-picture-lock e non vengono applicati
finché non esiste un picture lock con impronta della timeline. Il contratto v5 separa `B_ROLL_PROVIDED` da
`B_ROLL_GENERATED`: il primo usa soltanto file espliciti e allowlistati, il secondo resta bloccato
finché non viene scelto e validato un provider generativo.

Il flag `CAP_VERTICAL_SOCIAL` parte sempre `false`. Job, journal e prove restano locali alla
workstation. Il ledger `validation/vertical-social-ledger.json` conserva gate indipendenti:
`PC_PERSONALE=PENDING` e `PC_SEGRETERIA=PENDING` finché ciascun PC non supera la propria prova.
Sul personale i sottogate nativi CUT, REFRAME, B-roll fornito, MUSIC_DUCK, GRAPHIC/CTA e CAPTIONS
sono PASS; questo non abilita né modifica Segreteria.

Grafiche e CTA sono opzionali: assenza nel piano significa zero scritture. Se richieste, il piano
deve indicare range, testo, motivo e ruolo colore canonico del Graphic Kit. Il tool
`apply_vertical_social_action` esegue REFRAME, `B_ROLL_PROVIDED`, MUSIC_DUCK, GRAPHIC, CTA e
CAPTIONS soltanto sulla timeline provvisoria posseduta dal piano, registra il read-back e
ripristina sempre la timeline sorgente. CAPTIONS accetta nel piano il placeholder
`AT_PICTURE_LOCK`: al lock il bridge calcola e conserva l'impronta reale della timeline; se il
montaggio cambia prima dei sottotitoli, l'esecuzione si blocca senza scrivere.

La segreteria deve ascoltare i marker e rispondere una volta sola, senza spostarli. Alessio o
personale qualificato gestiscono failure, restore, overlay di apprendimento e soglie tecniche. Il
ledger `validation/carabellese-cleanup-ledger.json` parte con `PC_PERSONALE=PENDING` e
`PC_SEGRETERIA=PENDING`: prove automatiche o di un PC non promuovono l'altro. L'installer conserva
flag, job, journal, overlay, proposte e checkpoint locali senza copiarli tra workstation.
# Branded longform editorial

`BRANDED_LONGFORM_EDITORIAL` is the shared longform engine. It must always select one explicit
profile:

- `ARPHE_LONGFORM_EDITORIAL`: Graphic Kit ARPHE ready;
- `CARABELLESE_LONGFORM_EDITORIAL`: `kit_status=PENDING`, therefore cleanup, multicamera,
  transcript, markers and proposals are allowed, while every graphic write is blocked.

The original timeline is never modified. The bridge creates `<original>_CLEANUP`, adds the
proposal markers there, accepts one fingerprint-bound batch decision and creates
`<original>_EDITORIAL` only after approval. ARPHE graphic proposals use the installed Fusion
carrier and verify their exact range and Text+ read-back. A retry of an already applied job returns
the registered operations rather than duplicating overlays.

When high-confidence cleanup events are supplied for a single synchronized A/V source, the bridge
rebuilds `_CLEANUP` from the kept ranges and never edits the original. Multicam or complex timelines
are deliberately rejected from automatic cutting and returned for review until native sync/camera
selection is available.

OBS multicamera input uses `PROGRAM` as the only final audio. `CAM_A`, `CAM_B`, and later cameras
may carry guide audio solely for synchronization. Missing guide audio or mismatched frame rates
produce review-required status rather than a claimed sync.
Call `inspect_branded_longform_sources` first and pass its SHA-256 `source_fingerprint` to cleanup;
the bridge also binds the original timeline structure so a later source edit invalidates the job.

Normal secretary interaction is one compact card. A valid response can say, for example,
`approva P001 e P003; rifiuta P002; modifica P004: usa solo la parola fiducia`. The operator must
not send Resolve commands: ChatGPT converts this answer into the typed batch. Final human review
remains mandatory.

The capability is `CAP_BRANDED_LONGFORM_EDITORIAL`, default `false`. Native validation is allowed
only on PC_PERSONALE inside a disposable project named
`ARPHE_BRANDED_LONGFORM_NATIVE_GATE_*`. PC_SEGRETERIA requires a later independent rollout.

On 2026-10-10 the PC_PERSONALE native gate passed cleanup/editorial duplication, marker insertion,
one exact-range ARPHE Fusion graphic and complete rollback. This validates the implementation on
that workstation only; it does not enable the capability and does not validate PC_SEGRETERIA.
