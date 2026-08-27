# ARPHE Video Automation — Session Notes

## Regola operatore non tecnico
Ogni volta che il workflow richiede un intervento manuale in DaVinci Resolve, il README deve spiegare il passaggio click-per-click assumendo che l'operatore non sappia usare Resolve.

In particolare, per il tracking Fusion:
1. indicare esattamente quale pagina aprire;
2. indicare esattamente quale nodo selezionare;
3. indicare come mostrare il nodo nel Viewer;
4. indicare dove trascinare il tracker;
5. indicare quale pulsante Track premere;
6. indicare cosa aspettare a fine analisi;
7. indicare quale script lanciare dopo.

## Stato tecnico attuale
- Cut automatici via ricostruzione timeline: validati.
- Fusion Transform / BezierSpline: validati.
- Yoyo zoom: validato.
- Tracker creato via script: validato.
- Trigger automatico TrackForward via FusionScript nella build corrente: non affidabile.
- Strategia corrente: tracking nativo manuale in Fusion, poi lettura del path da Python e applicazione automatica dello yoyo.
