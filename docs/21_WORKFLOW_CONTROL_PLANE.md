# 21 — Workflow Control Plane

## Per la segreteria

Il controllo iniziale mostra in una sola card il PC che risponde, la versione del bridge, il progetto e la timeline aperti, gli FPS di montaggio e playback e le funzioni disponibili. Non modifica Resolve.

Un lavoro standard deve apparire come una card unica: linea editoriale, target, stato e un solo prossimo passo. Esempio:

```text
Lavoro: Reel podcast ARPHÈ · pronto per revisione
Target: Podcast EP12 / MASTER
Prossimo passo: ascolta i marker R01–R06 e rispondi in un messaggio unico.
Stato: nessun taglio o render è ancora partito.
```

Non serve conoscere ID, tool o JSON. Per modifiche editoriali si risponde normalmente in chat; ChatGPT le traduce nel flusso strutturato e chiede un chiarimento soltanto quando la richiesta è ambigua.

## Garanzie tecniche

- ogni job è locale alla workstation che lo ha creato;
- il target contiene progetto e timeline espliciti;
- un piano deve essere approvato con la sua impronta esatta prima di un avanzamento;
- una ripetizione restituisce l'evidenza già registrata, non crea un secondo output;
- una differenza di workstation, progetto o timeline blocca l'operazione;
- gli FPS di playback sono letti separatamente dagli FPS di timeline e non vengono cambiati dal controllo iniziale.

## Recupero tecnico

Un job `BLOCKED`, `STALE` o `FAILED_RECOVERABLE` non va corretto manualmente sulla timeline. Aprire la card tecnica, verificare target e impronte, quindi riprendere soltanto l'azione indicata. I registri dei workflow specializzati restano la fonte di verità per marker, checkpoint e operazioni Resolve.

## Rollout

`CAP_WORKFLOW_CONTROL_PLANE` è disattivato per default. Il codice non abilita né installa nulla su `PC_PERSONALE` o `PC_SEGRETERIA`. Il primo gate nativo appartiene al personale e richiede un target isolato; la segreteria resta `PENDING` fino alla sua validazione separata, senza toccare progetti aperti, Python, tunnel o configurazioni esistenti.
