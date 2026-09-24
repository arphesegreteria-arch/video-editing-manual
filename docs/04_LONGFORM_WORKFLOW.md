# 04 — Longform Workflow

## Obiettivo

Usare il contenuto parlato per creare un primo rough cut automatico, mantenendo separati:
- decisione editoriale;
- localizzazione delle parole;
- precisione fisica del punto di taglio;
- esecuzione deterministica in Resolve.

## Pipeline editoriale corrente

### Ordine obbligatorio: audio → tagli → Deliver

1. Avviare `start_prepare_longform_audio` sulla registrazione originale.
2. Controllare `get_longform_audio_job` fino allo stato `COMPLETED`.
3. Ascoltare un campione del WAV e conservare il suo `output_path`.
4. Validare il piano una sola volta e chiamare `apply_longform_edit_plan` passando
   `enhanced_audio_path`.
5. Verificare contenuto e sincronizzazione delle timeline individuali.
6. Chiamare `queue_longform_exports`: in Deliver compare un job per ogni estratto.
7. Solo dopo il gate umano e con `CAP_RENDER=true`, chiamare `start_longform_exports`.

Il trattamento precede i tagli, quindi ogni estratto riceve la stessa correzione e non dipende da
interventi manuali clip per clip. Il video rimane quello originale; il suo audio viene escluso e
sostituito dal WAV sincronizzato. La preparazione dei job non avvia automaticamente il render.

1. Selezionare una sorgente o una `SOURCE_EXCERPT` autonoma.
2. Conservare sempre la sorgente/timeline originale intoccabile.
3. Trascrivere localmente con `faster-whisper`.
4. Generare JSON `ARPHE_TRANSCRIPT_V1` con timestamp segmento + parola.
5. Analizzare il transcript per:
   - pause eccessive;
   - disfluenze;
   - false partenze / speech repair;
   - ripetizioni;
   - digressioni o concetti non funzionali;
   - contenuti sensibili da **FLAG**, non da auto-cut.
6. Generare un edit plan strutturato.
7. **Non usare i timestamp Whisper direttamente come lama.**
8. Raffinare i bordi con analisi locale dell'audio reale:
   - proteggere gli intervalli occupati dalle parole;
   - cercare punti di giunzione naturali;
   - privilegiare la conservazione del parlato rispetto all'aggressività;
   - accorciare pause chiaramente troppo lunghe lasciando respiro.
9. Validare edit plan e intervalli.
10. Resolve crea una **nuova timeline** usando gli intervalli da tenere.
11. Operatore revisiona il risultato.

## Principio fondamentale

**ChatGPT decide cosa tagliare; l'audio aiuta a decidere dove mettere la lama; Python/Resolve eseguono deterministicamente.**

Whisper è una mappa semantica e temporale, non un sistema di edit point perfetti.

## Runtime: prototipo storico vs target

### Prototipo V4.x
Il prototipo corrente genera script `.py` da lanciare in Resolve. È servito per validare ricostruzione timeline e audio alignment.

### Target prodotto

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio external API`

Nel prodotto finale la segreteria non deve generare/copiare/lanciare manualmente uno script Resolve. ChatGPT discute le decisioni, poi chiama tool MCP controllate e il bridge esegue il piano tramite API Studio.

Dettagli: `08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`.

## Podcast excerpt benchmark

Per velocizzare gli esperimenti su podcast molto lunghi:
- esportare un estratto autonomo di circa 8–15 minuti **prima** del montaggio editoriale;
- da quel momento trattare l'estratto come unica sorgente canonica;
- tutti i timestamp partono da `00:00` dell'estratto;
- non mantenere mapping col timecode dell'episodio completo durante il benchmark.

## Diagnostica FPS

Prima di attribuire parole troncate a drift temporale, verificare:
- FPS timeline;
- FPS sorgente;
- durata in frame;
- durata transcript.

Nel test `blabla.mp4`:
- timeline = 30 fps;
- sorgente = 30 fps;
- 62860 frame;
- Resolve ≈ 2095.333 s;
- Whisper ≈ 2095.339 s.

Quindi il problema osservato non era drift FPS.

## Formato edit plan

Esempio minimo:

```json
{
  "source_file": "E05_SOURCE_EXCERPT.mp4",
  "remove": [
    {"start": 222.5, "end": 238.2, "reason": "ripetizione"}
  ],
  "flags": [
    {"start": 431.0, "end": 447.8, "reason": "contenuto_sensibile"}
  ]
}
```

Il formato dovrà evolvere per rappresentare in modo esplicito anche le `speech_repairs`, invece di ridurre ogni intervento a un semplice blocco `remove`.

## Stato V4

### V4.2
Ha introdotto waveform e protezione delle parole. Problema osservato: ottimizzare separatamente i due bordi poteva lasciare troppa aria.

### V4.3
Ha migliorato la compattezza delle giunzioni e corretto il problema specifico dello spazio eccessivo prima della ripartenza del parlato.

Il benchmark umano ha però mostrato che il problema maggiore resta anche **cosa rilevare/tagliare**, quindi non continuare a ottimizzare la sola waveform come se fosse la soluzione editoriale.

## Regola di sicurezza

Mai sovrascrivere la timeline originale.

Ogni tool o script che applica un piano deve creare una nuova timeline con nome esplicito. Questa regola dovrà essere imposta anche nel bridge MCP, non lasciata alla discrezione del modello.

## Prima acquisizione longform completa — 2026-09-14

La sorgente locale `Angolo delle recensioni (degli altri) ep 2.mp4` è stata trascritta senza API
esterne con `faster-whisper small`, CPU `int8`, lingua italiana e timestamp parola-per-parola.
Il file dura 3091,876 secondi; il risultato `ARPHE_TRANSCRIPT_V1` contiene 1375 segmenti e 7278
parole, con ultimo timestamp a 3090,66 secondi.

Il transcript resta locale sotto `%LOCALAPPDATA%\ARPHE\Longform04\transcripts` e non deve essere
committato: può contenere materiale editoriale o dati personali. La repository contiene soltanto
il trascrittore checkpointed `scripts/experiments/ARPHE_LONGFORM_TRANSCRIBE_01.py`; `*.transcript.json`
è escluso da Git.

Per l'integrazione MCP, una trascrizione longform non deve occupare una singola richiesta HTTP fino
alla fine. Il contratto previsto è asincrono: avvio job, lettura stato, metadati e chunk JSON. In
questo modo si evitano timeout 504 e ChatGPT carica soltanto le finestre temporali necessarie alla
decisione editoriale.

## Selezione episodio 2 e primo gate applicativo — 2026-09-15

L'intera trascrizione è stata analizzata in un'unica sessione editoriale. Sono stati approvati 11
estratti, tutti entro 3 minuti, per evitare cicli ripetuti di analisi e montaggio. Il piano validato
contiene 33180 frame a 30 fps (18:26 complessivi); il clip più lungo dura 5310 frame (2:57).

La prima applicazione deve creare esclusivamente:

- progetto `ARPHE_ANGOLO_RECENSIONI_EP2_CUTS`;
- master `ARPHE_EP2_PUBLISHABLE_MASTER_V1`;
- 11 timeline individuali, una per estratto.

Il piano iniziale è conservativo. L'approvazione semantica non equivale ancora a un edit point
definitivo: prima del PASS finale ogni confine deve essere raffinato e documentato secondo la
gerarchia `significato -> timestamp parola -> audio -> frame -> controllo audiovisivo`. Nessun
render o salvataggio automatico è incluso nel gate applicativo.

## Episodio 1: recupero di una seconda voce distante — 2026-09-17

La sorgente `Commenta la mia dieta (ep 1).mp4` ha due interlocutori registrati sulla stessa traccia;
la seconda voce è stata ripresa con il microfono troppo lontano. Il piano editoriale approvato crea
12 estratti ed è versionato in `plans/ARPHE_EP1_PUBLISHABLE_V1.json`.

Il bridge espone tre preset distinti:

- `ARPHE_DIALOGUE_CLEAN_V1`: pulizia conservativa per materiale già bilanciato;
- `ARPHE_DIALOGUE_LEVEL_V2`: livellamento dinamico per differenze moderate;
- `ARPHE_DIALOGUE_DISTANT_V3`: recupero più deciso con denoise, presenza, livellamento e limiter.

### Parametri standard di mixaggio (baseline 2026-09)

Questi valori sono lo standard operativo attuale, non un vincolo artistico definitivo:

- tutti i preset: passa-alto a `80 Hz`, conversione a PCM `s16`, stereo `48 kHz`;
- `CLEAN_V1`: `afftdn nr=8`, noise floor `-50 dB`, compressore soglia `0.125`, ratio `3:1`,
  attack `15 ms`, release `150 ms`, makeup `1.4`, limiter `0.891` (circa `-1 dB`);
- `LEVEL_V2`: `afftdn nr=8`, `dynaudnorm f=400:g=21:p=0.85:m=4:r=0.12:s=6:t=0.01:o=0.5`,
  compressore soglia `0.125`, ratio `2:1`, attack `15 ms`, release `150 ms`, makeup `1.1`,
  limiter `0.891`;
- `DISTANT_V3`: `afftdn nr=14`, noise floor `-48 dB`, EQ presenza `3.2 kHz`, Q `1.2`, gain `+3 dB`,
  `dynaudnorm f=300:g=15:p=0.82:m=8:r=0.16:s=8:t=0.008:o=0.5`, compressore soglia `0.10`,
  ratio `2.5:1`, attack `10 ms`, release `180 ms`, makeup `1.15`, boost `+6 dB`, limiter `0.8`.

La normalizzazione deve essere applicata all'intera sorgente prima dei tagli; il controllo umano
decide se il recupero V3 solleva troppo ambiente o riverbero. Questi parametri sono centralizzati in
`scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_worker.py` e sono modificabili dopo
un confronto A/B documentato.

Il confronto in Resolve ha confermato che V3 rende la voce distante più leggibile, ma non ricrea il
segnale mancante. Un test basato sui singoli turni ha sollevato eccessivamente ambiente e riverbero
ed è stato scartato. Per registrazioni future servono microfoni separati o un mixer; in postproduzione
va conservato il preset globale che supera l'ascolto umano, senza inseguire automaticamente ogni
passaggio debole.

Per gli estratti parlati usare transizioni minime: fade audio di 2–4 frame quando il taglio cade su
rumore ambiente, nessun fade se taglia una parola, e fade-out finale di 6–10 frame. Sul video basta
un ingresso diretto o una dissolvenza molto breve; l'uscita può usare 6–8 frame verso nero soltanto
quando la clip non prosegue in una end card. Le transizioni non devono mascherare edit point errati.

Il preset programmabile `create_edge_fade_test` realizza questo gate su una copia della timeline:
video 6 frame in / 8 frame out tramite Fusion e audio 4 frame in / 10 frame out tramite WAV PCM
derivato. Il gate V3 del 2026-09-18 ha verificato nero ai due estremi, progressione intermedia,
durata audio invariata e campioni iniziale/finale a zero. La prima versione supporta timeline con
esattamente una clip su V1 e una su A1.

Il pacchetto pubblicabile dell'episodio 1 è stato creato e salvato il 2026-09-18 nel progetto
`ARPHE_COMMENTA_DIETA_EP1_PUBLISH_V1`. Contiene il longform `ARPHE_EP1_LONGFORM_YOUTUBE_V1`, il
master `ARPHE_EP1_CUTS_MASTER_V1` e 12 timeline individuali. Longform e cut usano il WAV V3 e il
preset edge fade; nessun render è stato accodato. Il manifest operativo è
`plans/ARPHE_EP1_PUBLISH_PACKAGE_V1.json`.
