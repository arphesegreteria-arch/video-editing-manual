# 15 — Sottotitoli Fusion ARPHÈ

## Grafia del marchio

La grafia corretta è **Arphé**, oppure **ARPHÉ** nei testi tutti maiuscoli. La e finale ha sempre l’**accento acuto**, anche in corsivo: `é` (Unicode U+00E9), `É` (Unicode U+00C9). Non usare l’accento grave `è`/`È`, il circonflesso, un apostrofo al posto dell’accento o una lettera non accentata nel testo visibile. Normalizzare i cue in Unicode NFC e verificare il carattere prima del render.

La regola deriva dalla grafia presente nelle istruzioni ufficiali `brand-guidelines/ISTRUZIONI-PER-AI.md`. Se documenti storici o precedenti cue riportano ARPHÈ, prevale questa grafia corretta. I nomi tecnici ASCII di file, cartelle, progetti e tool restano invariati. La correzione del marchio appartiene ai dati editoriali e alla documentazione; non aggiungere sostituzioni dedicate al marchio nel codice del bridge.

## Stato

**SUPPORTED / APPROVATO** su `PC_PERSONALE` il 31 ottobre 2026.

Evidenza visuale approvata:
`ARPHE_ADV_RICERCA_PERSONALE_REVIEW_V4_TWO_SIZES.mp4`.

Il percorso corretto è l'azione generica `CAPTIONS` del workflow Vertical Social, eseguita dopo il
picture lock su una nuova timeline provvisoria. Non creare tool MCP, preset, comandi o eccezioni
dedicati a un singolo video.

## Contratto grafico

- Testo sempre maiuscolo in **Satoshi Bold**.
- Al massimo una parola rilevante per frase in **Satoshi Bold Italic**.
- Esistono soltanto due misure Fusion: `0.050` standard e `0.065` evidenza.
- Vietate misure intermedie, fitting dinamico parola per parola e riduzioni dell'intero blocco.
- L'intera frase resta visibile; lo sfondo bordeaux karaoke passa dietro la parola pronunciata.
- Lo sfondo segue la larghezza reale della parola e aggiunge `0.012` di padding orizzontale (raffinamento generale richiesto l’11 novembre 2026).
- La distanza minima fra card/parole è `0.014`.
- Una frase usa una riga quando entra nella safe area; altrimenti usa al massimo due righe
  centrate e bilanciate.
- Se una frase non entra neppure in due righe, viene divisa in gruppi temporali leggibili senza
  cambiare la grandezza del carattere.
- Le due righe devono restare nella safe area verticale sia in posizione `LOWER` sia `UPPER`.

La fonte di verità estetica corrispondente è
`C:\ARPHE\arphe-graphic-kit\VIDEO-EDITING.md`.

## Contratto operativo

1. Trascrivere l'audio della timeline e conservare i timing parola per parola.
2. Completare tagli, reframing, color e Fairlight prima dei sottotitoli.
3. Creare/approvare un piano Vertical Social con azione `CAPTIONS` `POST_LOCK`.
4. Creare una timeline provvisoria non distruttiva e marcarne il picture lock.
5. Applicare il grafo Fusion generico e verificare il read-back del testo.
6. Catturare almeno un frame a una riga, uno a due righe e tutte le parole lunghe/enfatizzate.
7. Renderizzare tramite batch Deliver isolato; verificare l'output prima dell'upload.

Il processo non deve modificare audio, color, montaggio o testo trascritto quando viene rigenerato
soltanto il layer dei sottotitoli.

## Regressioni obbligatorie

La suite deve verificare:

- insieme delle misure limitato a `{0.050, 0.065}`;
- `DERMATOLOGO`, `POLIAMBULATORIO`, `COLLABORAZIONE` e `CONTATTACI` interamente dentro le card;
- una e due righe senza collisioni e dentro la safe area;
- conservazione di ordine e range temporali delle parole;
- posizione verticale distinta per ogni riga nel grafo Fusion;
- separazione temporale delle frasi troppo dense.

Modulo generico:
`scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_captions.py`.

Test:
`scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_captions.py`.

## Interlinea karaoke compatta

Raffinamento generale richiesto l’11 novembre 2026: avvicinare anche le due righe. In posizione LOWER, distanza fra i centri delle righe `0.060` e altezza card `0.050`; in UPPER `0.055`/`0.045`. Resta uno spazio verticale libero di `0.010` tra i rettangoli delle card (19,2px su1920px). Il testo mantiene font, grandezze, larghezze e timing approvati. Le card a riga singola mantengono altezza e posizione precedenti.

La funzione generale restituisce `card_height` per parola e il grafo Fusion usa quel valore nella maschera. Non ridurre la sola distanza fra righe lasciando card alte: verificare entrambi i fondi attivi, accenti e corsivi nelle catture native. Nessun riferimento al progetto nel bridge. Patch/test in `reference/patches/2026-11-11-caption-line-spacing/`.

