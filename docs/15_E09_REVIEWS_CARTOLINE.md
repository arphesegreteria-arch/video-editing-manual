# E09 — Recensioni MioDottore come cartoline in movimento

Il nuovo piano è `plans/ARPHE_E09_REVIEWS_CARTOLINE_V1.json`. Contiene cinque recensioni originali pubblicate su MioDottore e una CTA finale. La selezione bilancia due testimonianze di medicina estetica e tre testimonianze su ambiente, personale e organizzazione.

## Kit grafico applicato

Il repository non contiene ancora un export autonomo dei CSS del sito; fino alla consegna del kit ufficiale usiamo la palette già canonizzata nel Creative Bridge: ivory `#F7F2E8`, cream `#EFE3CF`, beige `#D7C2A6`, burgundy `#6C2438`, warm brown `#8A6248`, dark brown `#3A2923`. Il modulo grafico resta quindi parametrico e sostituibile senza cambiare le recensioni.

Ogni cartolina deve avere fondo cream, bordo/ombra beige molto leggeri, testo dark brown, stelle e piccoli accenti burgundy. Il testo originale non va corretto: si può andare a capo, ma non cambiare parole, punteggiatura o senso.

## Transizione “cartoline che scorrono”

La sequenza è 16:9, 1920×1080, 30 fps. Una card occupa circa il 78% della larghezza e il 34% dell'altezza. Le card entrano da sinistra, restano leggibili, poi escono a destra; l'ingresso successivo è sfalsato di 12 frame. Il preset da usare è `ARPHE_PAPER_STACK`, con easing morbido e rotazione minima o nulla. La CTA finale resta più a lungo e non viene trattata come recensione.

Prima applicazione prevista:

1. creare progetto e timeline nuovi;
2. creare le cinque card con `create_review_sequence_v2` oppure, se serve controllo singolo, `add_review_card`;
3. applicare `animate_review_stack` con il preset cartolina;
4. aggiungere CTA in una finestra separata;
5. catturare frame iniziali, intermedi e finali per verificare leggibilità, ordine e assenza di testo tagliato;
6. solo dopo autorizzazione, salvare/renderizzare.

Il primo tentativo è volutamente un test visivo. Non modifica timeline esistenti e non pubblica nulla.
