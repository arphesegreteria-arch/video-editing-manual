# 01 — Setup Resolve + Python

## Ambiente verificato

### Ambiente storico / fallback
- Windows;
- Python installato;
- DaVinci Resolve Free;
- script Python eseguiti **dentro Resolve** tramite `Workspace -> Scripts -> Utility`.

### Ambiente corrente Studio
- Windows;
- DaVinci Resolve Studio `21.0.4.5`;
- Preferences -> **System -> General**;
- `External scripting using = Local`;
- Python eseguito **fuori da Resolve**;
- import `DaVinciResolveScript` riuscito;
- connessione esterna e lettura progetto/timeline riuscite.

Vedi `docs/RESOLVE_STUDIO_CAPABILITIES.md` per lo stato dei singoli comandi.

## Setup Studio — External scripting

1. Aprire DaVinci Resolve Studio.
2. Aprire `DaVinci Resolve -> Preferences`.
3. In alto selezionare **System**.
4. A sinistra cliccare **General**.
5. Cercare `External scripting using`.
6. Selezionare **Local**.
7. Cliccare **Save**.
8. Chiudere e riaprire Resolve Studio se necessario.
9. Lasciare Resolve aperto con un progetto/timeline di test.
10. Lanciare il probe Python esterno.

Test validato: `ARPHE_STUDIO_EXTERNAL_API_TEST_01.py`.

## Cartella script Resolve — fallback legacy

Percorso usato per gli script interni:

`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`

Gli script `.py` copiati qui compaiono sotto:

`Workspace -> Scripts -> Utility`

Questo percorso resta utile per test storici e fallback, ma **non è più la direzione architetturale principale**.

## Direzione runtime corrente

Il target è:

`ChatGPT -> MCP -> bridge Python esterno -> Resolve Studio API`

Il bridge locale userà l'API esterna di Studio senza chiedere alla segreteria di copiare/lanciare manualmente script Utility.

## Stato dei gate

- External READ: **SUPPORTED**.
- External WRITE innocua: **PENDING**, test `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`.
- MCP locale READ: **PENDING**.
- ChatGPT -> MCP -> Resolve: **PENDING**.

Non saltare direttamente a tool MCP distruttive prima della validazione del write test.
