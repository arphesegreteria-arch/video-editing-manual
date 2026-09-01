# 06 — Troubleshooting

## Prima domanda: quale percorso stai testando?

### Percorso corrente
`ChatGPT / MCP -> bridge Python esterno -> Resolve Studio`

### Percorso legacy/fallback
`Workspace -> Scripts -> Utility -> script interno Resolve`

Non usare le istruzioni del percorso legacy per diagnosticare un problema MCP/Studio esterno.

## Python esterno non vede Resolve Studio

Controllare click-per-click:
1. Aprire Resolve Studio.
2. Aprire `Preferences`.
3. Selezionare **System**.
4. Cliccare **General**.
5. Controllare `External scripting using`.
6. Deve essere **Local** per i test sullo stesso PC.
7. Cliccare **Save**.
8. Riavviare Resolve se necessario.
9. Aprire un progetto e una timeline.
10. Rilanciare il probe.

`ARPHE_STUDIO_EXTERNAL_API_TEST_01` è già stato validato su Resolve Studio 21.0.4.5.

## MCP locale funziona ma ChatGPT non lo vede

ChatGPT non collega direttamente un MCP server localhost/private network.

Per il percorso target serve Secure MCP Tunnel e una custom MCP app configurata nel workspace ChatGPT.

Controllare anche che il piano/workspace disponga delle autorizzazioni MCP necessarie: le write action richiedono full MCP.

## MCP server locale non parte

Controllare:
- Python 3.10+;
- installazione `mcp[cli]` v2;
- prima eseguire il test in-memory del bridge;
- solo dopo usare MCP Inspector / Secure MCP Tunnel.

Il primo bridge ARPHE deve restare read-only (`ping`, `resolve_status`).

## Script legacy non compare in Resolve

Solo per i vecchi test Utility, controllare:
`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`

Poi riavviare Resolve.

## Timeline con buchi dopo cut

Preferire intervalli sorgente contigui e verificare:
- `startFrame`;
- `endFrame`;
- `recordFrame`.

Il frame successivo deve iniziare esattamente dopo il precedente. Dopo un append usare il vero `GetEnd()` dell'item appena creato come prossimo record cursor quando possibile.

## Longform: parole troncate dopo i cut

Non assumere subito drift.

Controllare:
- FPS timeline;
- FPS sorgente;
- durata in frame;
- durata transcript.

Se coincidono, il problema più probabile è un boundary troppo vicino alla parola.

Regola: **non usare direttamente i timestamp Whisper come lama finale.**

L'audio alignment deve:
- proteggere l'interno delle parole;
- cercare una giunzione naturale vicina;
- preferire conservare parlato piuttosto che troncarlo.

## Longform: ci sono ancora troppe pause

I gap possono essere reali, non "latenza Whisper".

Non eliminare tutte le pause:
- pause brevi: lasciare;
- pause chiaramente lunghe: accorciare;
- conservare respiro naturale.

## Longform: clip audio e video sembrano disallineate

Prima distinguere vero offset A/V da silenzio dentro la clip.

Se i bordi video/audio iniziano e finiscono sugli stessi frame ma la waveform del parlato parte più tardi, è probabilmente **troppa aria nella giunzione**, non sync perso.

V4.3 ha migliorato questo problema specifico rispetto a V4.2.

## Longform: il cut audio è corretto ma visivamente brutto

L'audio alignment non risolve automaticamente i jump cut visivi. Serve un livello separato: B-roll, punch-in/reframe o altre primitive validate.

## Zoom non visibile

Per test:
- usare valori molto evidenti (es. 1.75x–2.5x);
- creare una timeline/Fusion Comp nuova;
- ridurre la catena a `MediaIn -> Transform -> MediaOut`.

## Tracker altera il render

Non inserire il Tracker in serie verso MediaOut.

Usare:
`MediaIn -> MediaOut`

e in parallelo:
`MediaIn -> Tracker`

## Tracking immobile da script

Il vecchio risultato riguarda la build Free testata. Non assumere che descriva automaticamente Studio.

Se un nuovo probe Studio fallisce, registrare il risultato nella capability matrix prima di ripiegare sul workaround manuale.

## Tracking segue la cosa giusta ma zoom è scentrato

Separare:
- anchor del tracking;
- target estetico;
- offset/reframe.
