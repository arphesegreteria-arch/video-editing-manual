# 13 — Diagnostica visuale e backup ARPHE

Data: 2026-09-10

## Diagnostica Resolve via MCP

Creative 03 espone due primitive diagnostiche:

- `inspect_fusion_graph(composition_id)`: inventario read-only di nodi e input sicuri; il testo
  non viene restituito, soltanto la sua lunghezza;
- `capture_timeline_frames(frame_offsets)`: esporta da uno a otto frame precisi della timeline
  ARPHE corrente e li restituisce come immagini JPEG MCP. Gli offset sono relativi all'inizio
  timeline. JPEG è usato perché il PNG nativo di Resolve 21 non è interoperabile con il decoder
  immagini del client MCP verificato, mentre il JPEG nativo lo è.

La cattura usa `Project.ExportCurrentFrameAsStill()` della documentazione Resolve Studio
21.0.4.5. Sposta temporaneamente pagina/playhead, esporta JPEG nella sola render root ARPHE e
ripristina lo stato UI. Non modifica il grafo, non salva il progetto e non usa la render queue.

Per sequenze lunghe l'agente deve lavorare a batch: prima campionamento ampio, poi batch contigui
di massimo otto frame nelle zone critiche. È possibile coprire ogni frame ripetendo le chiamate,
senza inviare centinaia di JPEG in una singola risposta MCP.

Le annotazioni MCP distinguono esplicitamente le letture (`ping`, status, feature flag e ispezione
grafo) dalle scritture. Tutte le azioni sono dichiarate closed-world e non distruttive;
`capture_timeline_frames` resta una scrittura non distruttiva perché crea file JPEG temporanei.

Stato app al 2026-09-11: il server Creative 03 espone 30 azioni con annotazioni corrette. La
sequenza validata è `create_review_sequence_v2`: usa una sola composition e i parametri `name`,
`reviews`, `total_duration_frames` (massimo 150) e `style_role`; il nome non versionato resta un
wrapper per i client con schema precedente. Il test V5
ha coperto in immagine tutti i confini delle quattro finestre senza buchi. Il refresh dello schema vede soltanto la
copia installata in `C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03`: modificare la repository e
riavviare il vecchio processo non basta, occorre rieseguire `install_on_segreteria.ps1` prima
dello switch/restart. Nella console ChatGPT il caricamento dell'app e dell'elenco azioni può
richiedere almeno 30 secondi; evitare refresh ripetuti. Su un'app già attivata, **Modifica → Vedi
dettagli → Aggiorna** seguito dal salvataggio aggiorna direttamente la versione attiva e non
mostra un ulteriore pulsante **Pubblica**.

Se cambia soltanto la firma di un tool già pubblicato, la console può lasciare **Aggiorna** grigio
e mostrare la descrizione precedente. Pubblicare un nome versione aggiuntivo nella stessa app
forza il confronto dell'elenco azioni; non serve creare un'altra app.

Nell'ultima prova il runtime/tunnel a 30 azioni era sano, ma tre istanze della pagina admin sono
rimaste congelate anche durante una lettura e **Aggiorna** non è stato premuto. Questo è un blocco
UI distinto dal bridge: considerare la pubblicazione della trentesima azione ancora PENDING.

`capture_timeline_frames` costruisce un `CallToolResult` con metadati testuali strutturati e
blocchi `ImageContent` JPEG; non inserire gli helper `Image` nel JSON strutturato. Il percorso è
stato validato end-to-end dalla chat sia sui frame `0`, `75` e `149`, sia sugli otto lati dei
confini della sequenza V5, con ripristino del playhead.

## Backup su disco esterno

Con Resolve aperto sul progetto ARPHE corrente:

```powershell
cd C:\ARPHE\video-editing-manual
.\scripts\backup\backup_arphe.ps1 -DestinationRoot 'E:\ARPHE_BACKUPS' -IncludeCurrentResolveProject
```

Sostituire `E:` con la lettera verificata del disco esterno. Lo script rifiuta il disco di sistema
per default e richiede una repository pulita. Produce:

- Git bundle completo con tutta la cronologia;
- ZIP dello stato `HEAD`;
- config Creative redatta, stato e audit Creative;
- config runtime redatta;
- export `.drp` del solo progetto corrente, se il nome inizia con `ARPHE_`;
- `MANIFEST.json` con dimensioni e SHA-256 di ogni file.

La runtime API key protetta da DPAPI non viene copiata. Deve essere rigenerata/reinstallata in un
ripristino su un altro PC.
