# 13 — Diagnostica visuale e backup ARPHE

Data: 2026-09-09

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
senza inviare centinaia di PNG in una singola risposta MCP.

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
