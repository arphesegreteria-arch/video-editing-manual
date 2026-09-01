# Resolve Studio Capability Matrix

Ambiente di riferimento corrente:
- Windows;
- DaVinci Resolve Studio `21.0.4.5`;
- `External scripting using = Local`;
- Python esterno;
- Python MCP SDK v2 installato per il prototipo locale.

Stati ammessi:
- `SUPPORTED`: riprodotto con successo nel nostro ambiente;
- `PARTIAL`: funziona in parte o manca robustezza;
- `MANUAL`: non affidabile via API / richiede intervento umano;
- `PENDING`: non ancora testato.

| Capability | Stato | Evidenza / note |
|---|---|---|
| Import `DaVinciResolveScript` da Python esterno | SUPPORTED | `ARPHE_STUDIO_EXTERNAL_API_TEST_01`, exit code 0 |
| Connessione a Resolve Studio da Python esterno | SUPPORTED | Versione letta `21.0.4.5` |
| Leggere progetto corrente | SUPPORTED | Test: progetto `blabla` |
| Leggere timeline corrente | SUPPORTED | Test: `Timeline 1` |
| Leggere FPS timeline | SUPPORTED | Test: `30.0` |
| Leggere track count video/audio | SUPPORTED | Test: 1 V / 1 A |
| Leggere item V1/A1 | SUPPORTED | Test: 130 V1 / 130 A1 |
| Creare timeline vuota da Python esterno | SUPPORTED | `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`: timeline count 2 -> 3, exit code 0 |
| Tornare alla timeline originale via API | SUPPORTED | Test 02: `SetCurrentTimeline(original) = True`, timeline finale `Timeline 1` |
| MCP locale: avvio server/tool discovery | SUPPORTED | `ARPHE_MCP_BRIDGE_READ_01`, protocollo MCP negoziato, tool `ping` e `resolve_status` visibili |
| MCP locale -> Resolve READ | SUPPORTED | `resolve_status` ha letto versione, progetto `blabla`, `Timeline 1`, FPS 30, 1V/1A, 130 V1 + 130 A1; exit code 0 |
| Import media da Python esterno | PENDING | Da testare |
| Ricostruire timeline con cut da bridge esterno | PENDING | Primitiva validata internamente, non ancora rieseguita via bridge esterno Studio |
| TimelineItem transforms esterni | PENDING | Da testare |
| Fusion composition create/read/write da Python esterno | PENDING | Da testare |
| Tracking automatico Studio / IntelliTrack | PENDING | Rivalutare in Studio; vecchio trigger FusionScript Free non affidabile |
| Captions/subtitles automation | PENDING | Da auditare |
| Render queue/export esterno | PENDING | Da auditare |
| ChatGPT -> Secure MCP Tunnel -> MCP bridge | PENDING | MCP locale validato; manca tunnel/custom app |
| ChatGPT -> MCP -> Resolve READ | PENDING | Non ancora provato dalla UI ChatGPT |
| ChatGPT -> MCP -> Resolve WRITE | PENDING | External WRITE validato; manca trasporto ChatGPT + write tool MCP protetta |

## Regola

Un valore `PENDING` non diventa `SUPPORTED` dalla sola documentazione API. Deve essere verificato su questa installazione con un test controllato e con controllo del risultato reale in Resolve.

## Prossimi probe

### 1. ChatGPT/MCP transport gate
- configurare Secure MCP Tunnel sul server MCP locale read-only già validato;
- collegare la custom app a ChatGPT;
- chiedere da ChatGPT `resolve_status`;
- validare `ChatGPT -> MCP -> Resolve READ`.

### 2. MCP WRITE gate
Solo dopo il transport gate:
- esporre una tool innocua e allowlisted `create_safe_working_timeline`;
- creare sempre una nuova timeline;
- verificare che l'originale resti intatto;
- validare `ChatGPT -> MCP -> Resolve WRITE`.
