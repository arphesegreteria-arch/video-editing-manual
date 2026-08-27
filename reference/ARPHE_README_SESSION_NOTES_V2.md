# ARPHE Video Automation — Session Notes v2

## REGOLA FONDAMENTALE: operatori non tecnici
Ogni passaggio manuale in DaVinci Resolve deve essere spiegato click-per-click assumendo zero conoscenze di Resolve.

## REGOLA FONDAMENTALE: tracking limitato nel tempo
MAI lanciare Track Forward sull'intera clip quando il soggetto da seguire esiste solo in un segmento.

Prima del tracking:
1. determinare l'intervallo esatto dell'effetto;
2. convertire l'intervallo in frame usando gli FPS della timeline;
3. impostare automaticamente COMPN_RenderStart e COMPN_RenderEnd nella Fusion Comp;
4. portare il playhead al RenderStart;
5. solo a quel punto chiedere all'operatore di premere Track Forward.

Esempio corrente:
- FPS timeline: circa 29.97
- tracking labbro: 25.30s -> 27.20s
- frame approssimativi: 758 -> 815

Motivo:
un tracker lasciato correre sull'intera clip puo perdere il soggetto dopo un cambio scena e agganciarsi ad altri dettagli/labbra/volti.

## Stato tecnico validato
- Cut automatici via ricostruzione timeline: VALIDATO
- Transform statico via TimelineItem.SetProperty: VALIDATO
- Fusion Transform: VALIDATO
- BezierSpline su Transform.Size: VALIDATO
- effetto yoyo zoom: VALIDATO
- creazione Tracker Fusion via Python: VALIDATO
- Tracker su ramo laterale senza alterare MediaOut: VALIDATO come architettura
- trigger TrackForward automatico via FusionScript nella build corrente: NON AFFIDABILE
- tracking nativo manuale con range limitato + lettura successiva da Python: STRATEGIA CORRENTE

## Procedura manuale tracking da documentare sempre
1. Lanciare lo script di setup.
2. Aprire la pagina Fusion.
3. Selezionare il nodo tracker indicato dallo script.
4. Premere 1 per mostrarlo nel Viewer, se necessario.
5. Controllare che il playhead sia all'inizio del range indicato.
6. Trascinare il pattern sul dettaglio ad alto contrasto da seguire.
7. Controllare che il pattern interno contenga solo il dettaglio utile.
8. Controllare che la search area esterna permetta il movimento atteso.
9. Premere Track Forward una sola volta.
10. Attendere che Resolve raggiunga la fine del range impostato.
11. NON modificare altri nodi.
12. Lanciare lo script di applicazione successivo.

## Lezione tracking vs framing estetico
- Il punto di tracking deve essere scelto per stabilita/contrasto, non per forza come centro estetico dell'effetto.
- Il framing finale deve poter applicare un offset separato rispetto al punto tracciato.
- Nel test labbro: tracking sul labbro superiore era accettabile come punto stabile; il problema residuo era il reframing ai picchi dello zoom.
- Proof of concept promosso: tracking nativo manuale -> lettura path da Python -> yoyo automatico.
- Non insistere sulla perfezione del singolo test se l'architettura e' gia validata: consolidare la lezione nel framework.

## Nuovo filone: longform da Premiere
- Obiettivo: importare timeline Premiere via XML in Resolve, trascrivere il contenuto, usare la trascrizione per proporre tagli e applicarli via script.
- Per ogni passaggio manuale in Resolve, documentare istruzioni click-per-click assumendo zero conoscenze del software.
