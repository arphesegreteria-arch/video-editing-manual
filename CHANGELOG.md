# CHANGELOG

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
- affidarsi al trigger automatico `TrackForward` via FusionScript nella build corrente.

### Regole aggiunte
- mai modificare l'originale;
- tracking sempre limitato al range utile;
- tracking anchor separato dal centro estetico;
- ogni passaggio manuale spiegato click-per-click.
