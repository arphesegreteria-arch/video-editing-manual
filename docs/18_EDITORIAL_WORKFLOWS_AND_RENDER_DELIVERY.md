# 18 — Workflow editoriali e consegna render

Stato codice: implementato e verificato automaticamente. Rollout e prove Resolve reali:
`PENDING` separatamente su `PC_PERSONALE` e `PC_SEGRETERIA`.

## Scelta della linea

ChatGPT propone la linea più probabile e chiede una conferma breve. Se la richiesta è ambigua:

1. `ARPHE_PODCAST_REELS_CTA` — estratti 16:9/source-native con CTA;
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

- Podcast ARPHÈ: risoluzione e FPS della sorgente primaria; MP4/H.264 High/AAC 48 kHz.
- Verticale: progetto, timeline, playback e render 1080×1920/30; master ProRes 422 HQ e derivato
  H.264 separati.
- Carabellese: 1920×1080, FPS esatto della sorgente, MP4/H.264 High/AAC 48 kHz.
- Longform: risoluzione e FPS dichiarati nel brief; review render, master e pubblicabile separati.

In ogni linea `playback FPS = project FPS = timeline FPS`. “Review render” indica un file;
“playback FPS” indica la riproduzione in Resolve. Sorgenti con FPS differenti richiedono la
conferma della sorgente/frequenza primaria.

In Resolve Studio 21.1.1 `timelinePlaybackFrameRate` è leggibile ma non scrivibile tramite la
API di scripting. Il bridge non tenta quindi di forzarla. Se il valore non coincide con il
contratto, la chat mostra il flag `PLAYBACK_FPS_ACTION_REQUIRED`, il valore trovato, quello
richiesto e l'istruzione `Project Settings > Master Settings`. Fino al read-back conforme non
vengono create né timeline, né directory di staging, né job render.

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

### PC_PERSONALE — BLOCKED (playback FPS)

- [x] identità, task e percorsi del profilo verificati (`PC_PERSONALE`);
- [ ] read-back formato e playback FPS: rilevati timeline/progetto 30 FPS ma playback 24 FPS;
- [ ] job innocuo preesistente lasciato intatto;
- [ ] prepare senza start;
- [ ] approvazione e avvio selettivo;
- [ ] verifica media e promozione;
- [ ] prova recovery/rollback circoscritta.

Evidenza 2026-10-07: il primo rollout Creative03 è stato interrotto sul progetto disposable
`ARPHE_ROLLOUT_PC_PERSONALE_20261007` prima del gate render e riportato temporaneamente a
SafeWrite02. Dopo la correzione, Creative03 è stato reinstallato sul solo `PC_PERSONALE`: task
`Running`, `/readyz=ready` e codice installato identico al commit verificato. Una chiamata reale
del tool pubblico sul nuovo progetto disposable `ARPHE_ROLLOUT_PLAYBACK_FLAG_PROJECT_20261007`
ha restituito `PLAYBACK_FPS_ACTION_REQUIRED` (attuale 24, richiesto 30) senza creare la timeline.
Il gate render riparte dopo la modifica manuale del playback FPS e un nuovo read-back. Nessun
test è stato eseguito sul progetto di lavoro della segreteria.

### PC_SEGRETERIA — PENDING

- [ ] identità e percorsi del profilo;
- [ ] read-back formato e playback FPS;
- [ ] job innocuo preesistente lasciato intatto;
- [ ] prepare senza start;
- [ ] approvazione e avvio selettivo;
- [ ] verifica media e promozione;
- [ ] prova recovery/rollback circoscritta.

Il lavoro attualmente in sospeso sul PC segreteria non deve essere usato per questi gate.
