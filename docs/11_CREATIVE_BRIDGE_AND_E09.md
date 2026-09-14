# 11 — Creative Bridge 03 + E09 MioDottore Reviews

Data: 2026-09-04

## Stato

`ARPHE_MCP_BRIDGE_CREATIVE_03` è **GATE A/B PASS / GATE C STATIC PASS / GATE D PASS /
GATE E MOTION TECHNICAL PASS**.

Non sostituisce né modifica `ARPHE_MCP_BRIDGE_SAFE_WRITE_02`, che resta il fallback validato.
La presenza di codice o di un metodo nella documentazione Resolve non rende una capability
`SUPPORTED`: servono i gate manuali A-G sul PC segreteria.

Formato master deciso: **16:9, 1920x1080, 30 fps**. La timeline verticale validata nel Gate A
resta come evidenza tecnica e possibile adattamento successivo.

## Architettura

```text
ARPHE_MCP_BRIDGE_CREATIVE_03.py
  -> bridge/server.py               MCP e output JSON
  -> bridge/config.py               config/palette/flag locali
  -> bridge/safety.py               validazione e allowlist
  -> bridge/registry.py             progetti, timeline ed elementi creati
  -> bridge/resolve_connection.py   connessione Resolve
  -> bridge/project_tools.py        progetto e save
  -> bridge/timeline_tools.py       timeline/versioni
  -> bridge/fusion_tools.py         composition, canvas e Text+
  -> bridge/creative_tools.py       review card, CTA e motion
  -> bridge/motion_presets.py       preset deterministici
  -> bridge/asset_tools.py          import solo da asset root
  -> bridge/render_tools.py         preview gated
  -> bridge/audit.py                audit senza input sensibili
```

Il registry locale consente di riaprire solo progetti creati/allowlisted e di indirizzare solo
composizioni/card generate dal bridge. Non contiene API key. L'audit salva esclusivamente data,
azione, esito, stage e tipo di errore: non salva recensioni, path, environment o credenziali.

## Superficie MCP

Tool mantenute e già validate nelle build precedenti:

- `ping`
- `resolve_status`
- `create_safe_working_timeline`

Project/timeline:

- `get_feature_flags`
- `create_project`
- `set_current_project`
- `create_timeline`
- `set_current_timeline`
- `duplicate_timeline_version`
- `get_creative_status`
- `save_project`

Fusion/creative semantiche:

- `create_fusion_composition`
- `add_brand_background`
- `add_text_plus`
- `add_review_card`
- `set_review_highlight`
- `add_end_card`
- `animate_card_entry`
- `animate_card_exit`
- `animate_review_stack`
- `apply_transition_preset`
- `retime_creative_duration`

Asset/output:

- `add_logo`
- `add_image_asset`
- `add_video_background`
- `render_preview`

Non esistono `run_python`, `run_shell`, delete project/timeline, generic node/property setter o
eval Fusion. I controlli di radius/shadow/opacity/rotation/position/scale sono interni alle card
e ai preset, non tool MCP arbitrari.

## Feature flags

| Flag | Default | Implemented | Validated | Stato |
|---|---:|---:|---:|---|
| `CAP_PROJECT` | true | sì | parziale | Gate A create/status SUPPORTED; selezione/save PENDING |
| `CAP_TIMELINE` | true | sì | parziale | Gate A create/status SUPPORTED; selezione/versioning PENDING |
| `CAP_FUSION` | false | sì | sì | SUPPORTED — Gate B e grafo pulito V5 |
| `CAP_REVIEW` | false | sì | parziale | PARTIAL — review card statica PASS; highlight/end card PENDING |
| `CAP_MOTION` | false | sì | parziale | PARTIAL — Gate D soft drop PASS; Gate E motion technical PASS, continuità transizioni PENDING |
| `CAP_ASSETS` | false | sì | no | PENDING |
| `CAP_RENDER` | false | sì | no | PENDING — Gate G |

`get_feature_flags` separa `configured`, `implemented`, `technically_available`, `active` e
`validated`. Un flag configurato diventa `active` solo se l'oggetto Resolve corrente espone i
metodi richiesti. Lo stato resta `PENDING` finché il gate non è registrato con evidenza reale.

## Sicurezza

- nomi creati sanificati e prefissati `ARPHE_`, massimo 64 caratteri;
- collisione case-insensitive rifiutata, nessun overwrite;
- nessuna delete di progetto o timeline;
- selezione progetto limitata al registry/config locale;
- selezione timeline limitata a `ARPHE_` o allowlist; ogni write creativa richiede inoltre che
  la timeline sia stata creata/registrata dal bridge oppure esplicitamente allowlisted;
- formati timeline: 1080x1920, 1920x1080 o 1080x1080; FPS 24/25/30;
- frame range limitati e coerenti;
- timing/hold degli elementi incorporato nelle primitive semantiche tramite una finestra Blend;
- recensione massimo 800 caratteri, stelle 1-5, highlight contenuto nel testo iniziale;
- palette limitata a ivory, cream, beige, burgundy, warm_brown, dark_brown, black, white;
- preset limitati a `ARPHE_SOFT_DROP`, `ARPHE_PAPER_STACK`, `ARPHE_ELEGANT_REVEAL`,
  `ARPHE_CTA_SETTLE`;
- immagini/video soltanto sotto `asset_root`, con estensioni allowlisted;
- recensioni reali consentite soltanto se già approvate da ARPHE e anonimizzate; il testo arriva
  come input runtime e non viene hardcoded, registrato nei log o versionato nella repo pubblica;
- `CAP_RENDER=false` iniziale; nessuna pubblicazione automatica.

## Limiti tecnici noti prima dei gate

La documentazione Resolve Studio 21 installata conferma `CreateProject`, `LoadProject`,
`SaveProject`, `CreateEmptyTimeline`, `SetCurrentTimeline`, `DuplicateTimeline`,
`InsertFusionCompositionIntoTimeline`, `AddFusionComp`, `GetFusionCompByIndex`,
`ImportMedia`, `SetRenderSettings` e `AddRenderJob`.

Restano da verificare nel nostro ambiente:

- applicazione di resolution/FPS tramite `Project.SetSetting` prima della creazione della timeline;
- placement della Fusion composition: l'API inserisce al playhead corrente;
- `COMPN_RenderStart/End` regola il work range Fusion, ma non è ancora prova del trim del
  TimelineItem; `retime_creative_duration` lo dichiara esplicitamente;
- input RectangleMask, Merge e curve Bezier nel contesto external Python; per Text+ il probe
  Resolve 21 ha distinto `Width`/`Height` canvas da `LayoutWidth`/`LayoutHeight` frame;
- corrispondenza visiva tra i valori `easing` semantici e l'interpolazione Bezier effettiva;
- z-order visivo e qualità effettiva di shadow, corner radius, micro-settle ed easing;
- semantica `AppendToTimeline` per still/video nei track richiesti;
- formato/codec preview disponibili e comportamento della render queue.

Per questi motivi Fusion/Review/Motion/Assets/Render sono disabilitati di default.

Evidenza Gate A del 2026-09-04: Resolve ha rifiutato `Timeline.SetSetting` subito dopo
`CreateEmptyTimeline`, lasciando la prima V1 a 1920x1080/24. Il bridge ha risposto `ok=false` e
ha interrotto la sequenza. La correzione usa `Project.SetSetting` prima della creazione, soltanto
su progetti creati/allowlisted; resta PENDING fino al retest V2.

Retest V2: **Gate A PASS**. Creati senza overwrite
`ARPHE_E09_MIODOTTORE_REVIEWS_V2` e `ARPHE_E09_VERTICAL_V2`; API e controllo visivo hanno
confermato 1080x1920 e 30 fps. Il PASS copre `create_project`, `create_timeline` e
`get_creative_status`; selezione progetto/timeline, versioning e save restano PENDING.

Base originale: progetto `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`, timeline
`ARPHE_E09_16X9_V1`, 1920x1080/30. I test Gate B/C hanno poi creato timeline versionate fino
alla V4. Non modificare né cancellare la V2 verticale; per il Gate C V5 creare una nuova timeline
16:9 anziché riutilizzare i grafi diagnostici precedenti.

## Installazione affiancata — PC_SEGRETERIA

Non serve cambiare tunnel o runtime API key. Da PowerShell nella repository:

```powershell
cd C:\ARPHE\video-editing-manual
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\experiments\ARPHE_MCP_BRIDGE_CREATIVE_03\install_on_segreteria.ps1
```

Lo script copia la build in:

```text
C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03\
```

e crea, solo se assente, la config locale:

```text
%LOCALAPPDATA%\ARPHE\CreativeBridge03\creative_config.json
```

Non modifica `MCP_COMMAND`. Verificare prima lo switch:

```powershell
Test-Path 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03\ARPHE_MCP_BRIDGE_CREATIVE_03.py'
Get-Content "$env:LOCALAPPDATA\ARPHE\CreativeBridge03\creative_config.json"
```

## Switch runtime al Creative 03

Questo comando ferma e riavvia soltanto il runtime ARPHE, preservando tunnel ID e key DPAPI:

```powershell
.\scripts\experiments\ARPHE_MCP_BRIDGE_CREATIVE_03\switch_runtime_bridge.ps1 -Mode Creative03
Start-Sleep -Seconds 30
.\scripts\windows_bridge\status_bridge.ps1
```

Atteso: `TaskState: Running`, `SupervisorRunning: True`, `Readyz: True`.
In ChatGPT aggiornare/ricollegare la app DEV se il catalogo tool è rimasto in cache.

## Rollback esatto al SAFE_WRITE_02

```powershell
cd C:\ARPHE\video-editing-manual
.\scripts\experiments\ARPHE_MCP_BRIDGE_CREATIVE_03\switch_runtime_bridge.ps1 -Mode SafeWrite02
Start-Sleep -Seconds 30
.\scripts\windows_bridge\status_bridge.ps1
```

Poi da ChatGPT chiamare `ping`: deve rispondere
`bridge=ARPHE_MCP_BRIDGE_SAFE_WRITE_02`. Nessun file o progetto viene cancellato dal rollback.

## Gate manuali A-G

### Gate A — Project + Timeline + status — PASS

Completato il 2026-09-04 con evidenza API e visiva sulla V2 verticale. È stato inoltre creato e
verificato il master operativo 16:9 `ARPHE_E09_16X9_V1` a 1920x1080/30. Non ripetere il Gate A.

### Gate B — Fusion composition + background + Text+ — PASS

Composizione, background e Text+ sono stati creati e osservati sul master 16:9; il V5 ha
confermato un grafo pulito e il viewer corretto. `CAP_FUSION` è `SUPPORTED`.

### Gate C — Review card statica — PASS V5

V2-V4 sono prove diagnostiche rifiutate come risultato grafico. La causa V4 era il frame Text+
impostato tramite `Width`/`Height` (canvas) anziché `LayoutWidth`/`LayoutHeight`. La build V5
corregge lo schema, verifica il read-back e rimuove i soli nodi appena creati in caso di errore.
Il V5 ha confermato contenimento, angoli, shadow, cinque stelle e leggibilità sia via API/read-back
sia nel viewer Resolve. La card statica è PASS; qualità grafica finale, highlight ed end card non
sono comprese in questo PASS.

### Gate D — ARPHE_SOFT_DROP — PASS 2026-09-11

Solo dopo Gate C, impostare `CAP_MOTION=true`; chiamare `animate_card_entry` con
`preset="ARPHE_SOFT_DROP"`. Riprodurre la timeline e verificare ingresso dall'alto, rotazione
lieve, decelerazione e micro-settle senza bounce aggressivo.

Non usare `duplicate_timeline_version` per questo gate: la duplicazione di una timeline non
rimappa ancora nel registry gli ID degli elementi Fusion copiati. Creare invece una timeline
vuota `ARPHE_E09_16X9_GATE_D_V1`, ricreare composition/background/card e animare soltanto i nuovi
ID restituiti. V5 resta intatta.

Abilitazione locale controllata:

```powershell
.\scripts\experiments\ARPHE_MCP_BRIDGE_CREATIVE_03\set_feature_flag.ps1 `
  -Name CAP_MOTION -Enabled $true
.\scripts\experiments\ARPHE_MCP_BRIDGE_CREATIVE_03\switch_runtime_bridge.ps1 -Mode Creative03
```

PASS soltanto se:
- progetto e timeline corrispondono al target Gate D;
- `inspect_fusion_graph` conferma il nuovo grafo;
- tutti gli stati dal frame 0 al 18 sono acquisiti come 19 immagini, in batch massimi da otto;
- V5 non cambia;
- ingresso, opacità, scala, rotazione e micro-settle risultano visivamente coerenti.

Evidenza reale:
- timeline `ARPHE_E09_16X9_GATE_D_V1`;
- composition `ARPHE_COMP_BCB45B060D` e card `ARPHE_CARD_48A11B058C`;
- preset `ARPHE_SOFT_DROP`, keyframe `0`, `15`, `18`;
- grafo Fusion di 19 nodi confermato da `inspect_fusion_graph`;
- 19 immagini restituite e mostrate in ordine per i frame inclusivi `0`-`18`, in batch
  `8 + 8 + 3`, con playhead ripristinato dopo ogni acquisizione;
- tutte le chiamate `ok:true`; nessun save, render o write estranea al gate.

Gate D è quindi PASS. La parte ingresso di `CAP_MOTION` è `SUPPORTED`; la capability aggregata
resta `PARTIAL` fino al Gate E.

### Gate E — motion su sequenza recensioni — TECHNICAL PASS 2026-09-14

Creare cinque card da recensioni reali approvate e anonimizzate, passate a runtime, poi chiamare
`animate_review_stack` con stagger 12, overlap 0.25,
rotazioni alternate e durata 18 frame. Verificare ordine, sovrapposizione e z-order.

Stato diagnostico 2026-09-11: la card statica renderizza correttamente sulla timeline
`ARPHE_E09_16X9_GATE_E_STATIC_V1`, ma l'applicazione delle keyframe (sia `animate_card_entry`
sia `animate_review_stack`) produce uno sfondo vuoto in cattura. Il Gate E resta quindi PENDING;
non promuovere `CAP_MOTION` e non considerare valide le animazioni finché una sequenza animata
non mostra contenuto nei frame iniziali, intermedi e finali. La timeline statica è mantenuta come
baseline di confronto.

La prima implementazione di `create_review_sequence`, con una Fusion composition autonoma per
card inserita a playhead sfalsati, non è valida: `InsertFusionCompositionIntoTimeline()` crea
clip predefinite da 150 frame e gli inserimenti interni spezzano/spostano quelle precedenti. Le
timeline diagnostiche V1-V4 documentano il difetto e non sono baseline.

La versione validata crea invece una sola composition da massimo 150 frame e divide l'intervallo
totale in finestre intere consecutive, una per recensione. È esposta dal runtime come
`create_review_sequence_v2` con `name`, `reviews`, `total_duration_frames` e `style_role`; non
salva recensioni nel codice o nella repository. Il vecchio `create_review_sequence` resta come
wrapper di compatibilità per le chat che hanno già memorizzato il precedente schema. La
timeline `ARPHE_E09_16X9_SEQUENCE_V5` ha verificato in immagine i confini 0/36, 37/74, 75/111 e
112/149: quattro testi corretti, nessun frame vuoto e playhead ripristinato. La causa tecnica
era anche l'ordine di creazione dei modificatori Fusion: il `BezierSpline` deve essere collegato
all'input prima di ricevere i keyframe. La stessa correzione è stata applicata alle curve motion.

Retest reale del 2026-09-14: il progetto salvato
`ARPHE_E09_MIODOTTORE_REVIEWS_16X9` è stato riaperto dal Project Manager dopo il riavvio del PC;
la V5 originale è rimasta intatta ed è stata duplicata nella timeline non distruttiva
`ARPHE_E09_16X9_GATE_E_RETEST_V2`. Sulle quattro card della composition
`ARPHE_COMP_645C1A1DF0` è stato applicato `ARPHE_SOFT_DROP`, ingresso da `top`, durata 10 frame,
`ease_out` e micro-settle. Le finestre/keyframe verificate sono:

- Medicina estetica: `0 / 8 / 10`;
- Ambiente: `37 / 45 / 47`;
- Personale: `75 / 83 / 85`;
- Competenza: `112 / 120 / 122`.

Le catture ai frame iniziale, intermedio, settle e finale di ogni card hanno confermato
opacità, traslazione, scala e assestamento reali; ogni acquisizione ha ripristinato il playhead.
Il motore di animazione è quindi **TECHNICAL PASS**.

Resta un conflitto editoriale aperto: le finestre della V5 sono contigue ma non sovrapposte e
l'animazione imposta opacità zero esattamente ai frame `37`, `75` e `112`. La card precedente è
già terminata, quindi in ciascun cambio compare un frame del solo sfondo. Prima di dichiarare il
Gate E completamente chiuso occorre introdurre overlap/crossfade tra card oppure separare la
visibilità della card dalla sua curva di ingresso. Non correggere questo difetto modificando la
V5: produrre una nuova timeline versionata.

Nota operativa: il refresh della console legge la copia installata sotto `C:\ARPHE\MCP`, non i
file sorgente della repository. Dopo una modifica al bridge eseguire prima
`install_on_segreteria.ps1`, quindi lo switch/restart `Creative03`; solo dopo usare **Modifica →
Vedi dettagli → Aggiorna**. La console amministrativa è lenta con elenchi estesi: attendere almeno
30 secondi senza ricaricare. Se l'app è già in **Attivate**, il salvataggio aggiorna direttamente
lo schema attivo e può non comparire alcun pulsante **Pubblica** separato.

Una modifica della sola firma di un'azione già pubblicata può lasciare **Aggiorna** disabilitato
e mostrare ancora la descrizione precedente. In questo caso non creare una nuova app: aggiungere
nello stesso server un nome versionato (`*_v2`) e mantenere un wrapper compatibile. Il nuovo nome
forza il rilevamento senza rompere le chat esistenti.

Stato console al 2026-09-14: l'aggiornamento manuale della scheda è stato completato, ma questa
conversazione espone ancora 29 azioni e non mostra `create_review_sequence_v2`. Il wrapper
compatibile `create_review_sequence` continua comunque a usare l'implementazione V2 installata.
Trattare quindi la trentesima azione come non pubblicata/non propagata finché una nuova
conversazione non la espone esplicitamente; non creare un'altra app per aggirare la cache.

### Gate F — End card / CTA

Chiamare `add_end_card` con headline e CTA di test, poi `apply_transition_preset` con
`ARPHE_CTA_SETTLE`. Verificare visivamente e salvare soltanto il progetto ARPHE.

### Gate G — render_preview

Non eseguire ora. Dopo un probe controllato di format/codec/render queue, impostare
`CAP_RENDER=true`, renderizzare esclusivamente una preview nella render root allowlisted e
non pubblicarla. Fino ad allora `render_preview` deve restituire capability disabilitata.
