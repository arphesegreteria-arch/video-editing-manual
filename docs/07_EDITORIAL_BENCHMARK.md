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
- Boundary error alto: anche quando l'intervento è corretto, la lama va ancora raffinata.

Priorità: migliorare prima decisioni editoriali e speech repair; poi ottimizzare ulteriormente i bordi.

## ARPHE Editorial Profile v0.1

### Pause
- accorciare le pause chiaramente eccessive;
- non azzerare automaticamente gli spazi;
- preservare ritmo umano e respiro naturale.

### `ehm`, `eeee`, `mmm` e vocalizzi
- **non rimuoverli sempre**;
- rimuoverli quando la frase prima/dopo può essere ricucita naturalmente;
- conservarli quando svolgono una funzione espressiva o la rimozione rende il ritmo innaturale;
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
- se esistono più ricuciture plausibili, evitare auto-cut aggressivi.

### Ripetizioni
- preferire la formulazione più chiara/completa;
- se la seconda formulazione corregge la prima, trattarla come speech repair, non solo come blocco duplicato.

### Tagli concettuali
- livello separato dai micro-cut;
- possono riguardare materiale grammaticalmente corretto ma inutile, ridondante o non funzionale al video;
- devono essere misurati contro reference umani, non derivati dalla sola waveform.

### Contenuto sensibile
- **FLAG ONLY**;
- non effettuare auto-cut per motivi reputazionali/sensibili;
- produrre timestamp + breve motivo del flag;
- decisione finale umana.

## Protocollo Benchmark 02 — podcast excerpt autonomo

Obiettivo: verificare generalizzazione su materiale mai usato per calibrare il sistema senza processare ogni volta un podcast completo.

### Sorgente canonica

1. Individuare nel podcast un passaggio interessante, idealmente circa 8–15 minuti.
2. Esportarlo come MP4 autonomo **prima** di qualsiasi montaggio editoriale.
3. Dal momento dell'export, dimenticare il timecode dell'episodio completo.
4. L'estratto parte da `00:00` ed è l'unica sorgente canonica dell'esperimento.

Non fare somme/offset verso il podcast originale durante il benchmark: aggiungono rischio senza migliorare la misura.

### Regola anti-leakage

Il candidate automatico deve essere congelato **prima** di leggere il reference umano.

Ordine:
1. creare `E05_SOURCE_EXCERPT.mp4`;
2. generare `E05_TRANSCRIPT.json` con word timestamps;
3. generare e salvare `E05_CANDIDATE_V1.json` senza vedere il montaggio umano;
4. montare manualmente la stessa SOURCE_EXCERPT come risultato desiderato;
5. esportare `E05_REFERENCE.json` con `ARPHE_EXPORT_REFERENCE_EDIT_02.py`;
6. confrontare candidate e reference;
7. generare `E05_REPORT.txt`;
8. classificare i mismatch per:
   - pause;
   - vocalizzi;
   - filler senza funzione;
   - false partenze / speech repair;
   - ripetizioni;
   - tagli concettuali;
   - altro;
9. aggiornare le regole solo dopo il report.

## Metriche da tenere

- Precision e Recall sul tempo rimosso;
- F1;
- false positive seconds;
- false negative seconds;
- boundary match rate;
- mean / median boundary error;
- metriche separate per categoria editoriale.

## Regola di sviluppo

**Non ottimizzare una versione “a sensazione”: congelare un candidate, confrontarlo con un reference umano e migliorare una categoria alla volta.**

Il benchmark editoriale rimane indipendente dal canale di esecuzione: oggi può usare script/JSON; nell'architettura target ChatGPT potrà richiamare gli stessi passaggi tramite MCP senza cambiare la metodologia di valutazione.
