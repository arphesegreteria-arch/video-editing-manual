# INDEX

## Documenti principali

| File | Scopo |
|---|---|
| `START_HERE.md` | Punto di ingresso per persone e ChatGPT |
| `CURRENT_STATE.md` | Stato tecnico corrente |
| `CHANGELOG.md` | Storico delle decisioni |
| `docs/01_SETUP_RESOLVE_PYTHON.md` | Setup Resolve/Python e cartelle script |
| `docs/02_SHORTFORM_WORKFLOW.md` | Pipeline shortform |
| `docs/03_TRACKING_FUSION.md` | Tracking, Fusion, yoyo e lezioni |
| `docs/04_LONGFORM_WORKFLOW.md` | Pipeline longform |
| `docs/05_OPERATOR_GUIDE.md` | Istruzioni click-per-click |
| `docs/06_TROUBLESHOOTING.md` | Problemi noti |
| `docs/07_EDITORIAL_BENCHMARK.md` | Benchmark umano, profilo editoriale e protocollo anti-leakage |

## Script validati

| Script | Stato | Utilizzo |
|---|---|---|
| `scripts/validated/ARPHE_AUTOCUT_TEST_01.py` | ✅ | Ricostruzione timeline con tagli |
| `scripts/validated/ARPHE_NUCLEAR_RESET_YOYO_08.py` | ✅ | Yoyo via Fusion BezierSpline |
| `scripts/validated/ARPHE_MANUAL_TRACK_SETUP_13A_V2.py` | ✅ | Prepara tracking manuale limitato a un range |
| `scripts/validated/ARPHE_TRACKED_YOYO_APPLY_13B_V2.py` | ✅ proof of concept | Legge tracking e applica yoyo |

## Benchmark / strumenti di valutazione

- `ARPHE_EXPORT_REFERENCE_EDIT_02.py`: esporta da Resolve un reference umano con kept/remove/joins.
- `ARPHE_COMPARE_CUTS_01.py`: confronta reference e candidate plan con metriche quantitative.

## Script parziali

Vedi `scripts/partial/`. Possono essere utili come riferimento ma non vanno usati come primitive di produzione senza verifica.

## Esperimenti

Vedi `scripts/experiments/`.
Servono come archivio tecnico e per evitare di ripetere strade già testate.
