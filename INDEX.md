# INDEX

## Documenti principali

| File | Scopo |
|---|---|
| `START_HERE.md` | Punto di ingresso per persone e ChatGPT |
| `CURRENT_STATE.md` | Stato tecnico corrente |
| `EXPERIMENT_LOG.md` | Registro persistente degli esperimenti e dei prossimi step |
| `CHANGELOG.md` | Storico delle decisioni |
| `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md` | **Architettura prodotto corrente: ChatGPT -> MCP -> Resolve Studio** |
| `docs/09_MCP_TUNNEL_ROLLOUT_CHECKLIST.md` | Procedura tunnel e gate ChatGPT READ/WRITE |
| `docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md` | **Autostart Windows, PC segreteria vs PC personale, replica e handoff Codex** |
| `docs/RESOLVE_STUDIO_CAPABILITIES.md` | Matrice delle capacità Studio effettivamente testate |
| `docs/07_EDITORIAL_BENCHMARK.md` | Benchmark umano, profilo editoriale e protocollo anti-leakage |
| `docs/01_SETUP_RESOLVE_PYTHON.md` | Setup Resolve/Python, Studio external scripting e fallback legacy |
| `docs/02_SHORTFORM_WORKFLOW.md` | Pipeline shortform |
| `docs/03_TRACKING_FUSION.md` | Tracking, Fusion, yoyo e lezioni |
| `docs/04_LONGFORM_WORKFLOW.md` | Pipeline longform |
| `docs/05_OPERATOR_GUIDE.md` | Istruzioni manuali click-per-click per test/fallback |
| `docs/06_TROUBLESHOOTING.md` | Problemi noti |
| `docs/TRAINING_ROADMAP.md` | Sequenza di validazione delle capacità |
| `docs/PROVISIONAL_REFERENCES.md` | Fonti Resolve/Fusion esterne non authoritative |

## Architettura corrente

Interfaccia primaria:

`Segreteria -> ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio API`

Workstation di riferimento corrente:
- `PC_SEGRETERIA`: VALIDATED end-to-end READ + SAFE WRITE;
- `PC_PERSONALE`: PENDING REPLICA.

Non usare i vecchi documenti `ARPHE Remote Agent V1` come piano attuale: sono conservati in `docs/superpowers/` ma marcati **SUPERSEDED**.

Il piano `docs/superpowers/plans/2026-08-28-resolve-studio-capability-audit.md` resta valido come backlog di probe tecnici.

## Script validati

| Script | Stato | Utilizzo |
|---|---|---|
| `scripts/validated/ARPHE_AUTOCUT_TEST_01.py` | ✅ | Ricostruzione timeline con tagli |
| `scripts/validated/ARPHE_NUCLEAR_RESET_YOYO_08.py` | ✅ | Yoyo via Fusion BezierSpline |
| `scripts/validated/ARPHE_MANUAL_TRACK_SETUP_13A_V2.py` | ✅ | Prepara tracking manuale limitato a un range |
| `scripts/validated/ARPHE_TRACKED_YOYO_APPLY_13B_V2.py` | ✅ proof of concept | Legge tracking e applica yoyo |

## Studio / MCP experiments

- `scripts/experiments/ARPHE_STUDIO_EXTERNAL_API_TEST_01.py`: **external READ API superato** su Resolve Studio 21.0.4.5.
- `scripts/experiments/ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02.py`: **SAFE WRITE superato**; `CreateEmptyTimeline` + ritorno all'originale.
- `scripts/experiments/ARPHE_MCP_BRIDGE_READ_01.py`: **MCP locale -> Resolve READ superato** con `ping` + `resolve_status`.
- ChatGPT -> Secure MCP Tunnel -> Resolve READ: **VALIDATED**.
- ChatGPT -> Secure MCP Tunnel -> Resolve SAFE WRITE: **VALIDATED** per `create_safe_working_timeline`.
- Prossimo gate infrastrutturale: **autostart persistente sul PC segreteria senza PowerShell manuale**.

## Benchmark / strumenti di valutazione

- `ARPHE_EXPORT_REFERENCE_EDIT_02.py`: esporta da Resolve un reference umano con kept/remove/joins.
- `ARPHE_COMPARE_CUTS_01.py`: confronta reference e candidate plan con metriche quantitative.

## Script parziali / esperimenti storici

Vedi `scripts/partial/`, `scripts/experiments/` e `reference/nonvalidated_archive/`.

Servono come archivio tecnico e per evitare di ripetere strade già testate; non vanno usati come primitive di produzione senza verifica/promozione esplicita.
