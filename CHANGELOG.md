# CHANGELOG

## 2026-10-10 — Workflow Control Plane (prima tranche, non attiva)

- Aggiunti registro locale atomico, fingerprint di approvazione e card unica di controllo
  workstation/Resolve, con FPS timeline e playback distinti.
- Aggiunto `CAP_WORKFLOW_CONTROL_PLANE=false` per default: le scritture vengono rifiutate prima
  del runtime quando il flag è spento.
- Aggiunti test per isolamento workstation, fingerprint, idempotenza e controllo offline; suite
  Creative `467 PASS / 1 SKIP`.
- Questa tranche non installa, abilita o valida `PC_PERSONALE` o `PC_SEGRETERIA`; non tocca progetti
  Resolve aperti, Python o tunnel. Il binding esecutivo completo ai quattro workflow resta pending.

## 2026-10-09 — Workflow Studio Carabellese YouTube cleanup

- Aggiunto il flusso isolato trascrizione → proposte/marker → review con motivi → checkpoint DRT →
  applicazione verificata → recovery/chiusura, mantenendo una sola timeline canonica.
- La v1 esegue soltanto pulizia editoriale: niente CTA, Graphic Kit, grafiche o render.
- Aggiunti journal riprendibile, restore vincolato a fingerprint, marker di proprietà, apprendimento
  redatto e strumenti pubblici chiusi con una sola card per la segreteria.
- Installer e flag preservano stato e valore locali e rifiutano file di un'altra workstation;
  `CAP_CARABELLESE_CLEANUP=false` per default.
- Gate nativo `PC_PERSONALE`: PASS su media e progetto sintetici. Verificati review, checkpoint,
  failure/ripresa, timeline unica, marker estranei, pulizia e rollback del flag.
- Il gate ha corretto quattro differenze dell'API reale: wrapper Python non stabili, nome e playback
  ereditato nell'import DRT, `endFrame` esclusivo e salvataggio recuperabile dopo verifica finale.
- La review finale ha unificato il binding A/V anche nel wrapper pubblico, reso completo il rollback
  se la promozione DRT si interrompe e reso idempotente il doppio invio di review/recovery.
- Runtime personale riallineato: 62 hash uguali, task `Running`, `/readyz=ready`, restart count 0,
  progetto originario ripristinato, artefatti sintetici rimossi e flag finale `false`.
  `PC_SEGRETERIA=PENDING` e non toccato.

## 2026-10-09 — Chiusura gate personale e hardening del preflight

- Il gate live definitivo `PC_PERSONALE` resta PASS a progetto, timeline e playback 30 fps;
  `CAP_EDITORIAL_SELECTION` è tornata `false` dopo il rollback.
- La review finale ha trovato e corretto una scrittura prematura: un job `BLOCKED` che fallisce
  fingerprint o controllo FPS ora resta byte-invariato. Aggiunto il test di regressione.
- Suite rieseguite: bridge `282 PASS / 1 SKIP`, Windows `55 PASS / 1 SKIP`; validatore editoriale,
  compilazione e `git diff --check` PASS.
- Riallineato soltanto il runtime `PC_PERSONALE`: task `Running`, supervisore e tunnel vivi,
  `/readyz=ready`, hash installato uguale alla repository e capability disabilitata. Il vecchio
  file di stato diagnostico è stato conservato come backup recuperabile. `PC_SEGRETERIA` non è
  stato toccato e resta `PENDING`.

## 2026-10-08 — Selezione editoriale Reel podcast, ripresa e apprendimento locale

- Aggiunto il flusso chiuso proposta → marker → review completa → tagli verificati → cleanup.
- Limite assoluto 180 secondi CTA inclusa, formato sorgente esplicito, playback uguale agli FPS
  progetto, audio derivato accettato soltanto con manifest legato alla sorgente.
- Job e tagli sono riprendibili; collisioni e output modificati bloccano senza adozione implicita.
- Motivi e dettagli restano nel journal locale. Solo aggregati redatti possono diventare una
  proposta, previa approvazione di Alessio e digest del profilo precedente.
- Stato e flag sono separati per workstation; `CAP_EDITORIAL_SELECTION=false` per default.
  `PC_PERSONALE=PENDING`, `PC_SEGRETERIA=PENDING`; nessun test live è dichiarato.
- Chiarito il contratto ARPHÈ Podcast Reels: risoluzione source-native, ma progetto, timeline e
  playback obbligatori a 30 fps. Il bridge non scrive il playback read-only di Resolve: con 24
  restituisce `PLAYBACK_FPS_ACTION_REQUIRED` prima di marker o tagli.
- Il gate personale 24/24 ha validato il meccanismo tecnico ma non è promosso a prova produttiva;
  il PASS resta in attesa del default DaVinci 30/30 impostato manualmente e del nuovo gate.
- Gate definitivo `PC_PERSONALE` 30/30: **PASS** sulla copia installata. Verificati nuovo default,
  marker, review completa, tagli, limite durata, failure/ripresa senza duplicati, cleanup e rollback
  zero-write. Artefatti sintetici rimossi, progetto originale preservato, flag finale `false`.
  `PC_SEGRETERIA` resta `PENDING` e non toccato.

## 2026-10-08 — Leggibilità misurabile per Reel recensioni

- Il Graphic Kit definisce il contratto canonico per safe area, size, righe, velocità di lettura
  e ruoli font; il bridge video lo include con commit e digest verificabili.
- La regola operativa è una card unica quando possibile, quattro parole/secondo più un secondo,
  minimo 3 e standard massimo 12 secondi. Split solo verbatim e previa approvazione.
- Aggiunti ispezione read-only, approvazioni legate all'impronta e blocco zero-write per font,
  overflow, formato/FPS, contratto, gate o approvazione non validi.
- `CAP_READABILITY_GUARD=false` per default su entrambi i PC; upgrade e installer preservano
  identità e valore esplicito senza copiare stato tra workstation.
- Evidenza automatica: Creative `207/207 PASS` (1 skip symlink ambientale), Windows `52/52 PASS`
  (1 skip DPAPI). Installazione, contratto e font finali sono PASS su `PC_PERSONALE`;
  `PC_SEGRETERIA` non è stato toccato.
- La revisione integrale ha aggiunto il check Noto Serif 300 nel template, legato le approvazioni
  alla workstation, impedito che intro/CTA comprimano le card e chiuso i write Review legacy.
  Corretto anche il falso negativo GDI per i pesi Windows esposti come famiglie `Light`/`Medium`.
- Gate live `PC_PERSONALE`: **PASS**. Il primo tentativo ha isolato un alias Noto non riconosciuto
  da Fusion e una diagnostica diretta non supportata che ha causato un crash di Resolve. La font
  Light è stata rigenerata dalla sorgente OFL del Graphic Kit con famiglia/stile canonici, la copia
  precedente è stata salvata in backup e Resolve è stato riavviato. Il rerun ha prodotto sette
  catture leggibili 1080x1920 — intro, card corta, due casi limite, due metà dello split verbatim e
  CTA — senza overflow, con progetto/timeline/playback a 30 fps e senza nuovi errori font nel log.
- Rollback live PASS: a guardia spenta l'ispezione resta disponibile, 5/5 write Review pubbliche
  sono bloccate e snapshot Resolve/stato rimane identico. È stata poi riattivata soltanto
  `CAP_READABILITY_GUARD` su `PC_PERSONALE`; task `Running` e `/readyz=ready`. La timeline e le
  catture sono conservate. Il controllo visuale non comprende un upload nell'app social su un
  telefono reale. `PC_SEGRETERIA` resta `PENDING` e non toccato.

## 2026-10-08 — Ritiro Resolve archive-first e recovery senza overwrite

- Aggiunti prepare, approvazione tecnica, execute idempotente, inspection e recovery per timeline
  e progetti ARPHÈ.
- Ogni proposta salva ed esporta un `.drp` verificato con SHA-256 prima di qualunque rimozione;
  modifiche successive al progetto o all'archivio bloccano l'execute.
- Timeline corrente e progetti con render lock sono protetti; `DeleteProject` avviene solo dopo
  `CloseProject` e verifica API. Un crash in `EXECUTING` viene riconciliato senza doppio delete.
- Recovery via import in un nuovo `ARPHE_RECOVERY_...`, senza overwrite. Gli archivi restano tutti
  per 30 giorni e comunque gli ultimi 3 per progetto; nessuna cancellazione automatica.
- Nuovo gate e registry per-workstation `CAP_RESOLVE_RETIREMENT=false` di default. Un config o
  registry dell'altro PC blocca l'installer prima delle scritture.
- Suite finale: Creative `166 PASS / 1 SKIP`; Windows `48 PASS / 1 SKIP`.
- Rollout `PC_PERSONALE` PASS: timeline disposable ritirata, progetto ritirato, recovery importato
  senza overwrite e recovery disposable ritirato. Tre archivi registrati preservati, nessun probe
  rimasto in Resolve, progetto originario ripristinato e runtime `ready`.
- Resolve 21.1.1 non valorizza `GetProjectLastModifiedTime`; aggiunto fallback verificato a
  `GetProjectAttributesInCurrentFolder().lastModifiedDate`. Il nome recovery conserva sempre gli
  8 caratteri del suffisso UUID anche con nomi originali lunghi.
- Rimosso soltanto il `.drp` orfano non registrato del primo prepare fallito (22.738 byte,
  non recuperabile); tutti gli archivi registrati sono rimasti intatti. `PC_SEGRETERIA` non toccato.

## 2026-10-08 — Quarantena tecnica recuperabile e runtime separati

- Aggiunti registry artefatti per workstation, policy di retention fissa, inventario read-only,
  quarantena di 7 giorni, restore con collision check e purge verificato con hash.
- Catture diagnostiche e staging render vengono registrati; output pubblicabili, sorgenti e
  oggetti Resolve restano fuori dal perimetro.
- I log ruotati non si sovrascrivono più: ogni unità ha directory, sidecar, hash e identità PC.
- Rimossi i tool pubblici di cleanup generico; i nuovi tool non accettano percorsi arbitrari.
- Corretto l'installer profilo: log, config e registry sono workstation-specifici; il gate nuovo
  resta spento per default e un registry dell'altro PC blocca prima delle scritture.
- Evidenza codice: Creative `153 PASS / 1 SKIP` symlink ambientale; Windows
  `45 PASS / 1 SKIP` DPAPI ambientale.
- Rollout `PC_PERSONALE`: runtime `Running` e `/readyz` PASS; gate attivo; manutenzione esplicita
  PASS con zero quarantene/purge. I 68 file storici (~37 MB) restano `UNCLASSIFIED` e intatti.
  Registrata una sonda disposable reale, `ACTIVE` per le prime 24 ore; i gate temporali di
  quarantena/restore e purge restano PENDING senza retrodatazioni. `PC_SEGRETERIA` non toccato.
- Rollback: spegnere `CAP_ARTIFACT_MAINTENANCE`; l'ispezione resta disponibile e gli elementi già
  in quarantena non vengono eliminati finché il gate resta spento.

## 2026-10-07 — Stato render letto dall'API dedicata

- `get_render_batch_status` e la verifica finale usano `Project.GetRenderJobStatus(job_id)`;
  Resolve 21.1.1 omette `JobStatus` da `GetRenderJobList()` anche per job completati.
- Resta un fallback alla coda per compatibilità, ma `unknown` non viene accettato come completato.
- Suite: Creative `116/116` PASS; Windows `36` PASS e `1` SKIP DPAPI noto.
- Gate reale `PC_PERSONALE`: **PASS**. Il secondo job è stato avviato selettivamente, verificato
  (MP4/H.264 High, 1080×1920, 30 fps, AAC 48 kHz) e promosso in `publishable`; il job
  preesistente è rimasto fermo durante il render ed è stato poi annullato e rimosso da solo nella
  prova di rollback. Runtime finale `ready`, Creative03 attivo. `PC_SEGRETERIA` non toccato.

## 2026-10-07 — Registri runtime inclusi nel rollout Creative03

- L'installer Creative03 copia ora anche `editorial_workflows.json` e `render_profiles.json`;
  prima del fix il codice veniva installato senza i registri necessari ai render batch.
- Aggiunto test di installazione reale in directory temporanea.
- Suite: Creative `115/115` PASS; Windows `36` PASS e `1` SKIP DPAPI noto.
- `PC_PERSONALE`: playback del progetto disposable impostato via UI a 30 FPS; read-back e
  creazione timeline 1080×1920/30 completati. `PC_SEGRETERIA` non toccato.

## 2026-10-07 — Gate playback FPS visibile in chat

- Corretto il contratto formato per Resolve Studio 21.1.1: `timelinePlaybackFrameRate` è trattato
  come read-only e non viene più inviato a `Project.SetSetting`.
- Se il playback FPS non coincide con il workflow, la chat riceve
  `PLAYBACK_FPS_ACTION_REQUIRED` con valore attuale, valore richiesto e percorso dell'impostazione.
- Il mismatch blocca prima della creazione timeline e prima di staging/coda render, senza cambiare
  lo stato del batch.
- Suite: Creative `115/115` PASS; Windows `35` PASS e `1` SKIP DPAPI noto.
- `PC_PERSONALE`: Creative03 reinstallato e `ready`; chiamata reale del tool pubblico bloccata
  correttamente sul playback a 24 FPS del progetto disposable, con timeline non creata e flag
  24→30 completo. `PC_SEGRETERIA` non toccato.

## 2026-10-07 — Workflow editoriali e render batch sicuri

- Aggiunti quattro workflow versionati e profili review/master/pubblicabile.
- Resi espliciti risoluzione, project/timeline FPS e playback FPS con read-back prima dell'editing.
- Introdotti manifest persistenti, approvazione legata all'impronta e lock per progetto.
- La preparazione non avvia render; l'avvio usa solo gli ID nuovi approvati e rifiuta code mutate.
- Gli output restano in staging finché contenitore, codec, dimensioni, FPS, durata e audio non
  superano la verifica PyAV.
- I vecchi entry point pubblici non avviano più render immediati.
- Suite finali: Creative `112/112` PASS; Windows `35` PASS e `1` SKIP DPAPI noto. Gate reali di
  entrambe le workstation ancora `PENDING`; nessun lavoro Resolve esistente è stato toccato.

## 2026-10-07 — Isolamento completo dei percorsi workstation (codice)

- Config Creative, stato, audit, runtime e backup sono risolti dal profilo esplicito
  `PC_PERSONALE` o `PC_SEGRETERIA`.
- Lo switch non contiene più fallback `py -3`: usa solo comandi assoluti registrati e verifica
  sia l'interprete sia l'entry point prima del riavvio.
- Il rollback `SafeWrite02` e il bridge `Creative03` sono entrambi registrati nella configurazione
  generata dall'installer; il preflight rifiuta un rollback dichiarato ma non installato.
- Switch, backup, stato e modifica feature flag ricevono il profilo locale esplicito e risolvono
  la config runtime sotto `<install_root>\runtime-configs\<WORKSTATION_ID>`, senza ricadere nella
  copia storica sotto `AppData`.
- `set_feature_flag.ps1` e `backup_arphe.ps1` richiedono l'identità workstation e non leggono più
  la configurazione condivisa legacy.
- Una config Creative legacy viene copiata nel percorso del profilo soltanto se dichiara la
  stessa workstation; stato e audit esistenti vengono copiati senza eliminare gli originali.
  Una config appartenente all'altro PC blocca l'installazione prima delle scritture.
- Validazione automatica dopo integrazione di `origin/main`: suite Creative `67/67` PASS; suite
  Windows `35` PASS e
  `1` SKIP DPAPI perché il token sandbox non dispone del profilo CurrentUser.
- Stato workstation reale: **NON ANCORA VALIDATO**. Nessun installer, task, tunnel o Resolve dei
  due PC è stato modificato da questo cambiamento; READ/SAFE WRITE vanno ripetuti per PC dopo il
  rollout esplicito.
## 2026-10-02 — E10 Reel V2, confini umani e audio naturale

- Ricostruito il piano E10 in sei Reel usando frasi di ingresso/uscita indicate dall'operatore e
  timestamp parola-per-parola; durata complessiva ridotta da 18.818 a 10.534 frame.
- Aggiunto `ARPHE_DIALOGUE_NATURAL_V4`, preset conservativo ispirato al flusso Fairlight per
  sorgenti già intelligibili che con `LEVEL_V2` risultano metalliche o gracchianti.
- Documentate otto regole editoriali candidate: una tesi per Reel, tre minuti come limite e non
  target, conferme brevi preservate, frasi umane autorevoli, sensibilità contestuale e doppio gate.
- Aggiunto `ARPHE_CTA_FADE`: dissolvenza CTA di sola opacità, campionata frame per frame e mantenuta
  fino alla fine per evitare movimenti o scomparsa tardiva dei testi in Fusion.
- Versionato il piano in `plans/ARPHE_E10_MEDICINA_ESTETICA_REELS_V2.json`.

## 2026-10-02 — Caption Engine mobile e render verticale

- Verificata `CreateSubtitlesFromAudio` in Resolve Studio dopo apertura esplicita della pagina Edit.
- Documentato il limite della API pubblica per Track Style/Inspector e la mancata modifica testo
  tramite `TimelineItem.SetName`.
- Verificato un fallback non-PNG con una composition Fusion, 12 Text+, Merge temporizzati tramite
  espressioni Blend e Background trasparente.
- Definito il preset mobile osservato: Satoshi Bold, bianco su bordeaux `#680C09`, size `0.050`.
- Aggiunta una safe area 9:16: fascia bassa 68–82% come default, fascia alta 8–20% come fallback,
  almeno 15% libero in basso e divieto assoluto di sovrapposizione ai volti.
- Completato e controllato il render MP4/H.264 1080×1920/30, inclusi i gap senza caption.
- Aggiunto `docs/16_CAPTION_ENGINE_AND_MOBILE_SUBTITLES.md`; capability caption marcata `PARTIAL`
  e render esterno `SUPPORTED`.

## 2026-09-25 — Standard Instagram recensioni ARPHÈ

- Corretto il preset di consegna Reel: il bridge esporta un master QuickTime ProRes 422 HQ
  1080×1920/30 con audio incluso. È stato introdotto dopo aver rilevato che la prima esportazione
  manuale V3 era a circa 2,5 Mb/s e appariva degradata sul telefono. Le chiavi dirette H.264
  `DataRate` e `VideoQuality` sono state provate e, rispettivamente, ignorata e rifiutata dalla
  build, quindi non vengono usate per fingere un bitrate che non sarebbe effettivo.
- Verificato l'export reale `ARPHE_E09_REELS_MIODOTTORE_V7_MASTER.mov`: 1080×1920/30,
  27 secondi, circa 104 MB e 30,5 Mb/s. Le prove MP4 V4/V6 (~0,8 Mb/s) restano diagnostiche e
  non costituiscono consegne.
- Aggiunta e verificata la copia compatibile `ARPHE_E09_REELS_MIODOTTORE_V8_INSTAGRAM.mp4`,
  ottenuta dal master ProRes con H.264 High/CRF 17. Il confronto frame-per-frame con il master
  restituisce SSIM 0,9979 e PSNR 57,6 dB; V8 è il file da aprire, condividere e caricare.

- Creata e verificata la timeline nativa Reel `ARPHE_E09_REELS_MIODOTTORE_V2`, 1080×1920/30,
  con cinque recensioni originali, intro Satoshi, card cream, canvas beige e CTA burgundy.
- Formalizzato lo standard riusabile in `docs/16_INSTAGRAM_REVIEW_REEL_STANDARD.md` e aggiunto
  il template senza dati reali `plans/ARPHE_INSTAGRAM_REVIEW_REEL_TEMPLATE.json`.
- Regole canoniche: 3–5 secondi per card, intro di tre secondi, CTA di quattro secondi,
  nessuna attribuzione sotto la recensione e verifica visuale prima di save/render.
- La V3 mobile-first aumenta card, corpo del testo, intro e CTA per la leggibilità sul telefono;
  diventa il riferimento al posto della V2 dopo catture ai frame 30, 130, 250 e 809.

## 2026-09-22 - Tunnel personale operativo e stato runtime per-workstation

- Creata e connessa nell'area Business l'app `ARPHE Resolve Personale`, associata esclusivamente
  al tunnel personale; l'app legacy resta invariata.
- `ping`, `resolve_status` e `get_feature_flags` ora restituiscono `workstation_id`, cosi' una
  verifica remota identifica senza ambiguita' la workstation che ha risposto.
- Test end-to-end ChatGPT -> tunnel personale -> bridge -> Resolve superato in sola lettura:
  `PC_PERSONALE`, Resolve `21.0.4.5`, progetto `New Project 4`, `ok=true`.
- Suite Creative Bridge aggiornata: `59` test superati. La safe-write resta intenzionalmente
  sospesa finche' non e' attiva una timeline di partenza nel progetto di test.
- Creati tunnel e Runtime API key dedicati al PC personale; la key resta cifrata con DPAPI e ha
  soltanto `Tunnels Read + Use`.
- Installato il runtime personale con Python `3.12.10` e venv dedicato; arrestato il vecchio
  processo manuale collegato al tunnel condiviso.
- Config, stato, stop request e blob DPAPI ora vivono sotto una directory per workstation in
  `%LOCALAPPDATA%\ARPHE\WindowsBridgeRuntimeV1\<WORKSTATION_ID>\`.
- Aggiunta migrazione controllata del blob legacy solo quando l'identità workstation coincide.
- Aggiunti test di regressione sui percorsi isolati e sulla migrazione del blob.
- Documentata la diagnosi delle installazioni remote con filesystem isolato, nelle quali i file
  creati dalla sessione di automazione possono non essere visibili al Task Scheduler reale.
- Verifica finale nel contesto del task: `PC_PERSONALE`, tunnel personale, MCP su Python 3.12,
  stato `ready` e `/readyz` uguale a `ready`.

## 2026-09-21 - Isolamento workstation e incidente tunnel condiviso

- Verificato sul PC personale il collegamento locale Python `3.12.10` -> DaVinci Resolve Studio
  `21.0.4.5`, con runtime `ready` e progetto `New Project 4` leggibile.
- Un test remoto parallelo ha restituito risultati incompatibili; il log personale ha ricevuto
  soltanto una delle due richieste, nonostante i test locali concorrenti fossero verdi.
- Identificato con confidenza alta il tunnel condiviso tra due workstation come causa primaria
  del routing ambiguo. Le write remote restano sospese fino alla separazione.
- Stabilita la regola definitiva: un solo branch `main`, codice condiviso, profili di deployment
  separati, un tunnel e una Runtime API key per workstation.
- Aggiunti il runbook dell'incidente e il design dei profili multi-workstation.

## 2026-09-24 — Piano E09 recensioni originali e transizioni cartolina

- Selezionate cinque recensioni pubblicate da MioDottore: due di medicina estetica e tre su
  ambiente, personale e organizzazione.
- Aggiunto il piano non distruttivo `ARPHE_E09_REVIEWS_CARTOLINE_V1` con CTA, palette ARPHÈ,
  formato 16:9 e preset `ARPHE_PAPER_STACK`.
- Documentata la sequenza di verifica frame-by-frame prima di qualsiasi salvataggio/render.
- Formalizzati nel workflow i parametri numerici dei tre preset di mixaggio long-form come baseline
  modificabile: passa-alto, denoise, EQ presenza, dynaudnorm, compressore e limiter.

## 2026-09-18 — Pacchetto portabile per PC personale

- Rimossi i vincoli applicativi che limitavano runtime Windows e Creative Bridge a
  `PC_SEGRETERIA`, mantenendo quella identità come default retrocompatibile.
- Aggiunto `scripts/install_personal_pc.ps1`, che installa bridge e autostart con identità
  `PC_PERSONALE` e salva la nuova chiave esclusivamente tramite DPAPI locale.
- Aggiunti requirements, esclusioni Git per config/segreti/stato e il manuale completo
  `docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md`.
- Tunnel, Runtime API key e app ChatGPT Business restano intenzionalmente risorse dedicate e non
  versionate. Test runtime e Creative Bridge verdi.

## 2026-09-15 — Correzione routing timeline long-form

- Il controllo read-only sul primo progetto audio-clean ha mostrato 12 timeline esistenti ma
  contenuti distribuiti sulla timeline corrente precedente: master con un solo estratto e diverse
  timeline individuali con due estratti.
- `apply_longform_edit_plan` ora seleziona esplicitamente la master prima di ogni append master e
  la timeline individuale prima di ogni append clip; nessun affidamento sul cambio implicito della
  timeline corrente di Resolve.
- Aggiunto un test di regressione che simula il comportamento reale di `CreateEmptyTimeline` e
  verifica esattamente quattro inserimenti sulla master e due su ciascuna clip per un piano di due
  estratti con audio sostitutivo. Suite: 50 test verdi. Schema MCP invariato a 39 azioni.

## 2026-09-15 — Audio long-form prima dei tagli ed export separati

- Aggiunto il preset conservativo `ARPHE_DIALOGUE_CLEAN_V1`: passa-alto 80 Hz, riduzione rumore,
  compressione moderata e limiter a circa -1 dB. L'intera sorgente viene trattata una sola volta
  in WAV PCM 48 kHz stereo, prima di costruire gli estratti.
- Il restauro gira come job asincrono (`start_prepare_longform_audio` e
  `get_longform_audio_job`) per evitare timeout e verifica la deriva temporale entro un frame.
- `apply_longform_edit_plan` accetta `enhanced_audio_path`: usa il video originale senza il suo
  audio e il WAV restaurato come unica sorgente sincronizzata sulla master e sulle timeline clip.
- `queue_longform_exports` prepara in Deliver un job distinto per ogni timeline senza render;
  `start_longform_exports` avvia solo quel batch e resta protetto da `CAP_RENDER`.
- Catalogo codice portato da 35 a 39 azioni; pubblicazione UI ancora da aggiornare. Suite: 49 test
  verdi, incluso filtro audio reale su segnale sintetico e batch export separato.

## 2026-09-15 — Longform tools nel bridge Creative 03

- Aggiunta capability gated `CAP_LONGFORM`, disabilitata per default.
- Aggiunte cinque azioni MCP: `list_longform_media`, `get_transcript_metadata`,
  `get_transcript_chunk`, `validate_longform_edit_plan`, `apply_longform_edit_plan`.
- Media e transcript sono limitati a directory locali allowlisted; ogni estratto è limitato a
  180 secondi e il piano a 32 estratti.
- L'applicazione rifiuta collisioni e crea esclusivamente un progetto nuovo, una timeline master
  e timeline individuali; originale preservato e salvataggio automatico disabilitato.
- Installer retrocompatibile: migra la config esistente aggiungendo i path longform e la flag
  spenta. Suite: 43 test PASS.
- Alleggerita la risposta di `validate_longform_edit_plan`: restituisce conteggi, durata massima e
  SHA-256 canonico invece di rimandare l'intero piano espanso attraverso il tunnel.
- Corretto il preflight di `apply_longform_edit_plan`: la disponibilità tecnica viene verificata
  sul progetto corrente prima di crearne uno nuovo, invece di passare un contesto progetto nullo.

## 2026-09-11 — Creative 03 aggiornata in-place a 29 azioni

- Reinstallata nel runtime locale la build contenente `create_review_sequence`, preservando la
  configurazione Creative esistente, e riavviato il bridge in modalità `Creative03`.
- Aggiornato lo schema dell'app ChatGPT già attiva da 28 a 29 azioni; verificata nella scheda
  amministrativa la presenza e la firma completa di `create_review_sequence`.
- Allineato `EXPOSED_TOOL_NAMES` alla ventinovesima azione dopo che la suite completa aveva
  correttamente segnalato il catalogo di sicurezza rimasto alla versione precedente.
- Confermato il comportamento reale della console: legge la copia installata sotto
  `C:\ARPHE\MCP`, può richiedere almeno 30 secondi per caricare e, per un'app già attivata,
  salva direttamente lo schema attivo senza mostrare un secondo pulsante `Pubblica`.
- La nuova primitiva resta sperimentale finché non supera la verifica visiva su una timeline
  separata; nessuna timeline Resolve è stata modificata durante l'aggiornamento dello schema.

## 2026-09-11 — Primitiva sperimentale sequenza review

- Aggiunta `create_review_sequence`: card come clip Fusion autonome con durata e posizionamento
  sfalsato a livello timeline.
- La nuova azione è isolata dalle animazioni stack esistenti e resta sperimentale fino al test
  visivo su Resolve; nessuna timeline validata viene modificata automaticamente.

## 2026-09-11 — Gate E: diagnosi animazione card

- Registrata la baseline statica Gate E e la prova con cinque card e entrate sfalsate.
- Confermato che le card statiche sono visibili, mentre le keyframe dello stack producono
  frame vuoti; `CAP_MOTION` resta `PARTIAL` e Gate E `PENDING`.
- Nessuna modifica al codice, nessun salvataggio o render effettuato.

## 2026-09-11 — Gate D ARPHE_SOFT_DROP PASS

- Validato end-to-end `ARPHE_SOFT_DROP` sulla nuova timeline
  `ARPHE_E09_16X9_GATE_D_V1`, lasciando intatta la baseline Gate C V5.
- Confermati composition `ARPHE_COMP_BCB45B060D`, review card `ARPHE_CARD_48A11B058C`,
  keyframe `0`, `15`, `18` e grafo Fusion di 19 nodi.
- Acquisiti e mostrati in ordine tutti i frame da `0` a `18` in tre batch `8 + 8 + 3`,
  con ripristino del playhead dopo ogni acquisizione.
- Promossa la diagnostica grafo/frame a `SUPPORTED`; `CAP_MOTION` resta complessivamente
  `PARTIAL` fino alla validazione del Gate E.
- Nessun testo di recensione, dato di provenienza o contenuto sensibile è stato versionato.

## 2026-09-10 — E09 riallineato alla chat e Gate D preparato

- Registrata la chiusura del content-use check: E09 usa recensioni reali già approvate da ARPHE,
  anonimizzate e fornite a runtime; testi e dati di provenienza non vengono hardcoded o versionati.
- Riallineati README, log esperimenti e schema Fusion: Gate B e card statica Gate C V5 sono PASS.
- Registrato il progresso della chat: app Creative 03 aggiornata in-place a 28 azioni e cattura
  JPEG dei frame `0`, `75`, `149` validata con ripristino del playhead.
- Definito Gate D su una nuova timeline versionata, lasciando V5 intatta.

## 2026-09-10 — Schema MCP e annotazioni di sicurezza

- Verificato che il server Creative 03 annuncia 28 azioni, incluse le due diagnostiche.
- Aggiornato lo snapshot dell'app ChatGPT da 26 a 28 azioni senza creare una nuova app.
- Aggiunte annotazioni MCP esplicite: letture realmente read-only; tutte le azioni closed-world
  e non distruttive; scritture e idempotenza dichiarate separatamente.
- Corretto `capture_timeline_frames`: la risposta usa ora contenuti MCP nativi per testo e JPEG,
  evitando la serializzazione Pydantic degli helper `Image`.
- Validata dalla chat la cattura dei frame `0`, `75` e `149` con ripristino del playhead; suite
  Creative 03 a 35 test verdi.

## 2026-09-09 — Diagnostica visuale e backup verificabile

- Aggiunti `inspect_fusion_graph` e `capture_timeline_frames` per telemetria e JPEG MCP esatti.
- Verificata la cattura live dei frame 0, 75 e 149 con ripristino di pagina e playhead.
- Aggiunto backup verificabile di Git, stato Creative e progetto Resolve `.drp` corrente.

## 2026-09-08 — Gate C V5 hardening e fonti Resolve/Fusion

- Gate B e review card statica Gate C V5 superati via API/read-back e controllo visivo.
- Corretto Text+ frame layout: `LayoutWidth`/`LayoutHeight`, non canvas `Width`/`Height`.
- Verificato il read-back degli input e i collegamenti Fusion; gestito il ritorno `None` delle proxy.
- Resa `add_review_card` reversibile sui soli nodi creati dalla chiamata fallita.
- Introdotto lo stato capability `PARTIAL` per i gate non ancora chiusi completamente.
- Aggiunto un confronto tracciato tra documentazione Blackmagic, probe Resolve 21 e manuali GitHub.
- Documentato il blocco Smart App Control del tunnel non firmato e il relativo debito di sicurezza.

## 2026-09-04 — ARPHE_MCP_BRIDGE_CREATIVE_03

- Aggiunta build MCP modulare affiancata per E09 MioDottore Review Social Creative.
- Mantenute le tool validate `ping`, `resolve_status`, `create_safe_working_timeline`.
- Aggiunte API semantiche e non distruttive per project/timeline, Fusion, review card, motion,
  asset e preview; nessuna shell/Python/Fusion property generica e nessuna delete.
- Aggiunti registry locale, palette e filesystem allowlist, audit metadata-only e feature flag.
- Project/Timeline attivi per Gate A; Fusion/Review/Motion/Assets/Render disabilitati di default.
- Aggiunti 21 test offline, installazione PC segreteria, switch runtime e rollback SAFE_WRITE_02.
- Registrato Gate A parziale: `Timeline.SetSetting` post-creazione rifiutato; corretta la sequenza
  impostando i default con `Project.SetSetting` prima di creare una nuova timeline.
- Gate A V2 superato con riscontro API e visivo: progetto ARPHE nuovo, timeline 1080x1920/30,
  nessun overwrite; le altre primitive project/timeline restano PENDING.
- Creato e verificato in Resolve il nuovo master E09 16:9
  `ARPHE_E09_MIODOTTORE_REVIEWS_16X9` / `ARPHE_E09_16X9_V1`, 1920x1080/30; la V2 verticale
  resta intatta e il prossimo punto di ripartenza è Gate B Fusion.
- Gate A `create_project` / `create_timeline` / `get_creative_status` è `SUPPORTED`; le altre
  primitive project/timeline e i Gate B-G restano `PENDING`.

## 2026-09-04 — Windows bridge autostart + READ validati su PC_SEGRETERIA

- Installato `ARPHE_WINDOWS_BRIDGE_RUNTIME_V1` sul PC segreteria con secret DPAPI per-user.
- Confermato Task Scheduler `At logon` con processo background `pythonw.exe` e nessuna
  PowerShell persistente.
- Dopo riavvio/login: `/readyz` HTTP 200, ChatGPT `ping` PASS e `resolve_status` PASS.
- Corretti alias Python `WindowsApps` incompatibile con Task Scheduler e JSON con BOM di
  Windows PowerShell 5.1.
- Stato dichiarato **AUTOSTART + READ VALIDATED**; SAFE WRITE persistente, restart/backoff e
  audit segreti restano pending.

## 2026-09-01 — ARPHE_WINDOWS_BRIDGE_RUNTIME_V1 (repository)

- Aggiunto runtime Windows limitato a `PC_SEGRETERIA` in `scripts/windows_bridge/`.
- Autostart per-user via Task Scheduler `At logon` con `pythonw.exe`, senza console persistente.
- Secret runtime protetto con DPAPI per-user; health `/readyz`, restart/backoff, Job Object e log redatti.
- Aggiunti install/start/stop/status/uninstall PowerShell, config di esempio, test e guida operativa.
- Deployment e acceptance test reali sul PC segreteria restano pending; nessuna modifica al PC personale.
- Fix deployment Windows: lettura config compatibile con BOM di Windows PowerShell 5.1,
  scrittura UTF-8 senza BOM e rifiuto degli alias Python `WindowsApps` per Task Scheduler.

## 2026-09-01 — Workstation chiarite + runtime Windows come prossima priorità

- confermato che tutti i test end-to-end del 2026-09-01 sono stati eseguiti sul **PC segreteria**, non sul PC personale;
- introdotti gli identificatori logici `PC_SEGRETERIA` (CURRENT / VALIDATED) e `PC_PERSONALE` (PENDING REPLICA);
- il tunnel `ARPHE-RESOLVE-HOME` è documentato come nome legacy/fuorviante del tunnel attualmente collegato al PC segreteria;
- deciso un tunnel e una runtime API key separati per ogni workstation;
- vietata la copia della runtime API key del PC segreteria sul PC personale;
- creato `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md`;
- dopo il PASS end-to-end READ + SAFE WRITE, la nuova priorità è `ARPHE_WINDOWS_BRIDGE_RUNTIME_V1` per eliminare la PowerShell manuale;
- v1 deve partire nella sessione utente tramite Windows Task Scheduler `At logon`, non come Windows Service Session 0;
- il task di implementazione è delegabile a Codex e deve limitarsi a autostart, secret storage, health, restart/backoff, logging e deployment multi-workstation.

## 2026-09-01 — ChatGPT -> MCP -> Resolve READ + SAFE WRITE end-to-end validati

### READ end-to-end
- custom app DEV `ARPHE Resolve` collegata al tunnel `ARPHE-RESOLVE-HOME`;
- autenticazione MCP: None;
- chiamata `resolve_status` eseguita direttamente dalla conversazione ChatGPT;
- letti Resolve `21.0.4.5`, progetto `blabla`, `Timeline 1`, 30 fps, 1 traccia video, 1 audio, 130 clip V1 e 130 clip A1.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> MCP locale -> Resolve Studio READ è supportato end-to-end.**

### SAFE WRITE end-to-end
- bridge `ARPHE_MCP_BRIDGE_SAFE_WRITE_02` avviato tramite lo stesso tunnel;
- `/readyz` -> HTTP 200 `ready`;
- app DEV `ARPHE Resolve WRITE Test` collegata;
- `ping` da ChatGPT ha confermato `SAFE_WRITE` e `create_safe_working_timeline` abilitata;
- ChatGPT ha chiamato `create_safe_working_timeline`;
- timeline count: `3 -> 4`;
- creata `ARPHE_CHATGPT_WRITE_TEST_20260901_185749`;
- ritorno automatico a `Timeline 1`: `true`;
- clip edit: `0`;
- timeline delete: `0`;
- tool result: `ok=true`.

Conclusione:
**ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python -> Resolve Studio SAFE WRITE è supportato end-to-end** per la primitiva non distruttiva testata.

Prossima priorità aggiornata: rendere il bridge persistente sul PC segreteria; poi `list_media` allowlisted -> `transcribe_media` locale -> `apply_edit_plan` minimale su nuova timeline.

## 2026-09-01 — External Resolve WRITE validato

### Test `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`
- eseguito da Python esterno con Resolve Studio aperto;
- progetto `blabla`;
- timeline originale `Timeline 1`;
- timeline count prima `2`;
- creata timeline vuota `ARPHE_API_WRITE_TEST_20260901_145018`;
- timeline count dopo `3`;
- ritorno automatico all'originale riuscito (`True`);
- timeline finale `Timeline 1`;
- exit code `0`.

Conclusione:
**Python esterno -> Resolve Studio WRITE non distruttiva è supportato nel nostro ambiente** almeno per `CreateEmptyTimeline` e `SetCurrentTimeline`.

La prossima priorità infrastrutturale diventa il transport gate:
`ChatGPT -> Secure MCP Tunnel -> MCP locale -> Resolve READ`.

## 2026-09-01 — MCP locale -> Resolve READ validato

### Test MCP `ARPHE_MCP_BRIDGE_READ_01`
- installato/usato Python MCP SDK v2 per il prototipo locale;
- protocollo MCP negoziato correttamente;
- tool discovery riuscita: `ping`, `resolve_status`;
- `ping` ha confermato modalità `READ_ONLY` e write tool disabilitate;
- `resolve_status` ha raggiunto DaVinci Resolve Studio attraverso il bridge Python;
- letto Resolve `21.0.4.5`, progetto `blabla`, `Timeline 1`, FPS 30, 1 traccia video, 1 audio, 130 clip V1 e 130 clip A1;
- exit code 0;
- nessuna modifica fatta in Resolve.

Conclusione:
**MCP locale -> tool -> bridge Python -> Resolve Studio READ è supportato nel nostro ambiente.**

Non è ancora validato il tratto cloud `ChatGPT -> Secure MCP Tunnel -> MCP locale`.

## 2026-09-01 — Resolve Studio external API + ChatGPT/MCP pivot

### Resolve Studio
- installato/testato DaVinci Resolve Studio `21.0.4.5`;
- impostato `External scripting using = Local`;
- `ARPHE_STUDIO_EXTERNAL_API_TEST_01` eseguito da Python esterno con exit code 0;
- letti correttamente progetto `blabla`, `Timeline 1`, 30 fps, 1 traccia video, 1 audio, 130 item V1 e 130 item A1;
- conclusione: **external READ API supported** nel nostro ambiente;
- preparato `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02` come probe non distruttivo.

### Nuova direzione prodotto
La segreteria deve usare **ChatGPT come interfaccia primaria**, non una GUI ARPHE separata.

Architettura target:

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio API`

Il bridge è infrastruttura: tool allowlisted, validazione, accesso controllato ai media e operazioni deterministiche su Resolve.

### Ricerca MCP
Verificata la fattibilità concettuale sulle fonti correnti:
- custom MCP app in ChatGPT possono esporre tool e, con full MCP, write/modify;
- full MCP write è attualmente beta su Business, Enterprise ed Edu web;
- Pro può collegare custom MCP in read/fetch ma non full write al momento;
- server MCP locali/private network richiedono Secure MCP Tunnel per essere raggiunti da ChatGPT senza esposizione pubblica;
- `tunnel-client` può inoltrare a MCP locale via stdio/HTTP;
- SDK Python MCP v2 scelto come base del prototipo.

### Cleanup architetturale
- creato `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`;
- creato `docs/RESOLVE_STUDIO_CAPABILITIES.md`;
- aggiornati README, START_HERE, CURRENT_STATE, INDEX, setup, longform, operator guide, roadmap ed EXPERIMENT_LOG;
- vecchio design `ARPHE Remote Agent V1` GUI + GitHub polling dichiarato **SUPERSEDED**;
- mantenuti i suoi principi di sicurezza utili: allowlist, path guard, original timeline protection, log strutturati.

### Podcast benchmark
- usare estratti autonomi di circa 8–15 minuti;
- una volta esportato l'estratto, tutti i timestamp ripartono da `00:00`;
- nessun mapping al timecode del podcast completo durante l'esperimento;
- candidate automatico congelato prima del reference umano.

## 2026-09-01 — Benchmark editoriale + profilo v0.1

### Benchmark 01
- creato reference umano da timeline Resolve tramite `ARPHE_EXPORT_REFERENCE_EDIT_02.py`;
- confronto contro `ARPHE_LONGFORM_SAFE_EDIT_PLAN_V3`;
- Precision 0.522;
- Recall 0.430;
- F1 0.472;
- false positive 197.5 s;
- false negative 286.1 s;
- 48 boundary matched su 246;
- mean boundary error 625 ms;
- median boundary error 373 ms.

### Lezione principale
Il collo di bottiglia non è soltanto il posizionamento della lama.
Prima del waveform alignment bisogna migliorare la selezione editoriale e il rilevamento di micro-cut/speech repair.

### ARPHE Editorial Profile v0.1
- pause: accorciare quelle eccessive senza azzerare il ritmo;
- vocalizzi (`ehm`, `eeee`, `mmm`): non eliminarli sempre, solo quando la ricucitura resta naturale;
- filler linguistici: rimuovere solo quando non svolgono realmente funzione nel discorso;
- false partenze: preferire ricuciture precise conservando il prefisso buono;
- ripetizioni: preferire la formulazione più chiara/completa;
- tagli concettuali: livello editoriale separato;
- contenuto sensibile/reputazionale: FLAG ONLY, mai auto-cut.

### Nuovo protocollo di sviluppo
- congelare il candidate automatico prima di leggere il reference umano;
- usare materiale mai visto per misurare la generalizzazione;
- classificare mismatch per categoria;
- ottimizzare una categoria alla volta;
- per iterazioni rapide usare estratti/campioni invece di longform completi.

## 2026-08-27 — Longform transcript + audio alignment

### Validato
- trascrizione esterna con `faster-whisper` in JSON `ARPHE_TRANSCRIPT_V1`;
- timestamp a livello segmento e parola utili per paper edit;
- diagnostica timing su `blabla.mp4`: sorgente 30 fps, timeline 30 fps, 62860 frame, durata Resolve e Whisper coerenti;
- il problema delle parole troncate non era drift FPS nel test;
- ricostruzione timeline resta la primitiva corretta per applicare i cut senza toccare l'originale.

### Osservato nei rough cut
- usare direttamente i timestamp Whisper come edit point produce cut troppo vicini alle parole;
- restano pause lunghe se non vengono trattate separatamente;
- un bordo video/audio apparentemente allineato può comunque contenere troppo silenzio prima del parlato: non è necessariamente vero fuori-sync.

### Nuova architettura editoriale emersa allora
- ChatGPT decide semanticamente **cosa** togliere;
- Whisper localizza/protegge le parole;
- un analizzatore locale legge la waveform reale e raffina i confini;
- Resolve applica gli intervalli raffinati ricostruendo una nuova timeline.

Principio ancora valido:
**decisione editoriale ≠ posizione fisica della lama**.

### V4.x
- V4.2: primo audio align conservativo; osservata troppa aria in alcune giunzioni.
- V4.3: candidato con giunzioni più compatte; ha corretto il problema specifico della troppa aria, ma non risolve da solo la selezione editoriale.

## 2026-08-25 — Sessione iniziale

### Validato
- esecuzione script Python dentro Resolve;
- lettura progetto/timeline;
- ricostruzione timeline per cut;
- zoom statico via TimelineItem;
- Fusion Transform;
- `BezierSpline` per yoyo;
- creazione Tracker da script;
- tracking manuale nativo + lettura path da Python.

### Scartato come base di produzione
- simulare yoyo con micro-tagli;
- usare il Tracker in serie verso MediaOut;
- affidarsi al trigger automatico `TrackForward` via FusionScript nella build Free testata.

### Regole aggiunte
- mai modificare l'originale;
- tracking sempre limitato al range utile;
- tracking anchor separato dal centro estetico;
- ogni passaggio manuale spiegato click-per-click.
## 2026-10-09 — Vertical Social Assistant foundation

- Aggiunti contratto, piano versionato, lifecycle, recupero locale e strumenti MCP chiusi.
- `CAP_VERTICAL_SOCIAL` resta `false`; PC personale e segreteria mantengono stati separati.
- Il CUT ha ora un motore proprio: conserva intervallo, motivo, effetto narrativo e dipendenze;
  genera una timeline provvisoria nominata, verifica il read-back A/V e riusa soltanto una prova
  già verificata dello stesso piano. Non modifica la timeline sorgente.
- L'approvazione resta legata a target e istruzioni editoriali; gli stati/evidenze di esecuzione
  non invalidano un retry idempotente. Test automatici: piano, impronta, range, read-back e resume
  PASS. Nessun gate Resolve nativo né workstation è stato modificato per questa estensione.

## 2026-10-10 — Vertical Social contract v2 e primi esecutori

- Separati `B_ROLL_PROVIDED` e `B_ROLL_GENERATED`: il primo richiede asset, range sorgente,
  range timeline e motivo; il secondo fallisce chiuso finché manca un provider validato.
- Aggiunto l'esecutore MCP idempotente per REFRAME e B-roll fornito sulla sola timeline provvisoria
  del piano, con target esplicito, read-back, journal e ripristino della timeline sorgente.
- Grafiche e CTA sono opzionali e validate contro ruoli colore canonici; non vengono applicate se
  assenti e restano non eseguibili fino al proprio gate Resolve.
- Test Vertical Social: 43 PASS. Suite completa del bridge: 405 PASS e 1 skip previsto. Gate nativi PC_PERSONALE PASS per CUT, REFRAME e B-roll fornito;
  PC_SEGRETERIA non modificato e ancora PENDING.
- Contratto v3: `MUSIC_DUCK` usa la proprietà Resolve reale `AudioVolume`, richiede confini clip
  esatti, limita il guadagno a -30/0 dB e ha superato un gate sintetico reversibile a -12 dB con
  ripristino a 0 dB sul solo PC_PERSONALE.
- Contratto v4: GRAPHIC e CTA opzionali hanno un esecutore Fusion su track dedicata, range esatto,
  palette del Graphic Kit e read-back del testo. Gate nativo su timeline temporanea PASS e rollback
  completato sul solo PC_PERSONALE.
- Contratto v5: CAPTIONS è eseguibile soltanto dopo picture lock, con cue non sovrapposte, massimo
  84 caratteri/due righe, fasce sicure e un solo carrier Fusion. Il lock registra l'impronta reale
  della timeline provvisoria e blocca qualsiasi esecuzione dopo una modifica. Gate sintetico
  parametrico PASS; la precedente prova renderizzata reale resta documentata separatamente.
- Suite completa aggiornata: 419 PASS e 1 skip Windows previsto. `CAP_VERTICAL_SOCIAL=false`,
  PC_SEGRETERIA non toccato, B-roll generato ancora chiuso.
- Commit `3fa0385` reinstallato sul solo `PC_PERSONALE`: hash della copia runtime corrispondente,
  contratto v5, task e supervisore attivi, `/readyz` HTTP 200. Il flag Vertical Social è rimasto
  disabilitato; nessuna config o runtime di `PC_SEGRETERIA` è stata modificata.

## 2026-10-10 — Branded Longform Editorial

- Sostituito il concetto ARPHE-only con `BRANDED_LONGFORM_EDITORIAL` e profili brand isolati.
- Aggiunti contratto, input OBS single/multicam, job persistenti per workstation, binding a
  sorgente/profilo/timeline, cleanup conservativo e proposta editoriale adattiva.
- Aggiunte timeline derivate `_CLEANUP` e `_EDITORIAL`, marker idempotenti, approvazione batch
  legata all'impronta e applicazione grafica Fusion sul solo profilo ARPHE ready.
- Il profilo Carabellese resta pending e blocca le grafiche senza contaminazioni ARPHE.
- Aggiunti strumenti MCP completi, validatore, ledger e gate nativo con rollback su progetto
  sintetico PC_PERSONALE. Capability ancora disabilitata; PC_SEGRETERIA non toccato.
- Gate nativo PC_PERSONALE superato: copie `_CLEANUP`/`_EDITORIAL`, marker, grafica Fusion Satoshi
  e rollback del progetto sintetico verificati; aggiunti retry idempotente e rollback degli overlay
  parziali, impronta strutturale della timeline originale e validazione/fingerprint dei pacchetti
  SINGLE/OBS. Suite completa: 457 test, 1 skip per privilegio symlink Windows.
- Il cleanup high-confidence ora ricostruisce fisicamente `_CLEANUP` dalla sorgente A/V singola,
  preservando l'originale; timeline complesse e multicam restano fail-closed in revisione.
- Il B-roll fornito con asset e range sorgente espliciti è applicabile solo su `_EDITORIAL`; B-roll
  generato e cambio camera restano proposte non automatiche.
