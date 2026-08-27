# CURRENT STATE

Ultimo aggiornamento: sessione 2026-08-25.

## Obiettivo del progetto

Automatizzare il montaggio di contenuti video in DaVinci Resolve tramite Python:
- cut / remove / reassemble;
- punch-in e zoom ritmici;
- tracking del soggetto;
- B-roll;
- in futuro trascrizione e paper edit di longform.

## ✅ VALIDATO

### Cut automatici
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

## ⚠️ PARZIALE / DA RIFINIRE

### Reframing estetico dopo tracking
Il tracking può essere tecnicamente corretto ma il soggetto può risultare scentrato durante forti zoom.

Lezione:
**punto di tracking ≠ centro estetico dell'effetto**.

Il tracker va posizionato sul dettaglio più stabile; il framing finale deve usare un offset/target separato.

### Maschere Fusion
La creazione di una Ellipse Mask da script è stata osservata, ma non è la base consigliata per il punch.
Per il nostro use case il tracker è più appropriato.

## ❌ NON AFFIDABILE NELLA BUILD ATTUALE

### Avvio automatico del tracking da FusionScript
I trigger `TrackForward` / `TrackForwardFromCurrentTime` sono esposti, ma i test hanno prodotto:
- path immobile;
- range di render anomali;
- nessun path/modifier generato.

Decisione:
**non basare il prodotto sul trigger automatico del Tracker nella versione gratuita attuale**.

Strategia corrente:
1. Python prepara tutto.
2. Operatore esegue un singolo Track Forward nativo.
3. Python riprende il controllo.

## PROSSIMO FILONE

### Longform
Pipeline proposta:
1. MP4 longform in Resolve.
2. Timeline pulita.
3. Estrazione audio / trascrizione con timestamp.
4. Analisi editoriale del transcript.
5. Lista di intervalli da rimuovere.
6. Script Python che crea una nuova timeline tagliata.
7. Originale sempre preservato.
