# ARPHE Video Automation — START HERE

Questa cartella è la **fonte di verità** del progetto di automazione video ARPHE.

## Ordine di lettura

1. `CURRENT_STATE.md` — cosa funziona oggi e cosa no.
2. `INDEX.md` — indice di documenti e script.
3. `docs/01_SETUP_RESOLVE_PYTHON.md` — setup tecnico.
4. `docs/02_SHORTFORM_WORKFLOW.md` — workflow shorts/ADV.
5. `docs/03_TRACKING_FUSION.md` — lezioni su tracking, Fusion e yoyo.
6. `docs/04_LONGFORM_WORKFLOW.md` — pipeline longform e trascrizione.
7. `docs/05_OPERATOR_GUIDE.md` — istruzioni per operatori non tecnici.
8. `docs/06_TROUBLESHOOTING.md` — errori noti e cosa fare.

## Regola per ChatGPT

Quando questa cartella viene fornita a ChatGPT in una nuova sessione:
- leggere prima `START_HERE.md`;
- poi `CURRENT_STATE.md`;
- poi consultare solo i file pertinenti al task;
- non assumere che gli script nella cartella `experiments/` siano affidabili;
- trattare `scripts/validated/` come primitive già verificate;
- aggiornare `CURRENT_STATE.md` e `CHANGELOG.md` quando un test cambia lo stato del progetto.

## Regola per gli operatori

Gli operatori possono non conoscere né Python né DaVinci Resolve.
Ogni passaggio manuale deve essere spiegato **click-per-click**, senza presupporre conoscenze pregresse.
