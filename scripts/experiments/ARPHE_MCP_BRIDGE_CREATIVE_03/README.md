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

Stato: **40 TEST PASS / GATE A-B PASS / GATE C STATIC PASS / GATE D PASS / REVIEW SEQUENCE PASS /
GATE E SEQUENCE TRANSITION PASS / PAPER STACK + GATES F-G PENDING**.

Stato operativo E09: progetto `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`; Gate C V5 e timeline
`ARPHE_E09_16X9_GATE_D_V1` sono baseline da conservare. Dal 2026-09-11 il runtime installato
espone 30 azioni, inclusa `create_review_sequence_v2` e il wrapper compatibile
`create_review_sequence`; diagnostica grafo/frame è validata. La V2 usa
una sola composition, divide fino a 150 frame in finestre consecutive e ha superato la verifica visuale sulla timeline
`ARPHE_E09_16X9_SEQUENCE_V5`. `CAP_MOTION` è attiva nella config locale del test; la correzione
BezierSpline è applicata anche alle animazioni. Il retest del 2026-09-14 sulla timeline
`ARPHE_E09_16X9_GATE_E_RETEST_V2` ha verificato quattro ingressi `ARPHE_SOFT_DROP` tramite
catture iniziali/intermedie/finali. Il successivo fix usa finestre sovrapposte di 10 frame e
anima l'opacità sul Transform della sola card, non sul Merge della catena. La timeline
`ARPHE_E09_16X9_GATE_E_OVERLAP_V2` ha confermato card visibili ai confini 37/75/112 e fino al
frame finale 149. La transizione sequenziale è PASS; `ARPHE_PAPER_STACK` resta un gate distinto.

Pubblicazione UI della trentesima azione: **PENDING**. L'aggiornamento manuale è stato completato,
ma la conversazione di verifica espone ancora 29 azioni e non include
`create_review_sequence_v2`; il wrapper `create_review_sequence` resta operativo sulla nuova
implementazione.

Procedura di aggiornamento app ChatGPT già verificata: prima reinstallare la copia runtime con
`install_on_segreteria.ps1` e riavviare in modalità `Creative03`; poi, nella scheda dell'app già
attivata, usare **Modifica → Vedi dettagli → Aggiorna** e attendere il caricamento completo.
L'elenco pubblicato è passato da 28 a 29 azioni per la prima primitiva; il runtime locale è poi
passato a 30 con la firma versionata, ancora da confermare nella console. Per un'app già presente
in **Attivate**, il salvataggio
aggiorna direttamente la versione attiva: in questo flusso non compare un secondo pulsante
**Pubblica**. La pagina amministrativa può richiedere circa 30 secondi o più a causa del numero
di app/azioni; non ricaricarla durante l'attesa.
