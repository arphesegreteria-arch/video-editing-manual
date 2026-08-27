# 05 — Operator Guide

## Principio

Assumere sempre che l'operatore:
- non sappia programmare;
- non conosca Resolve;
- non sappia cosa siano Fusion, Media Pool, Timeline, Tracker o Viewer.

Ogni procedura deve contenere:
- nome esatto della pagina;
- nome esatto del menu;
- nome esatto del nodo;
- dove cliccare;
- cosa deve comparire;
- quando aspettare;
- cosa NON toccare;
- quale script lanciare dopo.

## Procedura standard — tracking manuale

1. Eseguire lo script di setup da:
   `Workspace → Scripts → Utility`.
2. Cliccare **Fusion** nella barra inferiore.
3. Nel riquadro dei nodi, cliccare il nodo tracker indicato dallo script.
4. Se non è visibile nel Viewer, premere `1`.
5. Controllare di essere all'inizio del range indicato.
6. Nel Viewer trascinare il tracker sul dettaglio ad alto contrasto richiesto.
7. Controllare il rettangolo interno:
   deve contenere principalmente il dettaglio utile.
8. Controllare il rettangolo esterno:
   deve essere sufficientemente largo da consentire il movimento previsto.
9. Nell'Inspector del Tracker premere **Track Forward** una sola volta.
10. Attendere la fine dell'analisi.
11. Verificare che Resolve si fermi alla fine del range.
12. Non modificare altri nodi.
13. Eseguire lo script di applicazione successivo.

## Procedura longform — audio-aligned cut V4.3

Questa è una procedura di test tecnico. La versione finale destinata alla segreteria dovrà ridurre questi passaggi a un'interfaccia molto più semplice.

### Fase A — preparazione fuori da Resolve

1. Sul PC dove si trova il video, assicurarsi di avere:
   - il file MP4 originale;
   - il file `*_transcript.json` generato dal trascrittore;
   - il pacchetto Audio Align V4.3 estratto in una cartella.
2. Fare doppio click sul file `.bat` di avvio del pacchetto V4.3.
3. Se compare una finestra di scelta file, selezionare il video MP4 originale e premere **Apri**.
4. Se viene richiesto il transcript, selezionare il file `*_transcript.json` corrispondente allo stesso MP4.
5. Attendere che la finestra nera termini l'analisi audio. Non chiuderla durante il lavoro.
6. Alla fine verificare che venga generato uno script Resolve chiamato circa:
   `ARPHE_LONGFORM_AUDIO_ALIGNED_CUT_04_3.py`.
7. Copiare questo file in:
   `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`.

### Fase B — esecuzione in Resolve

1. Aprire DaVinci Resolve.
2. Aprire il progetto del longform.
3. In basso cliccare **Edit**.
4. Nel pannello Timeline, aprire la timeline originale completa, per esempio `Timeline 1`.
5. Verificare visivamente che il video originale sia intero e non già tagliato.
6. Non lanciare lo script da una timeline V4.2/V4.3 già generata.
7. In alto cliccare **Workspace**.
8. Cliccare **Scripts**.
9. Cliccare **Utility**.
10. Cliccare `ARPHE_LONGFORM_AUDIO_ALIGNED_CUT_04_3`.
11. Attendere la creazione della nuova timeline.
12. Controllare che la timeline originale sia ancora presente e inalterata.
13. Aprire la nuova timeline `LONGFORM_AUDIO_ALIGNED_CUT_04_3`.

### Fase C — revisione obbligatoria

Guardare il video dall'inizio alla fine e controllare soprattutto:
- se l'inizio di una parola viene mangiato;
- se la coda di una parola viene troncata;
- se una pausa rimane troppo lunga;
- se una pausa diventa innaturalmente corta;
- se audio e video sembrano realmente fuori sync;
- se il jump cut è brutto visivamente anche quando l'audio è corretto.

Se un punto è sbagliato, segnare il timecode della **nuova timeline** e non correggere alla cieca il file originale.

## Regola

Queste procedure vanno rispiegate click-per-click ogni volta che l'operatore deve effettuare un passaggio manuale.
Non rimandare semplicemente a "come fatto l'altra volta".
