# 11 — Creative Bridge 03 + E09 MioDottore Reviews

Data: 2026-09-04

## Stato

`ARPHE_MCP_BRIDGE_CREATIVE_03` è **IMPLEMENTED / OFFLINE TESTED / GATE A PASS / GATES B-G PENDING**.

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
| `CAP_FUSION` | false | sì | no | PENDING — Gate B |
| `CAP_REVIEW` | false | sì | no | PENDING — Gate C/F |
| `CAP_MOTION` | false | sì | no | PENDING — Gate D/E |
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
- nessuna recensione reale hardcoded; per E09 usare testo fittizio finché il content-use check
  MioDottore non è concluso;
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
- nomi input Text+, RectangleMask, Merge e curve Bezier nel contesto external Python;
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

Stato operativo corrente: progetto `ARPHE_E09_MIODOTTORE_REVIEWS_16X9`, timeline
`ARPHE_E09_16X9_V1`, 1920x1080/30, vuota e verificata tramite read-back. Questa è la base da
usare per il Gate B nei prossimi lavori; non modificare né cancellare la V2 verticale.

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

### Gate B — Fusion composition + background + Text+

Prossimo punto di ripartenza. Sul progetto/timeline 16:9 corrente, impostare `CAP_FUSION=true`
nella config locale lasciando tutti gli altri flag avanzati false, quindi chiamare
`create_fusion_composition`, `add_brand_background` e `add_text_plus` con testo fittizio.
Aprire la pagina Fusion dalla barra inferiore di Resolve e verificare MediaOut, canvas e Text+.

### Gate C — Review card statica

Solo dopo Gate B, impostare `CAP_REVIEW=true`. Chiamare `add_review_card` con testo fittizio,
stelle 1-5 e label priva di nome paziente. Verificare card, angoli, shadow, stelle e leggibilità.

### Gate D — ARPHE_SOFT_DROP

Solo dopo Gate C, impostare `CAP_MOTION=true`; chiamare `animate_card_entry` con
`preset="ARPHE_SOFT_DROP"`. Riprodurre la timeline e verificare ingresso dall'alto, rotazione
lieve, decelerazione e micro-settle senza bounce aggressivo.

### Gate E — ARPHE_PAPER_STACK

Creare cinque card fittizie, poi chiamare `animate_review_stack` con stagger 12, overlap 0.25,
rotazioni alternate e durata 18 frame. Verificare ordine, sovrapposizione e z-order.

### Gate F — End card / CTA

Chiamare `add_end_card` con headline e CTA di test, poi `apply_transition_preset` con
`ARPHE_CTA_SETTLE`. Verificare visivamente e salvare soltanto il progetto ARPHE.

### Gate G — render_preview

Non eseguire ora. Dopo un probe controllato di format/codec/render queue, impostare
`CAP_RENDER=true`, renderizzare esclusivamente una preview nella render root allowlisted e
non pubblicarla. Fino ad allora `render_preview` deve restituire capability disabilitata.
