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

## Regola

Questa procedura va ripetuta/rispiegata ogni volta che un operatore deve effettuare un tracking.
Non rimandare semplicemente a "come fatto l'altra volta".
