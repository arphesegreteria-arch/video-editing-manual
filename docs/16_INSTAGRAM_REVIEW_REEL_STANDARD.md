# 16 — Standard ARPHÈ: Reel Instagram con recensioni

Questo è il modello operativo per creare una nuova sequenza recensioni per Instagram. È basato
sulla prova visuale `ARPHE_E09_REELS_MIODOTTORE_V2` e deve essere riusato, non ricostruito da zero.

## Risultato previsto

- formato nativo Reel: **1080×1920, 30 fps, 9:16**;
- fino a otto recensioni originali;
- apertura editoriale, card in sequenza e CTA conclusiva;
- durata automatica: **3–5 secondi per card**, tre secondi di intro e quattro di CTA;
- durata tipica per cinque recensioni: circa **27 secondi**;
- timeline e composition nuove per ogni consegna, senza sovrascrivere esperimenti precedenti.

Non usare la versione 16:9 come sorgente da ritagliare: il Reel nasce verticale.

## Regole contenuto

1. Usare solo recensioni originali approvate da ARPHÈ e riportarne il testo senza riscriverlo.
2. Ogni recensione richiede `text` e `stars`; `small_label` va omesso.
3. Non mostrare nomi del medico, nome paziente, “Paziente verificato”, data, prestazione o altra
   metadata di attribuzione sotto la card.
4. Non inventare recensioni, risultati clinici, promesse o claim sanitari.
5. Prima della scrittura in Resolve, ChatGPT deve riepilogare le recensioni selezionate e ottenere
   l'approvazione editoriale.

Il template senza dati reali è `plans/ARPHE_INSTAGRAM_REVIEW_REEL_TEMPLATE.json`.

## Kit grafico canonico

| Elemento | Standard |
|---|---|
| Canvas | beige `#D7C2A6` |
| Cartolina | cream `#EFE3CF`, angoli morbidi, ombra nera molto leggera |
| Testo | dark brown `#3A2923` |
| Stelle e titolo | burgundy `#6C2438` |
| Micro-etichetta e sottotitolo | warm brown `#8A6248` |
| Font | Satoshi: Regular per corpo, Medium per etichette, Bold/Black per titoli |

L'apertura usa un pannello cream centrato sul canvas beige: micro-etichetta `ARPHE
POLIAMBULATORIO`, titolo su due righe `Dicono / di noi` e sottotitolo `Recensioni su MioDottore`.
Non aggiungere una barra verticale accanto al titolo: nella prima prova appariva accidentalmente
attaccata alla lettera “D”.

Le card verticali hanno larghezza relativa 86%, altezza 40% e testo più grande del modello 16:9.
Il contenuto resta nell'area centrale: evitare elementi essenziali ai bordi superiore e inferiore,
dove l'interfaccia Instagram può sovrapporsi.

## Procedura standard

1. Verificare che `CAP_REVIEW`, `CAP_FUSION` e `CAP_MOTION` siano attive e che il bridge risponda
   `ready`.
2. Creare o selezionare un progetto ARPHÈ autorizzato.
3. Creare una timeline con nome `ARPHE_<SERIE>_REELS_V<n>`, 1080×1920, 30 fps.
4. Chiamare `create_review_sequence_v2` con `total_duration_frames: 0`, `style_role: cream`,
   l'intro e la CTA dello standard. Omettere `small_label` da ogni recensione.
5. Applicare `animate_card_entry` a ogni card: `ARPHE_ELEGANT_REVEAL`, direzione `left`,
   `ease_out`, 8 frame, `settle: false`.
6. Catturare almeno un frame dell'intro, una card breve, una card lunga e la CTA. Il playhead deve
   risultare ripristinato.
7. Chiedere approvazione visuale. Solo dopo un'autorizzazione esplicita salvare il progetto o
   renderizzare.

## Naming e verifiche

| Oggetto | Regola |
|---|---|
| Timeline | `ARPHE_<SERIE>_REELS_V<n>` |
| Fusion item | `ARPHE_<SERIE>_REELS_<VARIANTE>_V<n>` |
| Piano | `plans/ARPHE_<SERIE>_REELS_V<n>.json` |
| Catture | intro, card breve, card lunga, CTA |

La prova di riferimento è `ARPHE_E09_REELS_MIODOTTORE_V2`, composition
`ARPHE_COMP_8E3B74BD9D`, durata 810 frame / 27 secondi. Non costituisce un template di contenuto:
le prossime recensioni devono essere nuovamente selezionate e approvate.

## Limiti e miglioramenti futuri

Questo standard genera grafiche direttamente in Fusion; Canva non è necessario. Asset esterni
(fotografie, logo vettoriale, texture o illustrazioni) possono essere introdotti in un secondo
momento, ma non devono sostituire il layout, i font e le regole editoriali qui definite.

La cattura diagnostica JPEG serve a verificare struttura e leggibilità, non a valutare la qualità
di compressione finale: prima della pubblicazione il render deve avere una verifica dedicata.
