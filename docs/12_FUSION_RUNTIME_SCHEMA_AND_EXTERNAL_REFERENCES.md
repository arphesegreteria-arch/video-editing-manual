# 12 — Fusion runtime schema e riferimenti esterni

Data: 2026-09-08

## Regola operativa

Per gli input interni dei nodi Fusion, la fonte decisiva è il read-back della build Resolve
installata. L'ordine è: documentazione Blackmagic della versione locale, introspezione live con
`GetInputList`/`GetInput`, prova controllata, quindi riferimenti GitHub come ipotesi e pattern.

## Schema Text+ osservato su Resolve Studio 21.0.4.5

Probe read-only eseguito sul Text+ della timeline Gate C V4:

| Significato | Input corretto | Evidenza |
|---|---|---|
| risoluzione/canvas | `Width`, `Height` | read-back `1920`, `1080` |
| modalità layout | `LayoutType` | read-back `1.0` per frame |
| larghezza riquadro testo | `LayoutWidth` | input presente; valore live `0.5` |
| altezza riquadro testo | `LayoutHeight` | input presente; valore live `0.5` |
| posizione | `Center` | point `{1: x, 2: y, 3: 0}` |

Esito: usare `Width`/`Height` per contenere il testo è `REJECTED`. Il bridge usa ora
`LayoutWidth`/`LayoutHeight` e verifica i valori con `GetInput` dopo ogni `SetInput` sensibile.

## Idee recuperate dai riferimenti GitHub

### `mvarge/davinci-scripts` — TESTED come metodo diagnostico

Riferimenti:
- https://github.com/mvarge/davinci-scripts/blob/main/RESOLVE_SCRIPTING_GUIDE.md
- https://github.com/mvarge/davinci-scripts/blob/main/RESOLVE_API_REFERENCE.md

Idee adottate:
- non fidarsi del solo valore di ritorno delle proxy Fusion;
- interrogare `GetInputList` e fare read-back degli input effettivi;
- verificare collegamenti e risultato, non solo l'assenza di eccezioni;
- creare nodi temporanei o controllati e rimuoverli esplicitamente con `Delete()`.

La guida contiene anche affermazioni contraddittorie al proprio aggiornamento successivo
sull'inserimento delle Fusion composition. Quindi resta una fonte di tecniche, non autorità.

### `tmoroney/auto-subs` — UNVERIFIED / alternativa architetturale

Riferimento:
- https://github.com/tmoroney/auto-subs/blob/main/Resolve-Integration/README.md

Usa una macro `.setting` nota e versionata come sorgente del grafo Fusion, invece di costruire
ogni nodo ad hoc. È un'opzione promettente se il Gate C programmatico continua a essere fragile:
una card ARPHE potrebbe diventare una macro revisionabile e importabile, con pochi controlli
semantici esposti. Non viene adottata ora perché richiede un gate separato e una procedura di
versionamento dell'asset.

### `velvaiss/auto-subs-davinci-resolve` — UNVERIFIED

Riferimento:
- https://github.com/velvaiss/auto-subs-davinci-resolve

Utile come indice agent-friendly di API Resolve, Fusion, macro `.setting` e animazioni. Le copie
di documentazione incluse nel repository sono snapshot: servono per ricerca, non prevalgono sul
README Blackmagic installato o sui probe ARPHE.

### `czukowski/fusionscript-stubs` — UNVERIFIED

Riferimento:
- https://github.com/czukowski/fusionscript-stubs

Può ridurre errori di firma e migliorare autocomplete. Non può invece validare nomi dinamici
degli input Text+ né il comportamento delle proxy COM/Fusion.

## Correzioni di processo derivate

- Le capability ora distinguono `PARTIAL` da `SUPPORTED` e `PENDING`.
- Gate B è `SUPPORTED`: il V5 ha confermato composizione, canvas, Text+ e grafo pulito.
- Gate C statico è `SUPPORTED`: V2/V3/V4 restano evidenze diagnostiche fallite, mentre V5 ha
  superato read-back e controllo visivo. Highlight ed end card restano `PENDING`.
- `add_review_card` crea prima i Text+ fragili, verifica il read-back e, in caso di errore,
  elimina soltanto i nodi creati dalla chiamata corrente.
- Una macro `.setting` ARPHE resta un possibile asset versionato futuro, non è necessaria per
  dichiarare il PASS della card statica V5.

## Debito di sicurezza Windows

Sul PC segreteria Smart App Control è stato disabilitato per consentire l'esecuzione del client
tunnel non firmato, dopo un blocco Code Integrity/WinError 4551. Il runtime è tornato `ready`, ma
la mitigazione è globale e quindi non è il risultato finale desiderato. Azioni future: binario
firmato o meccanismo di tunnel approvato, hash/versione bloccati e controllo periodico dei log.
