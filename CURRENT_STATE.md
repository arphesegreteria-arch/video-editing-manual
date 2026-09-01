# CURRENT STATE

Ultimo aggiornamento: sessione 2026-09-01.

## Obiettivo del progetto

Automatizzare il montaggio di contenuti video in DaVinci Resolve tramite Python:
- cut / remove / reassemble;
- punch-in e zoom ritmici;
- tracking del soggetto;
- B-roll;
- trascrizione e paper edit di longform;
- raffinamento automatico dei punti di taglio sull'audio reale.

## ✅ VALIDATO

### Cut automatici per ricostruzione timeline
`ARPHE_AUTOCUT_TEST_01.py`
- crea una nuova timeline;
- ricompone intervalli della clip sorgente;
- elimina segmenti senza modificare l'originale;
- approccio consigliato: ricostruzione timeline, non blade diretto.

### Fusion Transform + BezierSpline
`ARPHE_NUCLEAR_RESET_YOYO_08.py`
- nuova timeline pulita;
- nuova Fusion Comp;
- `Transform.Size` animato tramite `BezierSpline`;
- effetto yoyo evidente e funzionante.

### Tracking manuale nativo + lettura Python
`ARPHE_MANUAL_TRACK_SETUP_13A_V2.py`
`ARPHE_TRACKED_YOYO_APPLY_13B_V2.py`
- Python prepara Tracker e range;
- operatore esegue il Track Forward nativo in Fusion;
- Python legge `TrackedCenter1`;
- path del tracking può pilotare l'effetto yoyo.

### Trascrizione longform esterna
Workflow con `faster-whisper` testato su `blabla.mp4`:
- JSON `ARPHE_TRANSCRIPT_V1` generato correttamente;
- timestamp a livello segmento e parola;
- durata transcript: circa 2095.339 s;
- il JSON è adatto al paper edit semantico.

### Diagnostica timing longform
Sul test `blabla.mp4`:
- source FPS = 30.0;
- timeline FPS = 30.0;
- frames = 62860;
- durata Resolve ≈ 2095.333 s;
- durata Whisper ≈ 2095.339 s.

Conclusione: nel test non c'è drift progressivo tra transcript e Resolve.

## ⚠️ PARZIALE / DA RIFINIRE

### Longform: paper edit da transcript
Il transcript è valido per decidere **cosa** togliere, ma i timestamp Whisper non devono essere trattati come punti di lama perfetti.

Problemi osservati nei primi rough cut:
- alcune parole tranciate;
- pause residue troppo lunghe;
- stacchi poco naturali sul parlato;
- jump cut visivi da revisionare.

Lezione:
**decisione editoriale ≠ posizione fisica del cut**.

Strategia corrente:
1. ChatGPT decide semanticamente cosa eliminare.
2. Whisper protegge e localizza le parole.
3. Un analizzatore locale legge la waveform reale dell'MP4.
4. Il confine viene spostato in un punto quieto vicino, senza mangiare altro parlato.
5. Resolve ricostruisce una nuova timeline.

### Audio-aligned cut V4.x
- V4.2: approccio conservativo, ma ottimizzare separatamente i due bordi può lasciare troppa aria alla giunzione.
- V4.3: candidato corrente; tratta la giunzione in modo più stretto e riduce il silenzio residuo.
- Stato: **in prova, non ancora promosso a validato**.

### Reframing estetico dopo tracking
Il tracking può essere tecnicamente corretto ma il soggetto può risultare scentrato durante forti zoom.

Lezione:
**punto di tracking ≠ centro estetico dell'effetto**.

Il tracker va posizionato sul dettaglio più stabile; il framing finale deve usare un offset/target separato.

## ❌ NON AFFIDABILE / DA NON USARE COME PRIMITIVA

### Timestamp Whisper usati direttamente come lama
Non usare `start/end` del transcript come cut frame senza margine o allineamento audio.

### Avvio automatico del tracking da FusionScript
I trigger `TrackForward` / `TrackForwardFromCurrentTime` sono esposti, ma i test hanno prodotto path immobili e range anomali.

Decisione:
**non basare il prodotto sul trigger automatico del Tracker nella versione gratuita attuale**.

Strategia tracking corrente:
1. Python prepara tutto.
2. Operatore esegue un singolo Track Forward nativo.
3. Python riprende il controllo.

## PROSSIMO TEST

### Validazione V4.3 longform
1. Partire sempre dalla timeline originale completa.
2. Generare il piano audio-aligned dal video + transcript + edit plan.
3. Creare una nuova timeline `LONGFORM_AUDIO_ALIGNED_CUT_04_3`.
4. Revisionare tutto il longform con priorità a:
   - attacchi delle parole dopo i cut;
   - code delle parole prima dei cut;
   - pause troppo lunghe/corte;
   - eventuale vero offset audio/video;
   - qualità visiva dei jump cut.
5. Solo dopo revisione completa promuovere la V4.3 a `validated`.

## 2026-08-31 — Remote Agent: chiusura atomica al confine di claim

- La richiesta di chiusura ora usa una stretta di mano atomica con il runner: un job già attivo richiede esplicitamente `finish` o `abort`, mentre un claim ancora in transito viene bloccato in modo irrevocabile.
- Un job che attraversa il confine dopo l'inizio della chiusura viene finalizzato `ABORTED`, senza avviare l'handler e senza pubblicare un `current_job_id` transitorio.
- Aggiunto un test deterministico controller + runner reale + coda finta che forza questo interleaving e controlla stato offline, heartbeat senza job corrente e transizione terminale.
- Verifica automatizzata: `194 passed, 1 skipped` con la suite completa del remote agent.

## 2026-08-31 — Remote Agent V1 release candidate

- Stato documento: release candidate con verifica automatizzata del branch per installazione manuale su `HOME_DEV`; checklist live `HOME_DEV` + Resolve Studio non ancora passato e tag `REMOTE_AGENT_V1_HOME_DEV_TESTED` ancora non impostato.
- Profilo `POLI_01`: ancora più ristretto di `HOME_DEV` e **non production-ready** in V1.
- Suite automatizzata più recente in questo branch: `221 passed, 1 skipped`.
- Gate automatizzato documentato per il branch: attivare un venv di sviluppo dedicato, installare `scripts/remote_agent/requirements-dev.txt` cosi `pytest` e disponibile sul PATH del venv, quindi eseguire dal root del repository `pytest tests/remote_agent -v`.
- Il test di regressione del launcher usa il `pytest.exe` gemello dell'interprete attivo, rimuove `PYTHONPATH` e verifica in `--collect-only` che la vera suite `tests/remote_agent` si raccolga dal root del repository senza errori di import.

Versioni verificate in questo ambiente di sviluppo:
- Python 3.12.13
- pytest 9.1.1
- pydantic 2.13.4
- requests 2.34.2
- keyring 25.7.0
- psutil 7.2.2

Limitazioni osservate:
- L'installer Windows e l'uninstaller PowerShell sono stati validati con parser, test statici e suite automatizzata, ma non eseguiti sul vero PC `HOME_DEV` in questa sessione.
- Il collegamento live a DaVinci Resolve Studio e i probe distruttivi restano subordinati al checklist manuale su `ARPHE_TEST` o `ARPHE_AUDIT_*`.
- Finché il checklist live non passa, non va pubblicata la dicitura `REMOTE_AGENT_V1_HOME_DEV_TESTED`.
- La static secret scan PowerShell esatta su `scripts/remote_agent` e `tests/remote_agent`, con esclusione di `__pycache__`, restituisce solo fixture sintetiche in `test_github_queue.py`, `test_job_runner.py`, `test_logging.py`, `test_models.py` e l'header `Authorization` costruito intenzionalmente in `github_queue.py`; nessun secret reale nei file scansionati.
- L'assenza di `pytest` sul PATH globale della macchina non e un criterio di fallimento del branch: conta solo il venv di sviluppo dedicato usato per il gate automatizzato.
