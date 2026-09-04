# Resolve Studio Capability Matrix

Ambiente di riferimento corrente:
- Windows;
- DaVinci Resolve Studio `21.0.4.5`;
- `External scripting using = Local`;
- Python esterno;
- Python MCP SDK v2;
- Secure MCP Tunnel con `tunnel-client-runtime-cloudflared`;
- ChatGPT Business custom MCP app in developer mode.

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
| MCP locale: avvio server/tool discovery | SUPPORTED | `ARPHE_MCP_BRIDGE_READ_01`, tool `ping` e `resolve_status` |
| MCP locale -> Resolve READ | SUPPORTED | `resolve_status` ha letto Resolve reale senza modifiche |
| Secure MCP Tunnel runtime -> MCP locale | SUPPORTED | tunnel `ARPHE-RESOLVE-HOME`, `/readyz` -> HTTP 200 `ready` |
| ChatGPT custom MCP app -> tunnel | SUPPORTED | draft DEV `ARPHE Resolve` collegata con auth None |
| ChatGPT -> MCP -> Resolve READ | SUPPORTED | chiamata reale `resolve_status` da chat: Resolve 21.0.4.5, progetto `blabla`, `Timeline 1`, 30 fps, 130 V1 + 130 A1 |
| ChatGPT -> MCP -> Resolve SAFE WRITE | SUPPORTED | `create_safe_working_timeline`: timeline count 3 -> 4, creata `ARPHE_CHATGPT_WRITE_TEST_20260901_185749`, ritorno a `Timeline 1`, 0 clip edit, 0 timeline delete |
| Import media da Python esterno | PENDING | Da testare |
| Ricostruire timeline con cut da bridge esterno | PENDING | Primitiva validata internamente, non ancora rieseguita via bridge esterno Studio/MCP |
| TimelineItem transforms esterni | PENDING | Da testare |
| Fusion composition create/read/write da Python esterno | PENDING | Da testare |
| Tracking automatico Studio / IntelliTrack | PENDING | Rivalutare in Studio; vecchio trigger FusionScript Free non affidabile |
| Captions/subtitles automation | PENDING | Da auditare |
| Render queue/export esterno | PENDING | Da auditare |
| Creative 03: create progetto ARPHE | SUPPORTED | Gate A V2: creato/selezionato progetto nuovo, nessun overwrite |
| Creative 03: create timeline 1080x1920/30 + status | SUPPORTED | Gate A V2: settings pre-creazione, match API e conferma visiva Resolve |
| Creative 03: create timeline 1920x1080/30 + status | SUPPORTED | Master E09 16:9 creato e verificato via read-back, nessun overwrite |
| Creative 03: load/save progetto ARPHE | PENDING | Implementato, da testare separatamente |
| Creative 03: set/duplicate timeline version | PENDING | Implementato, `DuplicateTimeline` da testare separatamente |
| Creative 03: Fusion composition/background/Text+ | PENDING | Implementato dietro `CAP_FUSION=false`; Gate B richiesto |
| Creative 03: review card/highlight/end card | PENDING | Implementato dietro `CAP_REVIEW=false`; Gate C/F richiesti |
| Creative 03: motion preset/card stack | PENDING | Implementato dietro `CAP_MOTION=false`; Gate D/E richiesti |
| Creative 03: asset allowlisted | PENDING | Implementato dietro `CAP_ASSETS=false`; import/placement da verificare |
| Creative 03: render preview | PENDING | Implementato dietro `CAP_RENDER=false`; non abilitare prima del Gate G |

## Regola

Un valore `PENDING` non diventa `SUPPORTED` dalla sola documentazione API. Deve essere verificato su questa installazione con un test controllato e con controllo del risultato reale in Resolve.

## Milestone raggiunto — 2026-09-01

La catena base è validata end-to-end sia in lettura sia in scrittura non distruttiva:

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio API`

Il write test da ChatGPT ha creato una sola timeline vuota ARPHE, non ha modificato clip, non ha eliminato timeline e ha ripristinato automaticamente `Timeline 1` come timeline corrente.

## Prossimi probe

1. Installare affiancato Creative 03 e svolgere Gate A senza contenuti reali.
2. Svolgere Gate B-G separatamente, promuovendo una riga a `SUPPORTED` solo con evidenza reale.
3. Testare `list_media` e accesso a una cartella allowlisted nel track editoriale separato.
4. Esporre `transcribe_media` e validare un `apply_edit_plan` minimale su una nuova timeline.
