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
| MCP locale: avvio server/tool discovery | SUPPORTED | `ARPHE_MCP_BRIDGE_READ_01`, protocollo MCP negoziato, tool `ping` e `resolve_status` visibili |
| MCP locale -> Resolve READ | SUPPORTED | `resolve_status` ha letto versione, progetto `blabla`, `Timeline 1`, FPS 30, 1V/1A, 130 V1 + 130 A1; exit code 0 |
| Creare timeline vuota da Python esterno | PENDING | `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02` pronto, da eseguire |
| Tornare alla timeline originale via API | PENDING | Incluso nel Write Test 02 |
| Import media da Python esterno | PENDING | Da testare solo dopo Write Test 02 |
| Ricostruire timeline con cut da bridge esterno | PENDING | Primitiva di ricostruzione validata internamente, non ancora rieseguita via controller esterno Studio |
| TimelineItem transforms esterni | PENDING | Da testare |
| Fusion composition create/read/write da Python esterno | PENDING | Da testare |
| Tracking automatico Studio / IntelliTrack | PENDING | Rivalutare in Studio; il vecchio trigger FusionScript in Free era non affidabile |
| Captions/subtitles automation | PENDING | Da auditare |
| Render queue/export esterno | PENDING | Da auditare |
| ChatGPT -> Secure MCP Tunnel -> MCP bridge | PENDING | Il server locale funziona; manca tunnel/custom app |
| ChatGPT -> MCP -> Resolve READ | PENDING | Non ancora provato dalla UI ChatGPT |
| ChatGPT -> MCP -> Resolve WRITE | PENDING | Richiede full MCP + write gate superati |

## Regola

Un valore `PENDING` non diventa `SUPPORTED` dalla sola documentazione API. Deve essere verificato su questa installazione con un test controllato e con controllo del risultato reale in Resolve.

## Prossimi probe

### 1. External WRITE gate
`ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`:
- crea una timeline vuota con nome univoco;
- verifica l'incremento del numero timeline;
- ritorna alla timeline originale;
- non modifica clip o contenuto esistente.

### 2. ChatGPT/MCP transport gate
Dopo il write gate:
- configurare Secure MCP Tunnel sul server MCP locale già validato;
- collegare la custom MCP app a ChatGPT;
- chiedere da ChatGPT `resolve_status`;
- solo dopo aggiungere una write tool innocua e allowlisted.
