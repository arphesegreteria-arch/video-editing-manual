# 04 — Longform Workflow

## Obiettivo

Usare il contenuto parlato per creare un primo rough cut automatico, mantenendo separati:
- decisione editoriale;
- localizzazione delle parole;
- precisione fisica del punto di taglio;
- ricostruzione della timeline in Resolve.

## Pipeline corrente

1. Importare MP4 longform in Resolve.
2. Creare o mantenere una timeline originale intoccabile.
3. Trascrivere esternamente con `faster-whisper`.
4. Generare JSON `ARPHE_TRANSCRIPT_V1` con timestamp segmento + parola.
5. Analizzare il transcript per:
   - ripetizioni;
   - digressioni;
   - esitazioni;
   - concetti duplicati;
   - meta-discorso;
   - pause e navigazione inutili.
6. Generare un edit plan strutturato.
7. **Non usare i timestamp Whisper direttamente come lama.**
8. Raffinare i bordi con analisi locale dell'audio reale:
   - proteggere gli intervalli occupati dalle parole;
   - cercare un punto quieto vicino al timestamp editoriale;
   - privilegiare la conservazione del parlato rispetto all'aggressività del cut;
   - accorciare solo pause chiaramente troppo lunghe lasciando respiro.
9. Generare uno script Resolve con gli intervalli raffinati.
10. Python crea una nuova timeline usando solo gli intervalli da tenere.
11. Operatore revisiona l'intero longform.

## Principio fondamentale

**ChatGPT decide cosa tagliare; l'audio decide dove mettere la lama.**

Whisper è utile come mappa semantica e temporale, ma i suoi confini parola/segmento non sono abbastanza precisi per essere usati alla cieca come edit point.

## Diagnostica FPS

Prima di attribuire parole troncate a drift temporale, verificare:
- FPS della timeline;
- FPS del file sorgente;
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

```json
{
  "source_file": "blabla.mp4",
  "remove": [
    {"start": 222.5, "end": 238.2, "reason": "ripetizione"},
    {"start": 431.0, "end": 447.8, "reason": "digressione"}
  ]
}
```

## Stato V4

### V4.2
Ha introdotto analisi waveform e protezione delle parole. Problema osservato: ottimizzando separatamente i due bordi di una giunzione può restare troppa aria tra una frase e la successiva.

### V4.3
Candidato corrente da revisionare integralmente. Obiettivo:
- trattare la giunzione in modo più compatto;
- mantenere un piccolo respiro;
- evitare parole troncate;
- verificare che video e audio restino allineati dopo la ricostruzione.

Non considerare V4.3 validata finché non è stata guardata per intero.

## Regola di sicurezza

Mai sovrascrivere la timeline originale.
Creare sempre una nuova timeline con nome esplicito, ad esempio:

`LONGFORM_AUDIO_ALIGNED_CUT_04_3`
