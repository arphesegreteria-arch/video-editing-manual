# 01 — Setup Resolve + Python

## Ambiente verificato

- Windows
- Python installato
- DaVinci Resolve Free
- Script Python eseguiti **dentro Resolve**

## Cartella script Resolve

Percorso usato:

`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`

Gli script `.py` vengono copiati qui.

Dopo l'aggiunta di nuovi script può essere necessario riavviare Resolve.

## Avvio script

In Resolve:

`Workspace → Scripts → Utility → <nome script>`

## Filosofia

Nella versione gratuita attuale non affidarsi a un controller esterno.
Gli script vengono eseguiti internamente a Resolve.

Se in futuro si passa a DaVinci Resolve Studio, rivalutare:
- remote scripting;
- IntelliTrack;
- Magic Mask;
- Smart Reframe;
- controller Python esterno.
