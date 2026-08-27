# 04 — Longform Workflow

## Obiettivo

Usare il contenuto parlato per creare un primo rough cut automatico.

## Pipeline prevista

1. Importare MP4 longform in Resolve.
2. Creare timeline originale intoccabile.
3. Estrarre o leggere l'audio.
4. Trascrivere con timestamp.
5. Analizzare transcript:
   - ripetizioni;
   - digressioni;
   - esitazioni;
   - concetti duplicati;
   - pause inutili;
   - segmenti deboli.
6. Generare un edit plan strutturato.
7. Python crea una nuova timeline usando solo gli intervalli da tenere.
8. Operatore revisiona.

## Formato edit plan suggerito

```json
{
  "source": "LONGFORM_ORIGINAL",
  "remove": [
    {"start": 222.5, "end": 238.2, "reason": "ripetizione"},
    {"start": 431.0, "end": 447.8, "reason": "digressione"}
  ]
}
```

## Regola di sicurezza

Mai sovrascrivere la timeline originale.
Creare sempre una nuova timeline con nome esplicito, ad esempio:

`LONGFORM_AI_CUT_TEST_01`
