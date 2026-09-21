# 15 - Isolamento workstation e incidente tunnel del 2026-09-21

Questo documento e' il primo riferimento quando una chiamata ChatGPT sembra raggiungere il PC
sbagliato, Resolve risulta raggiungibile solo a intermittenza, oppure due letture simultanee danno
risultati incompatibili.

## Regola operativa vincolante

`PC_SEGRETERIA` e `PC_PERSONALE` sono due ambienti distinti. Devono condividere il codice tramite
questa repository, ma non devono condividere l'identita' operativa.

Per ogni workstation sono obbligatori:

- un tunnel OpenAI dedicato;
- una Runtime API key dedicata, conservata localmente con DPAPI;
- una configurazione locale dedicata;
- un task di avvio Windows dedicato;
- un interprete Python e dipendenze verificati per quella macchina;
- un nome workstation univoco;
- durante sviluppo e diagnosi, una app ChatGPT chiaramente associata al solo tunnel previsto.

Non avviare mai due `tunnel-client` su PC differenti con lo stesso `tunnel_id`. Un tunnel non e'
un selettore di workstation: i client collegati prelevano richieste dalla stessa coda e una
chiamata puo' quindi essere gestita da un ambiente diverso da quello atteso.

## Decisione repository

Il progetto mantiene un solo branch stabile `main` per il codice condiviso. Non creare branch
permanenti `personale` e `segreteria`: divergerebbero e obbligherebbero a duplicare correzioni e
test.

Le differenze tra macchine devono essere espresse con profili di deployment versionati e privi di
segreti. Config reali, chiavi, blob DPAPI, stato runtime, log, media e progetti Resolve restano
fuori dalla repository.

I branch Git restano temporanei e servono solo allo sviluppo di una modifica destinata a tornare
in `main`.

## Incidente del 2026-09-21

### Contesto

Sul `PC_PERSONALE` e' stata completata una prima installazione del bridge usando:

- DaVinci Resolve Studio `21.0.4.5`;
- External scripting impostato su `Local`;
- Python `3.12.10` installato in `C:\Program Files\Python312`;
- runtime identificato come `PC_PERSONALE`;
- progetto Resolve aperto `New Project 4`, senza timeline corrente.

Per la prova iniziale il runtime personale e' stato collegato per errore allo stesso tunnel legacy
`ARPHE-RESOLVE-HOME` gia' usato dal PC di segreteria.

### Sintomi osservati

Una prova remota ha lanciato in parallelo `resolve_status` e `get_feature_flags`:

- una chiamata ha raggiunto Resolve;
- l'altra ha restituito `Resolve non raggiungibile`;
- ripetendo la prova dopo una protezione concorrente nel bridge, l'esito remoto e' rimasto
  incoerente;
- sul PC personale, gli stessi accessi locali e concorrenti sono passati;
- il log del tunnel personale ha registrato un solo comando nell'intervallo dell'ultima prova,
  non due.

### Verifiche effettuate

- `/readyz` sul PC personale: `ready`;
- collegamento locale Python 3.12 -> Resolve: riuscito;
- progetto letto localmente: `New Project 4`;
- suite Creative Bridge: `57` test superati;
- hash dei moduli caricati dal task automatico: uguali alla copia installata;
- serializzazione degli accessi FusionScript aggiunta e verificata localmente;
- il tunnel personale ha registrato solo una delle due richieste remote parallele.

### Diagnosi

La causa piu' probabile, con confidenza alta, e' l'uso contemporaneo dello stesso `tunnel_id` da
parte di due runtime/workstation. Le richieste remote possono essere prelevate da client diversi;
il risultato descrive quindi PC e istanze Resolve differenti.

La conferma assoluta richiede il confronto con il log del PC di segreteria nello stesso intervallo,
ma le prove locali escludono il bridge personale come causa primaria dell'incoerenza remota.

La protezione concorrente aggiunta al bridge resta utile per impedire accessi FusionScript
sovrapposti nella stessa istanza, ma non puo' correggere il routing tra due PC.

## Impatto e misura di sicurezza

Finche' le workstation non hanno tunnel separati:

- non eseguire operazioni di scrittura via ChatGPT;
- non interpretare un singolo `resolve_status` come prova dell'identita' del PC raggiunto;
- usare solo verifiche locali read-only;
- non cambiare il runtime del PC segreteria per correggere quello personale.

## Ripristino corretto

1. Lasciare invariato il PC di segreteria.
2. Creare un tunnel dedicato, nome consigliato `ARPHE-RESOLVE-PERSONALE`.
3. Creare una Runtime API key dedicata al personale con i soli permessi necessari.
4. Aggiornare esclusivamente la configurazione locale di `PC_PERSONALE`.
5. Collegare una app ChatGPT chiaramente denominata al tunnel personale.
6. Verificare `readyz`, `ping`, `resolve_status` e identita' workstation.
7. Solo dopo il READ PASS, eseguire una safe-write su progetto di prova.
8. Verificare separatamente il PC di segreteria e il suo tunnel.

## Handoff rapido per ChatGPT sul PC di segreteria

Se stai leggendo questo documento dal PC di segreteria:

1. non reinstallare Python e non sostituire chiavi come primo tentativo;
2. controlla che la workstation dichiari `PC_SEGRETERIA`;
3. controlla quale `tunnel_id` usa il runtime locale;
4. verifica che il PC personale non stia usando lo stesso ID;
5. esegui prima `readyz` e una lettura locale di Resolve;
6. confronta gli orari delle chiamate con il log runtime;
7. mantieni ogni correzione limitata alla workstation che presenta il problema.

La configurazione locale e i segreti non vanno copiati tra i due PC e non vanno inseriti in Git.

## Riferimento ufficiale

Il funzionamento del client, che esegue long-polling, preleva richieste MCP in coda e le inoltra al
server locale, è descritto nella guida OpenAI Secure MCP Tunnel:
https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
