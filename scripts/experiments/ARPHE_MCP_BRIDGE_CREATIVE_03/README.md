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

Stato: **50 TEST PASS / GATE A-B PASS / GATE C STATIC PASS / GATE D PASS / REVIEW SEQUENCE PASS /
GATE E SEQUENCE TRANSITION PASS / PAPER STACK + GATES F-G PENDING**.

Il modulo longform aggiunge nove azioni gated: lettura media/transcript, validazione e applicazione
del piano, restauro asincrono dell'intera sorgente audio e batch Deliver separato. `CAP_LONGFORM` è
disabilitata di default. L'ordine corretto è: completare il WAV restaurato, passarlo a
`apply_longform_edit_plan`, poi preparare un job per ogni timeline-estratto. L'applicazione crea
sempre un progetto nuovo, una master timeline e una timeline per ogni estratto (massimo 32, massimo
180 secondi ciascuno); non sovrascrive né salva automaticamente.

`ARPHE_DIALOGUE_CLEAN_V1` usa passa-alto, denoise conservativo, compressore moderato e limiter.
Produce PCM WAV 48 kHz stereo e rifiuta il risultato se la durata differisce di oltre un frame.
`ARPHE_DIALOGUE_LEVEL_V2` aggiunge un livellamento dinamico locale per registrazioni con voci a
distanze diverse dal microfono. Recupera fino a circa 12 dB, ignora i tratti sotto la soglia voce,
usa transizioni morbide e conserva il limiter finale. Non esegue diarizzazione: il gate umano deve
verificare che rumore ambientale e respiri non vengano sollevati in modo innaturale.
`ARPHE_DIALOGUE_DISTANT_V3` è il preset di recupero per una seconda voce registrata lontano:
usa denoise più deciso, un rinforzo moderato della presenza intorno a 3,2 kHz, livellamento locale
fino a circa 18 dB e compressione controllata. È intenzionalmente conservato come preset separato,
perché richiede ascolto comparativo prima dell'uso sul montaggio completo. Non sostituisce due
microfoni separati: il recupero selettivo dei turni può amplificare ambiente e riverbero e va
scartato quando peggiora l'ascolto.
`queue_longform_exports` non avvia il render; l'avvio resta separato e protetto da `CAP_RENDER`.

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

Pubblicazione UI: **35 AZIONI CONFERMATE** il 2026-09-15, incluse le cinque primitive longform.
Il runtime reale espone `CAP_LONGFORM=true` ed è stato verificato con `/readyz` HTTP 200, `ping` e
`get_feature_flags`. I task già aperti possono conservare il catalogo precedente: usare un nuovo
contesto per il primo test delle azioni appena pubblicate.

Stato codice successivo: **39 AZIONI / 52 TEST PASS**. Le quattro nuove azioni audio/export e il
parametro `enhanced_audio_path` richiedono ancora **Aggiorna** nella scheda amministrativa dell'app;
fino a quel momento la versione attiva mostra correttamente 35 azioni.

Procedura di aggiornamento app ChatGPT già verificata: prima reinstallare la copia runtime con
`install_on_segreteria.ps1` e riavviare in modalità `Creative03`; poi, nella scheda dell'app già
attivata, usare **Modifica → Vedi dettagli → Aggiorna** e attendere il caricamento completo.
L'elenco pubblicato è passato da 28 a 29 azioni per la prima primitiva; il runtime locale è poi
passato a 30 con la firma versionata, ancora da confermare nella console. Per un'app già presente
in **Attivate**, il salvataggio
aggiorna direttamente la versione attiva: in questo flusso non compare un secondo pulsante
**Pubblica**. La pagina amministrativa può richiedere circa 30 secondi o più a causa del numero
di app/azioni; non ricaricarla durante l'attesa.
