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
