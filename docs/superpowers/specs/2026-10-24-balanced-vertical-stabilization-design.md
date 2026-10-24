# Stabilizzazione verticale equilibrata

## Intento

Ridurre il galleggiamento residuo del video `peeling` senza bloccare artificialmente l'inquadratura. Il test resta sul solo PC_PERSONALE e deve produrre una nuova timeline provvisoria separata.

## Obiettivi e vincoli

- Conservare la correzione di rotazione già misurata.
- Correggere anche lo spostamento verticale rilevato sulla linea del soffitto, pari a circa 41 pixel sull'intera clip.
- Usare solo coordinate e fotogrammi espliciti, misurati; nessun riconoscimento automatico del soggetto o dell'orizzonte.
- Conservare il sorgente, la timeline precedente e una sola copia dell'audio.
- Applicare uno zoom conservativo iniziale di `1.08`, aumentando solo se il read-back visivo mostra bordi scoperti.
- Non salvare il progetto prima del controllo umano.

## Approcci considerati

1. **Stabilizzazione equilibrata — scelta:** keyframe espliciti di posizione verticale, smussati rispetto alle misure, con movimento naturale residuo.
2. **Blocco quasi totale:** linea del soffitto fissa a ogni campione; scartato perché richiede più zoom e può sembrare robotico.
3. **Solo rotazione più fitta:** scartato perché la rotazione residua è già entro circa `±0.28°`; il difetto dominante è la deriva verticale.

## Disegno tecnico

- Estendere l'azione generica `REFRAME` con `center_keys`, una lista ordinata di `{frame, x, y}` ancorata al primo e all'ultimo frame dell'intervallo.
- Validare numeri finiti, ordine, limiti sicuri e presenza degli estremi; nessun valore implicito ricavato dal nome del progetto o della timeline.
- Applicare i punti a un controllo Fusion posseduto da Resolve e leggerli nuovamente prima di dichiarare l'azione verificata.
- Creare prima test automatici fallenti per validazione, normalizzazione su timeline non-zero e read-back delle coordinate.
- Sul video reale, calibrare la direzione del controllo con una prova minima; poi generare una nuova timeline provvisoria e catturare almeno i 25 fotogrammi già misurati.
- Accettare il risultato solo se la deriva verticale diminuisce senza bordi neri, deformazioni, tagli o duplicazione dell'audio.

## Fuori ambito

- Riduzione del rimbombo audio.
- Conversione definitiva in Short 1080x1920.
- Salvataggio del progetto, render finale o aggiornamento del PC_SEGRETERIA.
