# EXPERIMENT LOG

Scopo: tenere un registro persistente degli esperimenti, dei file coinvolti, dell'ipotesi testata, del risultato e del prossimo passo. Questo file deve impedire di perdere il filo quando arrivano nuovi MP4, transcript, edit plan, reference JSON e report.

## Regola generale

Ogni nuovo esperimento deve avere:
- ID esperimento;
- sorgente/video;
- file input;
- candidate automatico congelato prima del reference umano;
- reference umano;
- report di confronto;
- risultato;
- decisione: validated / partial / rejected;
- prossimo passo.

## E01 — Auto-cut shortform

Stato: VALIDATED.

Risultato:
- ricostruzione timeline con `AppendToTimeline` funziona;
- originale preservato;
- preferire ricostruzione a blade diretto.

## E02 — Yoyo / Fusion / Tracking

Stato: PARTIAL / proof of concept.

Risultato:
- Transform + BezierSpline validati;
- tracking manuale nativo + lettura path da Python funziona;
- auto TrackForward via FusionScript non affidabile nella build Free;
- tracking anchor e centro estetico devono restare separati.

## E03 — Longform transcript + rough cut

Sorgente: `blabla.mp4`.

Passaggi:
- trascrizione `faster-whisper` con word timestamps;
- timing diagnostic: source e timeline 30 fps, nessun drift rilevante;
- V1/V2 rough cut: troppo aggressivi / parole troncate;
- V3 safe cut: migliorato ma ancora incompleto;
- V4.2 waveform alignment: riduce parole troncate ma lascia troppa aria in alcune giunzioni;
- V4.3: corregge meglio la giunzione, ma non risolve il problema editoriale principale.

Decisione:
- waveform = strumento per `dove tagliare`, non per `cosa tagliare`.

## E04 — Benchmark umano 01

Sorgente: `blabla.mp4`.
Reference: `ARPHE_REFERENCE_EDIT_Timeline_1.json`.
Candidate iniziale confrontato: `ARPHE_LONGFORM_SAFE_EDIT_PLAN_V3`.

Metriche:
- Precision 0.522
- Recall 0.430
- F1 0.472
- False positive 197.5 s
- False negative 286.1 s
- Boundary matched 48 / 246
- Mean boundary error 625 ms
- Median boundary error 373 ms

Interpretazione:
- molti tagli umani non vengono rilevati;
- diversi tagli automatici non coincidono con la scelta umana;
- il boundary placement resta da migliorare ma non è il collo di bottiglia principale.

Profilo editoriale emerso:
- pause: accorciare ma preservare ritmo naturale;
- `ehm/eeee/mmm`: non rimuovere sempre;
- filler: rimuovere solo se non portano a nulla;
- false partenze: preferire speech repair precisa, conservando il prefisso buono e ricucendo alla continuazione corretta;
- tagli concettuali: trattarli come livello editoriale separato;
- contenuto sensibile: FLAG ONLY, mai auto-cut.

## E05 — Podcast excerpt benchmark

Stato: NEXT.

Obiettivo:
- evitare di lavorare ogni volta su episodi podcast completi molto lunghi;
- scegliere una porzione interessante destinata potenzialmente alla pubblicazione;
- usare solo quella porzione come unità canonica del benchmark.

Workflow consigliato:

1. Individuare nel podcast originale un intervallo utile, idealmente 8–15 minuti.
2. Annotare il timecode originale di inizio/fine episodio.
3. Esportare quella porzione come MP4 autonomo, senza montaggio editoriale.
4. Questo MP4 diventa la `SOURCE_EXCERPT` e parte da 00:00.
5. Generare transcript con word timestamps sulla SOURCE_EXCERPT.
6. Generare il candidate automatico e congelarlo PRIMA di vedere il reference umano.
7. Montare manualmente la stessa SOURCE_EXCERPT come risultato desiderato.
8. Importare/ricreare il reference in Resolve e usare `ARPHE_EXPORT_REFERENCE_EDIT_02.py`.
9. Confrontare candidate e reference con `ARPHE_COMPARE_CUTS_01.py`.
10. Classificare i mismatch per categoria editoriale.
11. Aggiornare le regole solo dopo il report.

### Mapping al podcast originale

Per non perdere il collegamento con l'episodio lungo, salvare sempre:
- `episode_file`;
- `excerpt_start_in_episode_sec`;
- `excerpt_end_in_episode_sec`.

Formula:

`timestamp episodio = timestamp excerpt + excerpt_start_in_episode_sec`

Quindi non serve fornire o processare tutto il podcast ogni volta.

## Naming consigliato dei file

Per evitare confusione:

`E05_SOURCE_EXCERPT.mp4`
`E05_TRANSCRIPT.json`
`E05_CANDIDATE_V1.json`
`E05_REFERENCE.json`
`E05_REPORT.txt`

Per esperimenti successivi incrementare E06, E07, ecc.

## Principio di continuità

La chat non deve essere l'unico posto in cui vive lo stato del progetto. La repository è la fonte persistente: prima di iniziare un nuovo esperimento controllare `CURRENT_STATE.md`, `EXPERIMENT_LOG.md` e `docs/07_EDITORIAL_BENCHMARK.md`.
