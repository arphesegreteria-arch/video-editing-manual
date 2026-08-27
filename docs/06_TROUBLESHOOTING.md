# 06 — Troubleshooting

## Script non compare in Resolve

Controllare:
`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`

Poi riavviare Resolve.

## Timeline con buchi dopo cut

Preferire intervalli sorgente contigui e verificare:
- `startFrame`
- `endFrame`
- `recordFrame`

Il frame successivo deve iniziare esattamente dopo il precedente.

## Longform: parole troncate dopo i cut

Non assumere subito un problema di drift.

Controllare prima:
- FPS timeline;
- FPS sorgente;
- durata in frame;
- durata transcript.

Se coincidono, il problema più probabile è che il timestamp Whisper sia stato usato troppo vicino alla parola.

Regola:
**non usare direttamente i timestamp Whisper come lama finale.**

Usare un passaggio di audio alignment che:
- protegga l'interno delle parole;
- cerchi un punto quieto vicino;
- preferisca conservare un po' di materiale piuttosto che troncare parlato.

## Longform: ci sono ancora troppe pause

Il transcript può contenere veri gap tra parole/segmenti. Questi non sono necessariamente "latenza Whisper".

Non eliminare tutte le pause.
Strategia consigliata:
- pause brevi: lasciare intatte;
- pause chiaramente lunghe: accorciare;
- conservare sempre un piccolo respiro naturale.

## Longform: clip audio e video sembrano disallineate

Prima verificare se è un vero offset A/V oppure solo silenzio dentro la clip.

Se i bordi video e audio iniziano/finiscono sullo stesso frame ma la waveform del parlato parte più tardi, il problema è probabilmente **troppa aria nella giunzione**, non sync perso.

La V4.3 nasce proprio per rendere la giunzione più compatta rispetto alla V4.2.

## Longform: il cut audio è corretto ma visivamente brutto

L'audio alignment non risolve automaticamente i jump cut visivi.
La revisione umana resta obbligatoria finché non viene introdotto un livello separato di gestione visiva (B-roll, punch-in, morph/transition dove sensato).

## Zoom non visibile

Per test:
- usare valori molto evidenti (es. 1.75x–2.5x);
- creare una timeline/Fusion Comp nuova;
- ridurre la catena a `MediaIn → Transform → MediaOut`.

## Tracker altera il render

Non inserire il Tracker in serie verso MediaOut.

Usare:
`MediaIn → MediaOut`
e in parallelo:
`MediaIn → Tracker`

## Tracking immobile da script

Se `TrackedCenter1` resta identico:
- non insistere sul trigger automatico;
- usare tracking nativo manuale;
- leggere successivamente il path via Python.

## Tracking segue la cosa giusta ma zoom è scentrato

Non spostare necessariamente il tracker.
Separare:
- anchor del tracking;
- target estetico;
- offset/reframe.
