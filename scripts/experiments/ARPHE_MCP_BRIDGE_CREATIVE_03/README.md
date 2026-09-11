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

Stato: **35 TEST PASS / GATE A-B PASS / GATE C STATIC PASS / GATE D PASS / GATES E-G PENDING**.

Stato operativo E09: progetto `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`; Gate C V5 e timeline
`ARPHE_E09_16X9_GATE_D_V1` sono baseline da conservare. Dal 2026-09-11 l'app ChatGPT attiva
espone 29 azioni, inclusa `create_review_sequence`; diagnostica grafo/frame e
`ARPHE_SOFT_DROP` sono validate. `CAP_MOTION` è attiva nella config locale del test. Prossimo
passaggio: validare visivamente la nuova sequenza su una timeline separata, lasciando intatte le
baseline.

Aggiornamento app ChatGPT verificato: prima reinstallare la copia runtime con
`install_on_segreteria.ps1` e riavviare in modalità `Creative03`; poi, nella scheda dell'app già
attivata, usare **Modifica → Vedi dettagli → Aggiorna** e attendere il caricamento completo.
L'elenco è passato da 28 a 29 azioni. Per un'app già presente in **Attivate**, il salvataggio
aggiorna direttamente la versione attiva: in questo flusso non compare un secondo pulsante
**Pubblica**. La pagina amministrativa può richiedere circa 30 secondi o più a causa del numero
di app/azioni; non ricaricarla durante l'attesa.
