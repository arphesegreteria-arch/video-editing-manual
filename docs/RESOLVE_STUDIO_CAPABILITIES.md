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
| Fusion composition create/read/write da Python esterno | PARTIAL | Probe caption 2026-10-02: una composition con 12 Text+, 12 Merge, Background trasparente ed espressioni Blend è stata creata, letta, salvata e verificata via render; manca una primitiva parametrica ripetibile |
| Tracking automatico Studio / IntelliTrack | PENDING | Rivalutare in Studio; vecchio trigger FusionScript Free non affidabile |
| Captions/subtitles automation | SUPPORTED | Vertical Social `CAPTIONS`: Fusion karaoke, due misure fisse e massimo due righe; V4 approvata il 2026-10-31 su `PC_PERSONALE`. Lo styling nativo resta non sufficiente |
| Render queue/export esterno | SUPPORTED | Render completo avviato e monitorato da Python esterno; output 1080x1920/30 verificato visivamente, inclusi caption e gap |
| Creative 03: create progetto ARPHE | SUPPORTED | Gate A V2: creato/selezionato progetto nuovo, nessun overwrite |
| Creative 03: create timeline 1080x1920/30 + status | SUPPORTED | Gate A V2: settings pre-creazione, match API e conferma visiva Resolve |
| Creative 03: create timeline 1920x1080/30 + status | SUPPORTED | Master E09 16:9 creato e verificato via read-back, nessun overwrite |
| Creative 03: load/save progetto ARPHE | PENDING | Implementato, da testare separatamente |
| Creative 03: set/duplicate timeline version | PENDING | Implementato, `DuplicateTimeline` da testare separatamente |
| Creative 03: Fusion composition/background/Text+ | SUPPORTED | Gate B + V5: composizione/canvas/Text+ visibili e grafo pulito |
| Creative 03: review card statica | SUPPORTED | Gate C V5: API/read-back e verifica visiva PASS |
| Creative 03: diagnostica grafo/frame | SUPPORTED | Gate D: grafo Fusion di 19 nodi e cattura completa frame 0-18 in batch 8+8+3, con ripristino playhead |
| Creative 03: review highlight/end card | PENDING | Primitive implementate, Gate F richiesto |
| Creative 03: motion preset/card stack | PARTIAL | Gate D SUPPORTED; Gate E sequence transition PASS con overlap 10 frame e opacità sul Transform, confini 37/75/112 e finale 149 senza buchi; `ARPHE_PAPER_STACK` helper PENDING |
| Creative 03: asset allowlisted | PENDING | Implementato dietro `CAP_ASSETS=false`; import/placement da verificare |
| Creative 03: render preview | PENDING | Implementato dietro `CAP_RENDER=false`; non abilitare prima del Gate G |
| Colorist: versioni colore locali + CDL | PENDING | V2 offline applica CDL fingerprint-bound distinti per clip su nuove versioni locali; API Resolve 21 confermata, `CAP_COLORIST=false`; nuovo gate nativo disposable richiesto |
| Colorist: matching multicamera | PENDING | V2 usa correzioni misurate e CDL diretti per camera; il riferimento è comparativo e `CopyGrades` non è usato dai nuovi piani. Nessun auto-match; gate nativo e review umana richiesti |
| Colorist: preset DRX allowlisted | PENDING | `Graph.ApplyGradeFromDRX` confermata negli stub Resolve 21; nessun DRX configurato o validato visivamente |
| Colorist: preview prima/dopo | PENDING | Toggle reversibile tra versioni locali registrate; nessun cambio pagina/playhead, cattura o render; gate umano richiesto |
| Fairlight: Voice Isolation via scripting | PENDING | Resolve 21.1 installato documenta `Get/SetVoiceIsolationState` su traccia e clip; nessun probe live eseguito. `Amount` è generico e non è un controllo de-reverb separato |
| Fairlight: Dialogue Leveler via proprietà clip | PENDING | Le firme 21.1 documentano proprietà tipizzate; nessun test mutante e nessun parametro promosso a default |
| Fairlight: Dialogue Separator | MANUAL | Il manuale 21.1 conferma Voice/Background/Ambience e vincolo mono-only, ma le API installate non espongono il plugin o i suoi parametri |
| Fairlight: applicazione preset via scripting | PENDING | `GetFairlightPresets` e `ApplyFairlightPresetToCurrentTimeline` sono documentati; tipo, contenuto, destinazione e rollback del preset non sono attestati senza gate mutante isolato |

## Regola

Un valore `PENDING` non diventa `SUPPORTED` dalla sola documentazione API. Deve essere verificato su questa installazione con un test controllato e con controllo del risultato reale in Resolve.

La ricognizione documentale del 24 ottobre 2026 ha rilevato Resolve installato `21.1.1.10`, senza
collegarsi alla sessione o modificare progetti. Le righe Fairlight descrivono esclusivamente firme e
manuale locali; non sostituiscono il gate nativo.

## Milestone raggiunto — 2026-09-01

La catena base è validata end-to-end sia in lettura sia in scrittura non distruttiva:

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> bridge Python locale -> Resolve Studio API`

Il write test da ChatGPT ha creato una sola timeline vuota ARPHE, non ha modificato clip, non ha eliminato timeline e ha ripristinato automaticamente `Timeline 1` come timeline corrente.

## Prossimi probe

1. Installare affiancato Creative 03 e svolgere Gate A senza contenuti reali.
2. Svolgere Gate B-G separatamente, promuovendo una riga a `SUPPORTED` solo con evidenza reale.
3. Testare `list_media` e accesso a una cartella allowlisted nel track editoriale separato.
4. Esporre `transcribe_media` e validare un `apply_edit_plan` minimale su una nuova timeline.
