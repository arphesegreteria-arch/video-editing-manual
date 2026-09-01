# Resolve Studio Capability Matrix

Ambiente di riferimento corrente:
- Windows;
- DaVinci Resolve Studio `21.0.4.5`;
- `External scripting using = Local`;
- Python esterno.

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
| Creare timeline vuota da Python esterno | PENDING | `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02` pronto, da eseguire |
| Tornare alla timeline originale via API | PENDING | Incluso nel Write Test 02 |
| Import media da Python esterno | PENDING | Da testare solo dopo Write Test 02 |
| Ricostruire timeline con cut da bridge esterno | PENDING | Primitiva di ricostruzione validata internamente, non ancora rieseguita via controller esterno Studio |
| TimelineItem transforms esterni | PENDING | Da testare |
| Fusion composition create/read/write da Python esterno | PENDING | Da testare |
| Tracking automatico Studio / IntelliTrack | PENDING | Rivalutare in Studio; il vecchio trigger FusionScript in Free era non affidabile |
| Captions/subtitles automation | PENDING | Da auditare |
| Render queue/export esterno | PENDING | Da auditare |
| ChatGPT -> MCP -> Resolve READ | PENDING | Architettura definita in `08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md` |
| ChatGPT -> MCP -> Resolve WRITE | PENDING | Richiede full MCP + Gate 1-4 |

## Regola

Un valore `PENDING` non diventa `SUPPORTED` dalla sola documentazione API. Deve essere verificato su questa installazione con un test controllato e con controllo del risultato reale in Resolve.

## Prossimo probe

`ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`:
- crea una timeline vuota con nome univoco;
- verifica l'incremento del numero timeline;
- ritorna alla timeline originale;
- non modifica clip o contenuto esistente.
