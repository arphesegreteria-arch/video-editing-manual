# Bridge riusabile per trasformazioni di media esistenti

Data: 24 ottobre 2026.

Stato: proposta tecnica minima, solo documentazione. Non abilita capability, non modifica Resolve e
non implementa ancora funzioni Fairlight.

## Obiettivo operativo

La segretaria descrive in linguaggio naturale una modifica da apportare a un video o audio fornito.
Il bridge traduce la richiesta in un piano tipizzato e verificabile per **modificare materiale
esistente**, non per generare da zero contenuti sostitutivi. Quando la correzione non è supportata o
non è verificabile, il risultato corretto è un limite dichiarato e una proposta di test, non un effetto
approssimato presentato come equivalente.

## Architettura obbligatoria

1. **Intento naturale.** Il testo dell'operatrice viene normalizzato in obiettivo, materiale target,
   priorità, tolleranze e vincoli. Il prompt non diventa mai un comando Resolve libero.
2. **Analisi e capability.** Il bridge identifica formato, tracce, durata, fingerprint, stato del
   progetto e primitive realmente documentate o validate sulla workstation. L'analisi è read-only.
3. **Selezione verificata.** Solo azioni tipizzate e preset versionati compatibili con il materiale
   possono entrare nel piano. Parametri e limiti derivano dall'analisi, da un contratto validato o da
   una scelta umana; non esistono valori universali impliciti.
4. **Esecuzione non distruttiva.** Dopo fingerprint e approvazione, l'azione opera su una copia,
   versione o timeline isolata e produce un nuovo output. Sorgente e riferimenti restano immutati.
5. **Verifica e output.** Il bridge controlla formato, durata, sincronismo, struttura, fingerprint e
   metriche pertinenti, quindi espone confronto prima/dopo e review umana. Un fallimento lascia un
   checkpoint recuperabile e non promuove la capability.

## Contratto e assenza di hardcoding

Il contratto non contiene nomi di progetti o video, percorsi assoluti, durate attese, nomi di output o
parametri creativi legati a un caso storico. Questi valori sono input validati o dati derivati. Un
preset è identificato da nome logico, versione, capability richieste, intervalli consentiti e prova di
compatibilità; non è un insieme di valori dichiarati adatto a ogni video.

Gli esempi e gli artefatti prodotti durante i gate precedenti sono evidenza, non configurazione. Un
nuovo media deve poter attraversare lo stesso flusso senza rinominare codice, cambiare costanti o
riutilizzare fingerprint di un lavoro precedente.

## Superficie minima futura

- `inspect_media_transform`: lettura del media e delle capability, senza scritture;
- `prepare_media_transform`: traduzione dell'intento in piano tipizzato e fingerprintato;
- `approve_media_transform`: consenso umano sul piano esatto;
- `apply_media_transform`: esecuzione su copia/versione isolata, dietro capability default-off;
- `verify_media_transform`: confronto tecnico e pacchetto di review prima/dopo;
- `reject_or_accept_media_transform`: decisione umana finale senza sostituzione automatica.

Ogni famiglia di trasformazioni mantiene il proprio vocabolario chiuso. Non viene esposto un tool
generico capace di invocare metodi Resolve arbitrari o passare parametri non validati.

## Provenienza e igiene

Sorgente, output, manifest, piano approvato e prove di review sono artefatti `PROTECTED` collegati da
fingerprint. Un file sconosciuto resta `UNCLASSIFIED_PROTECTED`. La manutenzione non deduce mai che
un media sia eliminabile dal nome, dall'estensione, dall'età o dal fatto che esista un output più
recente. Solo artefatti tecnici esplicitamente registrati come disposable possono diventare candidati.

## Audio e Fairlight

La ricognizione locale di Resolve 21.1 conferma API documentate per Voice Isolation e Dialogue
Leveler, e conferma Dialogue Separator nell'app Studio con controlli separati Voice, Background e
Ambience. Non è documentata un'API diretta per Dialogue Separator. I metodi per elencare e applicare
preset Fairlight non attestano tipo, contenuto, destinazione o rollback del preset.

Di conseguenza l'audio/Fairlight resta `PENDING`/`MANUAL`: nessun modulo viene implementato e nessun
test mutante viene eseguito finché l'utente non sceglie un percorso e non autorizza un gate su copia
isolata. Gate, EQ e denoise non devono essere descritti come de-reverb.

## Criteri di arresto

Il bridge si ferma prima della scrittura se la sorgente è cambiata, la capability manca, il piano è
stale, il target non è isolato, il preset non è attestabile o la verifica richiesta non è disponibile.
Il messaggio all'operatrice indica cosa non è correggibile automaticamente, quale rischio rimane e il
test minimo eventualmente necessario. Non promette la rimozione completa di rumore, eco, difetti di
colore o altri problemi percettivi.
