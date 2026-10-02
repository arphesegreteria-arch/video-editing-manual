# 16 — Caption Engine e sottotitoli mobile

Stato: **PARTIAL / TESTED SU UN PROGETTO REALE**

Ultimo test: 2026-10-02, `PC_PERSONALE`, Resolve Studio `21.0.4.5`.

## Risultato verificato

Sul progetto `ARPHE_SHORTFORM_PROVA_EDITING_V1`, timeline
`ARPHE_SHORTFORM_MASTER_V4`, è stato completato e verificato tramite render un flusso verticale
1080×1920/30 con 12 sottotitoli temporizzati, modificabili e coerenti con il graphic kit:

- font Satoshi Bold;
- testo bianco;
- fondo bordeaux `#680C09`;
- corpo Text+ `0.050`, aumentato dopo controllo a piena risoluzione su formato telefono;
- fascia bassa con centro caption al 76% dell'altezza del frame;
- una sola battuta visibile per volta;
- nessun sottotitolo nei gap;
- output MP4/H.264 1080×1920/30 predisposto in Deliver.

La verifica non si è limitata al read-back API: sono stati renderizzati il video completo e
fotogrammi rappresentativi, includendo una pausa senza testo e frasi di lunghezza diversa.

## Safe area verticale e regola volto

Per contenuti 9:16 non usare una posizione fissa vicina alla testa. La posizione deve essere
scelta fra due fasce e verificata sull'immagine:

- **fascia bassa predefinita:** box caption entro il 68–82% dell'altezza del frame, centro
  indicativo al 76%; in Fusion, dove Y cresce dal basso, `Center.Y = 0.24`;
- **fascia alta alternativa:** box entro l'8–20% del frame, da usare soltanto quando la fascia
  bassa copre un elemento importante;
- **riserva interfaccia:** lasciare libero almeno l'ultimo 15% in basso;
- **margini orizzontali:** envelope massimo 8–92%, preferendo testo entro 12–88%;
- **volto:** il box, incluso padding e fondo, non deve intersecare alcun volto. Aggiungere un
  margine visivo attorno alla testa, non limitarsi al rettangolo facciale stretto.

La fascia bassa è il default perché evita la zona testa/sguardo nei talking head. Non cambiare
fascia a ogni battuta: mantenerla per tutta una scena, salvo una collisione reale. Se entrambe le
fasce collidono con volti o informazioni cliniche importanti, il risultato richiede revisione
umana o una posizione per-scena esplicitamente approvata.

## Cosa espone davvero l'API nativa

`Timeline.CreateSubtitlesFromAudio(...)` funziona nella build testata dopo aver aperto
esplicitamente la pagina Edit con `resolve.OpenPage("edit")`.

Il risultato nativo è utile come sorgente di timing e testo, ma la superficie pubblica osservata
non consente di automatizzare in modo affidabile lo stile Track Style/Inspector. Inoltre
`TimelineItem.SetName(...)` sui caption item ha restituito `False`, quindi non va usato come
metodo di correzione del testo riconosciuto.

Conclusione operativa: usare la traccia subtitle nativa come sorgente/diagnostica, non come unico
motore grafico quando servono stile ARPHÈ e controllo deterministico.

## Fallback Text+ verificato

La soluzione testata non usa PNG. Tutto il testo resta in nodi Text+ modificabili dentro una
singola composizione Fusion posta sopra il montaggio.

Grafo logico:

`Background trasparente → Merge caption 1 → ... → Merge caption N → MediaOut`

Per ogni battuta:

1. creare un nodo Text+ con testo e stile;
2. creare un Merge dedicato;
3. collegare il Text+ al Foreground del Merge;
4. rendere visibile il Merge soltanto nel suo intervallo con:

   `iif(time >= start and time < end, 1, 0)`

5. concatenare il Merge al precedente;
6. disabilitare la traccia subtitle nativa per evitare duplicati;
7. impostare `ExportSubtitle = False`: il risultato Fusion è già parte del video.

## Problemi incontrati e correzioni

### Tutti i sottotitoli visibili insieme

L'assegnazione diretta di un `BezierSpline` a `Merge.Blend` non è rimasta attiva nel test.
`Blend.SetExpression(...)` ha invece prodotto valori `0/1` corretti ai frame campione.

### Fondo nero sopra il video

Usare il MediaIn del carrier come radice del grafo ha prodotto un frame opaco. La correzione è
stata un nodo `Background` Fusion con RGBA tutti a zero come base reale del primo Merge.

### Nodi duplicati durante l'introspezione

In questa build `GetToolList(False)` può esporre lo stesso tool tramite più chiavi della mappa.
Prima di modificare il grafo, deduplicare i nodi usando `TOOLS_Name`.

### Verifica insufficiente tramite API

Un read-back corretto non prova la resa grafica. Il gate minimo deve includere:

- fotogramma con prima battuta;
- fotogramma con frase lunga;
- fotogramma in un gap senza testo;
- fotogramma vicino all'ultima battuta;
- render alla risoluzione finale, non solo Viewer o proxy.

## Regole operative provvisorie

- Preservare una copia `.drt` prima di aggiungere il layer caption.
- Mantenere la traccia nativa disabilitata, non cancellata, finché il testo non è approvato.
- Correggere nomi propri nel Text+; non affidarsi a `SetName` del caption item.
- Usare un carrier lungo esattamente quanto la timeline e verificare start/end frame.
- Applicare stile e timing in un'unica composizione per evitare decine di clip grafiche separate.
- Trattare `Center.Y = 0.24` come default 9:16, non come valore universale: applicare prima la
  regola volto e controllare almeno un frame per ogni cambio scena.
- Ripristinare sempre il preset Deliver finale dopo i render diagnostici.
- Non promuovere ancora questa procedura in `scripts/validated/`: serve un'implementazione
  parametrica e almeno un secondo progetto rappresentativo.

## Criteri per la promozione a VALIDATED

1. Tool MCP semantica, senza accesso a proprietà Fusion arbitrarie.
2. Input: caption/timing già approvati oppure traccia subtitle nativa letta in sicurezza.
3. Gestione line wrapping, safe area, font fallback e testi vuoti.
4. Rollback limitato al carrier/grafo creato dalla chiamata.
5. Test a 24/25/30 fps e su almeno due durate/formati verticali.
6. Render finale verificato e confronto frame-by-frame dei gap.
7. Nessun conflitto con sottotitoli nativi o burn-in della Deliver page.

## Fonti e provenienza

- documentazione Developer/Scripting installata con Resolve 21;
- [DaVinci Resolve 21 New Features Guide](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_21_New_Features_Guide.pdf);
- [DaVinci-Resolve-Subtitle-to-TextPlus](https://github.com/Rraz0rR/DaVinci-Resolve-Subtitle-to-TextPlus), usato come riferimento architetturale, non importato;
- [Resolve OpenCaptions](https://github.com/david-ca6/Resolve-OpenCaptions), riferimento esterno per caption Fusion modificabili.

Le fonti esterne restano subordinate al comportamento riprodotto e verificato nel nostro ambiente.
