# ARPHE_MCP_BRIDGE_CREATIVE_03

Bridge MCP sperimentale, affiancato ai bridge validati e dedicato alle creative social E09.

- Entry point: `ARPHE_MCP_BRIDGE_CREATIVE_03.py`
- Config locale: `%LOCALAPPDATA%\ARPHE\CreativeBridge03\creative_config.json`
- Asset allowlist predefinita: `C:\ARPHE\MCP\assets\creative`
- Render root predefinita: `C:\ARPHE\MCP\renders\creative`
- Audit minimale: `%LOCALAPPDATA%\ARPHE\CreativeBridge03\audit.jsonl`

Installazione, tool, flag, gate e rollback sono documentati in
`docs/11_CREATIVE_BRIDGE_AND_E09.md`.

Le feature progressive si modificano nella config locale, senza cambiare lo schema MCP, tramite
`set_feature_flag.ps1`; dopo la modifica riavviare il runtime Creative03.

Stato: **35 TEST PASS / GATE A-B PASS / GATE C STATIC PASS / GATES D-G PENDING**.

Stato operativo E09: progetto `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`; Gate C V5 è la baseline
visiva da conservare. L'app ChatGPT espone 28 azioni e la cattura frame MCP è validata. Prossimo
gate: D su una nuova timeline versionata, con `CAP_MOTION` abilitata e V5 lasciata intatta.
