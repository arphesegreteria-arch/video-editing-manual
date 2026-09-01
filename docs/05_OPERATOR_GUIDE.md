# 05 — Operator Guide

## Interfaccia target per la segreteria

La direzione prodotto corrente è: **la segreteria lavora in ChatGPT**.

Esperienza desiderata:

1. L'operatore indica/seleziona il video consentito.
2. Chiede a ChatGPT di trascriverlo e preparare il montaggio.
3. ChatGPT propone tagli, speech repair e flag.
4. Operatore e ChatGPT discutono i casi dubbi.
5. L'operatore approva.
6. ChatGPT usa la custom MCP app ARPHE.
7. Il bridge locale applica il piano in Resolve Studio creando una nuova timeline.
8. ChatGPT restituisce il riepilogo dell'operazione.

**Non è previsto che la segreteria usi una GUI ARPHE desktop separata come interfaccia primaria.**

Il bridge MCP, Python, Secure MCP Tunnel e i JSON sono infrastruttura tecnica e devono restare invisibili nel normale uso operativo.

## Principio per test e fallback manuali

Finché alcune capacità non sono automatizzate, assumere sempre che l'operatore:
- non sappia programmare;
- non conosca Resolve;
- non sappia cosa siano Fusion, Media Pool, Timeline, Tracker o Viewer.

Ogni procedura manuale deve contenere:
- nome esatto della pagina;
- nome esatto del menu;
- nome esatto del nodo;
- dove cliccare;
- cosa deve comparire;
- quando aspettare;
- cosa NON toccare;
- quale script/test lanciare dopo.

## Procedura standard — tracking manuale legacy

Questa procedura appartiene alla fase Free/proof-of-concept. Con Studio va rivalutato prima il tracking automatico via API.

1. Eseguire lo script di setup da `Workspace -> Scripts -> Utility`.
2. Cliccare **Fusion** nella barra inferiore.
3. Nel riquadro dei nodi, cliccare il nodo tracker indicato dallo script.
4. Se non è visibile nel Viewer, premere `1`.
5. Controllare di essere all'inizio del range indicato.
6. Nel Viewer trascinare il tracker sul dettaglio ad alto contrasto richiesto.
7. Controllare il rettangolo interno: deve contenere principalmente il dettaglio utile.
8. Controllare il rettangolo esterno: deve essere sufficientemente largo da consentire il movimento previsto.
9. Nell'Inspector del Tracker premere **Track Forward** una sola volta.
10. Attendere la fine dell'analisi.
11. Verificare che Resolve si fermi alla fine del range.
12. Non modificare altri nodi.
13. Eseguire lo script di applicazione successivo.

## Procedura longform — audio-aligned cut V4.3 legacy

Questa è una procedura di test tecnico precedente al bridge MCP. Resta documentata per riproducibilità e fallback.

### Fase A — preparazione fuori da Resolve

1. Sul PC assicurarsi di avere:
   - MP4 originale;
   - `*_transcript.json`;
   - pacchetto Audio Align V4.3 estratto.
2. Fare doppio click sul `.bat` di avvio V4.3.
3. Se richiesto, selezionare l'MP4 e premere **Apri**.
4. Se richiesto, selezionare il transcript corrispondente.
5. Attendere l'analisi audio senza chiudere la finestra.
6. Verificare che venga generato `ARPHE_LONGFORM_AUDIO_ALIGNED_CUT_04_3.py`.
7. Copiarlo in `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`.

### Fase B — esecuzione in Resolve

1. Aprire DaVinci Resolve.
2. Aprire il progetto longform.
3. In basso cliccare **Edit**.
4. Aprire la timeline originale completa, per esempio `Timeline 1`.
5. Verificare che il video originale sia intero e non già tagliato.
6. Non lanciare lo script da una timeline V4.2/V4.3 già generata.
7. In alto cliccare **Workspace**.
8. Cliccare **Scripts**.
9. Cliccare **Utility**.
10. Cliccare `ARPHE_LONGFORM_AUDIO_ALIGNED_CUT_04_3`.
11. Attendere la nuova timeline.
12. Controllare che la timeline originale sia ancora presente e inalterata.
13. Aprire `LONGFORM_AUDIO_ALIGNED_CUT_04_3`.

### Fase C — revisione obbligatoria

Controllare soprattutto:
- inizio parola mangiato;
- coda parola troncata;
- pause troppo lunghe/corte;
- vero fuori-sync A/V;
- jump cut visivamente brutto anche con audio corretto.

Se un punto è sbagliato, segnare il timecode della **nuova timeline**.

## Setup Studio per i nuovi test esterni

1. Aprire Resolve Studio.
2. Aprire `Preferences`.
3. Selezionare **System**.
4. Cliccare **General**.
5. Impostare `External scripting using` su **Local**.
6. Cliccare **Save**.
7. Lasciare aperto il progetto/timeline di test.
8. Eseguire il probe esterno richiesto.

Il test di lettura esterno è già validato. Il prossimo test controllato è `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`.

## Regola

Le procedure manuali sono strumenti di test/fallback, non la UX finale. Quando l'operatore deve comunque intervenire in Resolve, rispiegare sempre il passaggio click-per-click e non rimandare semplicemente a "come fatto l'altra volta".
