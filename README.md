# video-editing-manual

Memoria di lavoro persistente del progetto **ARPHE Video Automation**.

## Obiettivo prodotto corrente

L'interfaccia principale destinata alla segreteria deve essere **ChatGPT**, non una GUI ARPHE separata.

Architettura target:

`Segreteria -> ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> DaVinci Resolve Studio API`

ChatGPT gestisce il dialogo e le decisioni editoriali; il bridge locale espone soltanto tool controllati e traduce le decisioni approvate in operazioni deterministiche su Resolve.

Dettagli e gate di validazione: `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`.

## Da dove partire

Per persone e ChatGPT: aprire **[`START_HERE.md`](START_HERE.md)** e seguire l'ordine di lettura indicato lì.

- `CURRENT_STATE.md` — stato tecnico corrente e prossimi passi
- `EXPERIMENT_LOG.md` — registro persistente degli esperimenti
- `CHANGELOG.md` — decisioni e risultati consolidati
- `INDEX.md` — indice della documentazione e degli script
- `docs/` — procedure, architettura e workflow
- `scripts/validated/` — primitive già verificate
- `reference/` — note storiche e archivio degli esperimenti

## Regola operativa

La repository è la fonte di verità del progetto. Quando un test modifica ciò che sappiamo, aggiornare almeno `CURRENT_STATE.md`, `EXPERIMENT_LOG.md` e `CHANGELOG.md` quando pertinente.

Gli script sperimentali o parziali non devono essere trattati come affidabili finché non vengono promossi esplicitamente in `scripts/validated/`.

I vecchi documenti `ARPHE Remote Agent V1` basati su GUI Windows + polling GitHub sono **superati** e non rappresentano più la direzione da implementare. La fonte architetturale corrente è `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`.
