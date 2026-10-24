# Stabilizzazione verticale equilibrata

## Scopo

Il bridge può correggere una ripresa che oscilla senza stimare automaticamente soggetto o
orizzonte. L'azione generica `REFRAME` accetta misure esplicite per:

- rotazione, tramite `rotation_keys` e `BezierSpline` Fusion;
- posizione bidimensionale, tramite `center_keys` e `Path` Fusion;
- ingrandimento di sicurezza, tramite `zoom`.

Ogni lista di punti deve essere ordinata, restare nel range approvato e ancorare il primo e
l'ultimo frame. L'applicazione avviene esclusivamente su una timeline provvisoria posseduta dal
bridge e ogni valore viene riletto da Resolve prima di dichiarare l'azione `VERIFIED`.

## Verifica reale su PC personale — 2026-10-24

- progetto: `ARPHE_PEELING_ADV_TEST_20261023`;
- sorgente preservata: `ARPHE_PEELING_SOURCE_R4_20261023`;
- timeline provvisoria: `__ARPHE_VERTICAL_VERTICAL_9957F4FFC8BC43E0B5B333FF4B4BFC03`;
- piano verificato: `vertical_9957f4ffc8bc43e0b5b333ff4b4bfc03`;
- durata: 732 frame a 30 fps;
- intervento: 26 punti posizione, 7 punti rotazione, zoom `1.08`;
- deriva verticale misurata prima: 40,69 px;
- deriva verticale misurata dopo: 12,12 px;
- inclinazione misurata dopo: da -0,32° a +0,27°;
- struttura riletta: una clip V1 e una clip A1, entrambe 108000–108732, nessun taglio;
- sorgente riletta: `peeling_test_20261023.mp4` per video e audio;
- controllo visivo: frame 0, 450, 540 e 731 senza deformazioni o bordi scoperti nell'area immagine.

Il progetto non è stato salvato e non è stato eseguito alcun render. Il PC segreteria non è stato
aggiornato.

## Nota sul difetto individuato

`Center` è un parametro XY. Fusion accetta apparentemente anche `BezierSpline`, ma in Resolve 21
la lettura di ogni frame restituisce l'ultimo punto inserito. Per questo `Center` deve usare
`comp.Path()`. Il bridge fallisce chiuso e ora restituisce anche frame, valore atteso e valore letto
quando il read-back non coincide.

## Rollout successivo su PC segreteria

Eseguire il trasferimento solo dopo approvazione esplicita:

1. aggiornare la checkout/release della segreteria al commit approvato;
2. creare un backup del bridge e della configurazione locale della segreteria;
3. installare specificando `PC_SEGRETERIA` e il suo `creative_config.json`, senza copiare credenziali
   o configurazioni del PC personale;
4. riavviare il servizio della sola workstation segreteria;
5. verificare `ping`, `workstation_id=PC_SEGRETERIA` e `CAP_VERTICAL_SOCIAL=true`;
6. eseguire prima un piano di prova su un progetto separato e non salvare finché read-back e
   fotogrammi non sono stati controllati.
