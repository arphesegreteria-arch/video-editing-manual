# 04 — Longform Workflow

## Obiettivo

Usare il contenuto parlato per creare un primo rough cut automatico, mantenendo separati:
- decisione editoriale;
- localizzazione delle parole;
- precisione fisica del punto di taglio;
- esecuzione deterministica in Resolve.

## Pipeline editoriale corrente

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
