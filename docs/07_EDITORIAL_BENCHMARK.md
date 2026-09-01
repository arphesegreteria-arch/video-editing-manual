# 07 — Editorial Benchmark

## Scopo

Misurare il montaggio automatico contro un montaggio umano di riferimento, separando tre problemi diversi:

1. **decisione editoriale** — cosa va tolto;
2. **speech repair** — come ricucire false partenze, filler e frasi interrotte;
3. **boundary placement** — dove mettere fisicamente la lama.

La waveform non può correggere una decisione editoriale sbagliata: può solo raffinare un cut già sensato.

## Benchmark 01 — `blabla.mp4`

Reference umano esportato da Resolve tramite `ARPHE_EXPORT_REFERENCE_EDIT_02.py`.

Coverage reference:
- sorgente: `blabla.mp4`;
- FPS: 30;
- coverage: circa 1.7–2073.83 s;
- montaggio umano con molte pause accorciate, disfluenze rimosse e alcuni tagli concettuali.

Confronto iniziale contro `ARPHE_LONGFORM_SAFE_EDIT_PLAN_V3`:

- Precision: **0.522**
- Recall: **0.430**
- F1: **0.472**
- False positive: **197.5 s**
- False negative: **286.1 s**
- Boundary matched: **48 / 246**
- Mean boundary error: **625 ms**
- Median boundary error: **373 ms**

### Interpretazione

Il collo di bottiglia principale non è più soltanto l'audio alignment.

- Recall bassa: mancano molti tagli che il montatore umano esegue.
- Precision bassa: diversi tagli automatici non coincidono con le scelte editoriali umane.
- Boundary error alto: anche quando il tipo di intervento è corretto, la lama va ancora raffinata.

Priorità: migliorare prima il rilevamento delle decisioni editoriali e delle speech repair; solo dopo ottimizzare ulteriormente i bordi.

## ARPHE Editorial Profile v0.1

### Pause
- accorciare le pause chiaramente eccessive;
- non azzerare automaticamente gli spazi;
- preservare un ritmo umano e un respiro naturale tra attacco e attacco.

### `ehm`, `eeee`, `mmm` e vocalizzi
- **non rimuoverli sempre**;
- rimuoverli quando la frase prima/dopo può essere ricucita in modo naturale;
- conservarli quando svolgono una funzione espressiva o quando la rimozione rende il ritmo innaturale;
- i casi ambigui vanno raffinati tramite benchmark successivi.

### Filler linguistici (`allora`, `cioè`, `quindi`, `praticamente`, ecc.)
- non sono parole proibite;
- rimuoverli soltanto quando non svolgono realmente la funzione sintattica/discorsiva prevista e il ramo viene abbandonato;
- la decisione richiede contesto prima e dopo, non semplice keyword matching.

### False partenze / speech repair

Esempio:

`Questa specialità è... cioè... quello che volevo dire... questa specialità è molto importante.`

Obiettivo preferito quando possibile:

`Questa specialità è` + CUT + `molto importante.`

Quindi:
- conservare il prefisso valido della prima formulazione;
- eliminare il ramo abbandonato;
- riagganciare alla continuazione semanticamente corretta;
- usare word timestamps + audio per il posizionamento finale;
- se esistono più ricuciture plausibili, evitare un auto-cut aggressivo.

### Ripetizioni
- preferire la formulazione più chiara/completa;
- se la seconda formulazione completa corregge la prima, trattarla come speech repair, non solo come blocco duplicato.

### Tagli concettuali
- modello separato dai micro-cut;
- possono riguardare materiale grammaticalmente corretto ma inutile, ridondante o non funzionale al video;
- devono essere appresi e misurati contro reference umani, non derivati dalla sola waveform.

### Contenuto sensibile
- **FLAG ONLY**;
- non effettuare auto-cut per motivi reputazionali/sensibili;
- produrre timestamp + breve motivo del flag;
- decisione finale sempre umana.

## Protocollo Benchmark 02 — nuovo video

Obiettivo: verificare generalizzazione su materiale mai usato per calibrare il sistema.

### Regola anti-leakage

Il candidate automatico deve essere congelato **prima** di leggere il reference umano.

Ordine consigliato:

1. Registrare un nuovo video naturale.
2. Conservare l'MP4 originale intatto.
3. Generare transcript con word timestamps.
4. Generare e salvare il candidate automatico senza vedere il montaggio umano.
5. In parallelo, montare manualmente lo stesso video come risultato desiderato.
6. Esportare il reference con `ARPHE_EXPORT_REFERENCE_EDIT_02.py`.
7. Confrontare candidate e reference.
8. Classificare i mismatch per categoria:
   - pause;
   - vocalizzi;
   - filler senza funzione;
   - false partenze / speech repair;
   - ripetizioni;
   - tagli concettuali;
   - altro.
9. Aggiornare le regole solo dopo aver letto il report del secondo video.

## Ottimizzazione dei tempi

Per ogni iterazione non è necessario montare 35 minuti.

Per sviluppo rapido è sufficiente un campione nuovo di circa **8–12 minuti**, purché contenga parlato naturale e una quantità ragionevole di errori/disfluenze. Un secondo campione separato può essere usato come holdout.

Quando le metriche diventano stabili, eseguire un test completo su un longform più lungo.

## Metriche da tenere

- Precision e Recall sul tempo rimosso;
- F1;
- false positive seconds;
- false negative seconds;
- boundary match rate;
- mean / median boundary error;
- metriche separate per categoria editoriale.

Principio:

**non ottimizzare una singola V4.x “a sensazione”: congelare un candidate, confrontarlo con un reference umano e migliorare una categoria alla volta.**
