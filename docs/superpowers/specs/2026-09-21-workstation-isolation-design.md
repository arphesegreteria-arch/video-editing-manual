# Workstation Isolation Design

Data: 2026-09-21

Stato: approvato in conversazione; da tradurre in piano di implementazione dopo revisione del
documento.

## Obiettivo

Rendere impossibile confondere `PC_PERSONALE` e `PC_SEGRETERIA` durante installazione,
aggiornamento e uso remoto del bridge Resolve, mantenendo una sola base di codice condivisa.

## Vincoli

- Il PC di segreteria e il PC personale svolgono funzioni differenti.
- Le versioni Python possono differire e devono essere fissate per profilo.
- Nessun aggiornamento della repository deve modificare automaticamente l'altra workstation.
- Nessun segreto deve entrare in Git.
- Le operazioni Resolve devono restare allowlisted e non distruttive per impostazione predefinita.
- Il runtime personale gia' verificato usa Python `3.12.10`.
- Una versione Python gia' validata sull'altra macchina non va sostituita senza un gate dedicato.

## Decisione architetturale

Usare un solo branch stabile `main`, release/tag condivisi e due profili di deployment espliciti.
Ogni profilo definisce identita' workstation, requisiti Python, nomi delle risorse locali,
funzionalita' iniziali e tunnel atteso, senza contenere chiavi.

I branch permanenti per macchina sono esclusi: genererebbero drift, merge ripetuti e correzioni
presenti su un PC ma non sull'altro.

L'autorilevamento completo della workstation e' escluso: nasconderebbe decisioni sensibili e
renderebbe piu' facile applicare una configurazione al PC sbagliato.

## Componenti previsti

### Profili versionati

La repository conterra' due manifest di esempio, uno per workstation. Ogni manifest dichiarera':

- `workstation_id`;
- versione/interprete Python atteso;
- nome task Windows;
- directory di installazione e log;
- nome tunnel atteso e placeholder per il relativo ID;
- bridge e feature flag iniziali;
- controlli richiesti prima di installazione e aggiornamento.

I manifest reali generati localmente resteranno ignorati da Git.

### Installer guidato dal profilo

L'installer ricevera' un profilo esplicito. Prima di scrivere dovra' mostrare workstation,
interprete, destinazione e tunnel; dovra' interrompersi in caso di mismatch con una config locale
esistente. Non dovra' copiare o migrare automaticamente segreti da un'altra macchina.

### Isolamento tunnel

Ogni profilo avra' un tunnel e una Runtime API key propri. L'installer dovra' rifiutare nomi o
identita' note dell'altra workstation quando puo' riconoscerle. La documentazione richiedera' una
app ChatGPT distinta o inequivocabilmente nominata durante test e diagnosi.

### Runtime Python

Le dipendenze saranno installate in una directory o ambiente specifico del profilo. Gli script
non useranno alias generici `py`, `python` o `WindowsApps` nell'autostart: useranno un percorso
assoluto con versione verificata.

## Flusso di aggiornamento

1. Aggiornare il codice da `main`.
2. Selezionare esplicitamente il profilo della macchina corrente.
3. Eseguire preflight senza modifiche.
4. Installare solo nella destinazione del profilo scelto.
5. Preservare config e segreti locali compatibili.
6. Riavviare solo il task della workstation corrente.
7. Verificare runtime, identita', tunnel e Resolve in sola lettura.
8. Eseguire safe-write soltanto come gate separato e su progetto di prova.

Un aggiornamento Git, da solo, non avviera' deployment su alcuna macchina.

## Gestione errori

L'installazione deve interrompersi senza modifiche quando:

- il profilo non coincide con la config locale esistente;
- l'interprete Python non esiste o non ha la versione richiesta;
- il tunnel dichiarato appartiene all'altro profilo;
- il percorso contiene alias WindowsApps;
- il secret store non appartiene all'utente corrente;
- un preflight Resolve richiesto non passa.

Gli errori devono indicare il controllo fallito e la procedura di recupero, senza stampare segreti.

## Sicurezza e dati locali

Runtime API key, DPAPI, log, stato processo, media, transcript e progetti Resolve restano locali.
I log includono workstation e identificatore runtime, ma non token. Le operazioni di scrittura
restano disabilitate finche' il profilo non supera i gate previsti.

## Verifica

La suite dovra' coprire almeno:

- caricamento di entrambi i profili;
- rifiuto di un profilo su workstation/config incompatibile;
- percorsi Python assoluti e versioni differenti;
- assenza di segreti nei manifest versionati;
- installazione simulata senza toccare l'altro profilo;
- tunnel differenti tra i due profili;
- preservazione della config locale durante un aggiornamento compatibile;
- identita' workstation restituita dagli strumenti diagnostici.

Il rollout reale richiede READ PASS indipendente su entrambi i PC. Il safe-write viene eseguito una
workstation alla volta, su progetto di prova, solo dopo aver dimostrato il routing corretto.

## Migrazione

Il tunnel legacy `ARPHE-RESOLVE-HOME` resta temporaneamente associato al PC di segreteria. Il PC
personale ricevera' un nuovo tunnel dedicato. La migrazione non cambiera' automaticamente la
configurazione della segreteria.

L'incidente e la procedura operativa sono documentati in
`docs/15_MULTI_WORKSTATION_ISOLATION_AND_2026-09-21_INCIDENT.md`.
