# 17 — Workflow ARPHÉ per montaggi affidati alla segreteria

## Scopo

Questo documento trasforma le revisioni svolte con Alessio in regole generiche e riutilizzabili.
Serve a ottenere sul `PC_SEGRETERIA` lo stesso percorso decisionale usato sul `PC_PERSONALE`,
senza creare comandi, preset o eccezioni dedicati a un singolo video.

La fonte estetica resta `C:\ARPHE\arphe-graphic-kit\VIDEO-EDITING.md`. Questo documento descrive
ordine operativo, criteri editoriali, controlli e passaggio tra workstation. In caso di conflitto,
prevalgono il Graphic Kit per la resa visiva e i contratti/test del bridge per la sicurezza.

## Principi non negoziabili

1. Il sorgente e ogni timeline approvata restano intatti. Ogni fase sostanziale crea una copia
   chiaramente nominata.
2. Il bridge espone funzioni generiche. Frasi, timecode, nomi, immagini e scelte editoriali sono
   dati del piano; non diventano nuovi tool o rami di codice.
3. La trascrizione descrive l'audio effettivamente presente in timeline e guida tagli, timing,
   B-roll e sottotitoli.
4. I sottotitoli arrivano dopo il picture lock. Rigenerarli non deve cambiare montaggio, audio o
   colore.
5. Un risultato tecnico verificato non equivale ad approvazione estetica. La review umana resta
   necessaria prima di dichiarare definitivo un render.
6. Non cambiare gate, allowlist o protezioni per sbloccare un singolo progetto.

## Ordine operativo standard

Per ADV e Reel verticali senza esigenze eccezionali usare questo ordine:

1. **Ingest e verifica sorgente**
2. **Nuovo progetto e timeline verticale**
3. **Trascrizione con timing parola per parola**
4. **Tagli iniziali/finali e interventi editoriali**
5. **Picture lock provvisorio**
6. **Pulizia e omogeneizzazione audio**
7. **Colorist**
8. **B-roll, card tematiche ed eventuali effetti motivati**
9. **Picture lock definitivo**
10. **Sottotitoli Fusion ARPHÉ**
11. **Controllo frame, render di review e ascolto**
12. **Approvazione, export finale, eventuale upload Drive e protezione dalla pulizia**

Tagli e reframing devono precedere audio, colore e sottotitoli quando modificano durata o
sincronizzazione. Se un intervento successivo cambia la struttura, tornare al picture lock e
rigenerare soltanto ciò che dipende dai nuovi timing.

## 1. Ingest e progetto

- Scaricare o copiare il file in una cartella del progetto riconoscibile e separata per
  workstation.
- Verificare dimensione e decodifica del file prima dell'import. Un download completato nella UI
  non dimostra che il file sia integro.
- Per Reel/ADV creare una timeline `1080x1920` alla frequenza del sorgente, mantenendo audio e
  video collegati.
- Conservare sempre una timeline `SOURCE` e lavorare su copie successive.
- Usare nomi ASCII per file tecnici e progetti; nel testo visibile la grafia corretta è `ARPHÉ`.

## 2. Trascrizione e testo editoriale

- Trascrivere l'audio ascoltato dalla timeline corrente, non il file originale se audio o tagli
  sono già cambiati.
- Conservare start/end di ogni parola. I segmenti testuali senza timing non sono sufficienti per
  karaoke, card sincronizzate o B-roll semantici.
- Correggere nei cue errori evidenti di riconoscimento, parole unite, apostrofi, termini medici e
  marchi senza alterare il significato del parlato.
- Non modificare il transcript sorgente e non aggiungere correzioni dedicate nel codice.
- Se il parlato usa un termine tecnico ma il tema commerciale rischia di non essere chiaro, il
  sottotitolo resta fedele e una card separata può esplicitare il tema. Esempio generico: parlato
  “iperpigmentazioni”, card editoriale “MACCHIE SOLARI”.
- Non mostrare contemporaneamente due scritte che dicono la stessa cosa. Titolo tematico e
  sottotitolo devono avere ruoli e posizioni distinguibili.

## 3. Tagli, zoom e freeze frame

- Rimuovere silenzi o falsi inizi soltanto dopo aver identificato l'inizio reale del parlato.
- Mantenere la CTA completa e una coda naturale, evitando secondi morti dopo l'ultima parola.
- Uno zoom deve seguire il soggetto richiesto, non il centro geometrico. Per un dettaglio del viso
  scegliere l'occhio o la zona indicata e lasciare respiro sufficiente per sembrare un movimento
  di camera.
- Preferire ingressi brevi con easing e mantenimento della nuova inquadratura; uno zoom lento
  distribuito su tutta la frase può risultare impercettibile.
- Un freeze frame editoriale deve riempire il canvas come il video, conservare il corretto aspect
  ratio, essere muto e durare inizialmente circa `0,5 s`. Un suono d'impatto va allineato alla fine
  della parola che motiva il fermo. È un effetto opzionale, mai parte automatica del preset ADV.
- Un punch in non sostituisce la stabilizzazione e non deve introdurre un crop eccessivo.

## 4. Audio e Fairlight

Obiettivo: voce naturale, intelligibile e coerente; non una voce artificiale priva di ambiente.

- Iniziare dal cleanup naturale verificato (`ARPHE_DIALOGUE_DEREVERB_NATURAL_V5`) su una copia.
- Applicare Voice Isolation solo dopo il cleanup e verificarne sempre il read-back. Il range
  `30–45%` è un punto di partenza prudente; valori più forti richiedono ascolto comparativo.
- Per clip registrate in luoghi diversi, uniformare livello percepito e rumore tra i raccordi.
- Ventilazione e rimbombo richiedono dereverb/isolamento moderato; i crepitii elettrici o da
  lavalier sono difetti impulsivi e non scompaiono necessariamente aumentando l'isolamento.
- Per crepitii localizzati annotare le parole e intervenire in modo puntuale. Se una correzione
  peggiora timbro o intelligibilità, tornare alla versione precedente: “meno rumore” non basta se
  la voce diventa peggiore.
- Non dichiarare risolto un difetto ascoltando solo la waveform o leggendo i parametri. Serve un
  ascolto del render o della timeline nelle parole segnalate.
- Se il difetto è nella registrazione, documentare il limite invece di applicare catene sempre più
  aggressive.

## 5. Colorist

- Partire dal trattamento ARPHÉ approvato (`ARPHE_WARM_PRESENCE` o Social Plus quando richiesto)
  e calibrare sul girato: il preset è una base, non una garanzia.
- Obiettivo: incarnato coerente e figura leggibile rispetto allo sfondo, senza pelle plastificata.
- Controllare separatamente volto, camice/abiti, pareti, soffitto e alte luci. Una figura corretta
  non compensa uno sfondo lattiginoso o un soffitto sovraesposto.
- Le correzioni locali non devono attraversare testa, capelli o mani. Se una maschera non può
  seguire il soggetto con precisione, preferire una correzione più globale e conservativa.
- Verificare almeno apertura, metà e chiusura: una singola cattura non dimostra stabilità del
  trattamento.
- Conservare la versione colore applicata nella timeline finale e verificarla dopo ogni
  duplicazione.

## 6. B-roll e immagini

- Ogni B-roll deve chiarire il contenuto o sostenere l'attenzione; non inserirlo solo perché
  disponibile.
- Agganciare ingresso e uscita a parole precise della trascrizione. Il contenuto visivo deve
  apparire quando il concetto viene pronunciato, non qualche secondo prima o dopo.
- Per ARPHÉ usare fotografie pulite in bianco e nero, coerenti con il Graphic Kit, senza testo,
  loghi, watermark, split-screen o prima/dopo promozionali.
- Se un filmato esterno scatta anche nel render, sostituirlo. Una still verticale ad alta qualità
  con eventuale movimento lieve è preferibile a un video poco fluido.
- Un B-roll a pieno schermo è accettabile quando copre intenzionalmente l'A-roll e la voce resta
  continua. Nei contenuti in cui è importante mantenere visibile il relatore, usare card laterali,
  layout compositi o inserti più brevi.
- Evitare immagini sensazionalistiche, lesioni grottesche e risultati prima/dopo. La comunicazione
  sanitaria deve restare informativa.
- Salvare asset e prompt nella cartella del progetto e registrarli nel reference della sessione se
  il risultato diventa riutilizzabile.

Nota tecnica: nelle primitive osservate, l'inserimento asset usa frame assoluti di timeline
(tipicamente con start a `108000`), mentre la cattura diagnostica usa offset locali. Convertire in
modo esplicito e verificare il frame reale; non mescolare i due sistemi.

## 7. Card tematiche

- Usare una card quando il tema non è immediatamente comprensibile dal parlato o quando un termine
  tecnico ha bisogno di una traduzione editoriale breve.
- Una sola card primaria per volta, con testo breve, maiuscolo e leggibile.
- Usare Satoshi Bold, bordeaux e crema del kit; niente colori estranei salvo approvazione esplicita
  per un singolo test.
- La card deve stare nei margini sicuri, non tagliare il viso e non coprire il soggetto più del
  necessario. Controllare anche i fotogrammi di entrata e uscita, non soltanto il centro.
- La grafica speciale appartiene al piano del progetto. Non creare un nuovo comando bridge per la
  frase o il video.

## 8. Sottotitoli Fusion ARPHÉ

Applicare il contratto completo di `docs/15_ARPHE_FUSION_CAPTIONS.md`.

Regole sintetiche:

- intera frase visibile e sfondo karaoke dietro la parola pronunciata;
- Satoshi Bold maiuscolo;
- solo `0.050` standard e `0.065` evidenza;
- al massimo una parola rilevante per frase in Bold Italic e misura evidenza;
- massimo due righe, centrate e bilanciate;
- parole vicine, card aderenti, interlinea compatta e margini costanti;
- nessun fitting dinamico che introduca molte grandezze;
- parole lunghe interamente dentro lo sfondo;
- applicazione soltanto dopo il picture lock tramite azione generica `CAPTIONS POST_LOCK`.

La parola in evidenza si sceglie per significato, non per lunghezza. Se l'enfasi rende la frase
affollata, dividere il gruppo temporale o usare due righe; non ridurre il font.

## 9. Verifica prima della review

Controllare almeno:

- primo e ultimo frame utile;
- card tematica completa durante entrata, centro e uscita;
- ogni B-roll nel punto semantico corretto;
- una frase a una riga e una a due righe;
- tutte le parole in evidenza e le parole più lunghe;
- assenza di lettere fuori dalla card o parole attaccate;
- continuità di color e audio dopo la duplicazione;
- Voice Isolation effettivamente attiva sul track previsto;
- assenza di scatti nel render, non solo nella timeline;
- audio nelle parole precedentemente segnalate come problematiche.

Una cattura frame dimostra la composizione visiva; non dimostra fluidità o qualità audio. Per la
review completa serve un render locale verificato.

## 10. Export, Drive e definitivo

- Renderizzare dalla timeline finale nominata, non da una provvisoria tecnica.
- Verificare risoluzione, fps, durata, presenza audio e decodifica del file prima dell'upload.
- Tenere distinte le cartelle Drive di `PC_PERSONALE` e `PC_SEGRETERIA`.
- L'upload passa dal connettore/bridge previsto e non richiede prendere il controllo dello schermo.
- Un file approvato va dichiarato **definitivo** e protetto dal ciclo locale di quarantena tramite
  il meccanismo `keep` dell'artefatto registrato.
- Non assumere che un nome contenente `DEFINITIVO` sostituisca un hold tecnico. Il coordinatore di
  retention Drive deve essere verificato separatamente; finché non lo è, non promettere una
  protezione automatica remota.

## 11. Parità tra PC personale e PC segreteria

La repository condivisa trasferisce regole e codice, ma non rende automaticamente identiche due
workstation. Prima di affidare un progetto alla segreteria verificare che entrambi i PC abbiano:

- stessa revisione delle repository `arphe-graphic-kit` e `video-editing-manual`;
- stessa release del bridge e stessa versione compatibile di Resolve;
- font Satoshi e Noto Serif Display disponibili;
- stessi preset approvati e gate necessari;
- cartelle e allowlist corrette per quella workstation;
- separazione fra render, quarantena e Drive della workstation;
- accesso alla sorgente e agli asset del progetto.

Le configurazioni con percorsi, workstation ID e credenziali restano specifiche del PC e non vanno
copiate alla cieca. La parità si dimostra con un progetto campione, non con il solo `git pull`.

## Checklist breve per la segreteria

- [ ] Ho creato un nuovo progetto e conservato il SOURCE.
- [ ] Ho trascritto la timeline corrente.
- [ ] Ho completato tagli e scelte editoriali prima di audio/colore/caption.
- [ ] Ho applicato cleanup naturale e verificato Voice Isolation.
- [ ] Ho controllato incarnato, sfondo e alte luci in più frame.
- [ ] Ogni B-roll chiarisce una frase ed entra sulla parola corretta.
- [ ] Le immagini ARPHÉ sono in bianco e nero e non contengono testo generato.
- [ ] Ho marcato il picture lock prima dei sottotitoli.
- [ ] I sottotitoli usano soltanto due misure e massimo due righe.
- [ ] Ho verificato parole lunghe, accenti, `ARPHÉ`, spaziatura e card karaoke.
- [ ] Ho visto il render completo e ascoltato i punti audio critici.
- [ ] Solo dopo approvazione ho esportato, caricato e marcato il file definitivo.

## Cose che restano decisioni di Alessio

- approvazione estetica del color e dell'intensità Social Plus;
- scelta o rifiuto dei B-roll proposti;
- eccezioni cromatiche e grafiche fuori palette;
- effetti speciali, freeze frame e suoni d'impatto;
- accettabilità finale di difetti audio nativi;
- dichiarazione definitiva del render.

La segreteria può completare in autonomia il percorso standard; quando una decisione ricade in
questo elenco, prepara una review chiara e chiede approvazione senza modificare il bridge.

