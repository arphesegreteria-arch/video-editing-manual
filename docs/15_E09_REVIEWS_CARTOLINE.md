# E09 — Recensioni MioDottore come cartoline in movimento

Il nuovo piano è `plans/ARPHE_E09_REVIEWS_CARTOLINE_V1.json`. Contiene cinque recensioni originali pubblicate su MioDottore e una CTA finale. La selezione bilancia due testimonianze di medicina estetica e tre testimonianze su ambiente, personale e organizzazione.

## Kit grafico applicato

Il repository non contiene ancora un export autonomo dei CSS del sito; fino alla consegna del kit ufficiale usiamo la palette già canonizzata nel Creative Bridge: ivory `#F7F2E8`, cream `#EFE3CF`, beige `#D7C2A6`, burgundy `#6C2438`, warm brown `#8A6248`, dark brown `#3A2923`. Il canvas delle sequenze recensioni usa beige, così lo sfondo non appare bianco e le card cream restano ben separate. Il modulo grafico resta quindi parametrico e sostituibile senza cambiare le recensioni.

Ogni cartolina deve avere fondo cream, bordo/ombra beige molto leggeri, testo dark brown, stelle e piccoli accenti burgundy. Il testo originale non va corretto: si può andare a capo, ma non cambiare parole, punteggiatura o senso.

Le recensioni non mostrano sotto né il nome del medico né la dicitura “Paziente verificato”: il messaggio resta anonimo e centrato sul contenuto. L'apertura è un piccolo pannello editoriale: canvas beige, pannello cream dagli angoli morbidi, micro-etichetta warm brown, titolo Satoshi Black su due righe (“Dicono / di noi”) e sottotitolo “Recensioni su MioDottore”. Non usa una riga verticale accanto alla D, perché visivamente sembrava un segno accidentale.

## Transizione “cartoline che scorrono”

La sequenza è 16:9, 1920×1080, 30 fps. Una card occupa circa il 78% della larghezza e il 34% dell'altezza. La sequenza automatica usa 3–5 secondi per recensione, in base alla quantità di testo, con 10 frame di sovrapposizione tra card. Per evitare la sfocatura percepita nella prima entrata non usa più lo stack ruotato: applica ingressi singoli `ARPHE_ELEGANT_REVEAL`, da sinistra, di 8 frame, senza overshoot. La CTA finale ARPHÈ usa il fondo burgundy del kit e riceve automaticamente almeno 4 secondi.

## Variante Instagram/Reel

La variante Reel è nativa 9:16, 1080×1920, 30 fps: non è un crop della composizione orizzontale. Il bridge riconosce la timeline verticale, porta la card all'86% della larghezza, aumenta il corpo del testo e allarga il pannello iniziale. Mantiene Satoshi, le durate automatiche 3–5 secondi e la CTA finale; ogni formato resta una timeline ARPHÈ distinta.

La variante di riferimento è `ARPHE_E09_REELS_MIODOTTORE_V3` / `ARPHE_COMP_5923667C4E`, documentata in `plans/ARPHE_E09_REELS_MIODOTTORE_V1.json`. Contiene le stesse cinque recensioni della sequenza orizzontale, ma un layout nativo per Reel: canvas beige del kit, card cream, Satoshi e CTA burgundy. La scala tipografica è mobile-first: intro, card e CTA sono stati catturati e verificati senza modificare la V6 orizzontale.

Prima applicazione prevista:

1. creare progetto e timeline nuovi;
2. creare le cinque card con `create_review_sequence_v2` oppure, se serve controllo singolo, `add_review_card`;
3. applicare `animate_card_entry` singolarmente con `ARPHE_ELEGANT_REVEAL`;
4. aggiungere CTA in una finestra separata;
5. catturare frame iniziali, intermedi e finali per verificare leggibilità, ordine e assenza di testo tagliato;
6. solo dopo autorizzazione, salvare/renderizzare.

La V3 è stata applicata alla nuova timeline `ARPHE_E09_REVIEWS_CARTOLINE_16X9_V3` e alla composition `ARPHE_COMP_EDBE5399C6`; i frame catturati nella finestra 0–149 risultano nitidi e leggibili. Dal 2026-09-24 il bridge usa un carrier tecnico interno per ogni composizione oltre 150 frame: la timeline eredita automaticamente la durata richiesta (fino a 9.000 frame / 5 minuti), senza trim manuale da parte delle segretarie. Se non viene indicata una durata, calcola il tempo di lettura per ogni recensione: 3–5 secondi, più una CTA finale di almeno 4 secondi. Il carrier non contiene riprese né dati e viene coperto dal canvas ARPHÈ in Fusion.

## Prova definitiva — V4

La timeline `ARPHE_E09_REVIEWS_CARTOLINE_FINAL_V4` usa le cinque recensioni originali del piano, l'intro `Dicono di noi / su MioDottore`, le entrate `ARPHE_ELEGANT_REVEAL` da sinistra (8 frame, senza overshoot) e la CTA `Scopri Arphè / Prenota la tua visita`. La variante approvata per la revisione è `ARPHE_E09_REVIEWS_CARTOLINE_FINAL_V6` / `ARPHE_COMP_5062AADC95`: pannello editoriale, 3–5 secondi per card, 3 secondi di intro, CTA di 4 secondi e durata totale di 810 frame / 27 secondi. Usa Satoshi (Regular, Medium, Bold e Black), rimuove la riga verticale che appariva attaccata alla D e dispone il titolo su due righe. Le catture di intro, due card e CTA sono nitide. Le card restano anonime, senza medico né dicitura “Paziente verificato”.
