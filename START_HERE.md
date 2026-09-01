# ARPHE Video Automation — START HERE

Questa repository è la **fonte di verità** del progetto di automazione video ARPHE.

## Obiettivo corrente

La UI finale prevista per la segreteria è **ChatGPT**.

Percorso target:

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> DaVinci Resolve Studio`

Non costruire una GUI desktop ARPHE separata come interfaccia primaria salvo nuova decisione esplicita.

## Ordine di lettura

1. `CURRENT_STATE.md` — cosa funziona oggi e cosa no.
2. `EXPERIMENT_LOG.md` — esperimenti, file, risultati e prossimo passo.
3. `INDEX.md` — indice di documenti e script.
4. `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md` — architettura prodotto corrente.
5. `docs/RESOLVE_STUDIO_CAPABILITIES.md` — matrice delle operazioni Studio effettivamente testate.
6. `docs/07_EDITORIAL_BENCHMARK.md` — benchmark umano e profilo editoriale.
7. `docs/01_SETUP_RESOLVE_PYTHON.md` — setup Resolve/Python e fallback legacy.
8. `docs/02_SHORTFORM_WORKFLOW.md` — workflow shorts/ADV.
9. `docs/03_TRACKING_FUSION.md` — lezioni su tracking, Fusion e yoyo.
10. `docs/04_LONGFORM_WORKFLOW.md` — pipeline longform e trascrizione.
11. `docs/05_OPERATOR_GUIDE.md` — procedure manuali di test/fallback.
12. `docs/06_TROUBLESHOOTING.md` — errori noti e cosa fare.

## Regola per ChatGPT

Quando questa repository viene usata in una nuova sessione:
- leggere prima `START_HERE.md`;
- poi `CURRENT_STATE.md` e `EXPERIMENT_LOG.md`;
- usare `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md` come fonte della direzione prodotto;
- consultare solo i file pertinenti al task;
- non assumere che gli script nella cartella `experiments/` siano affidabili;
- trattare `scripts/validated/` come primitive già verificate;
- aggiornare lo stato persistente quando un test cambia ciò che sappiamo.

## Documenti storici superati

I documenti sotto `docs/superpowers/` relativi a **ARPHE Remote Agent V1** con GUI Windows + coda GitHub sono conservati soltanto come storia progettuale e devono essere marcati `SUPERSEDED`.

Non usarli come piano d'implementazione corrente.

Il piano `resolve-studio-capability-audit` resta invece pertinente per verificare una per una le capacità dell'API Studio.

## Regola per gli operatori

Gli operatori possono non conoscere né Python né DaVinci Resolve.

Nell'obiettivo finale devono poter operare conversando con ChatGPT. Finché esistono passaggi manuali di test/fallback, ogni passaggio in Resolve deve comunque essere spiegato **click-per-click**, senza presupporre conoscenze pregresse.
