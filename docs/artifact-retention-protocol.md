# Protocollo di pulizia degli artefatti video

## Ambito rigoroso

Questo protocollo riguarda esclusivamente cartelle, render, diagnostiche e output registrati dei progetti di **video editing ARPHE**. Non autorizza né automatizza la gestione di Downloads generici, documenti, materiale personale, file di altri reparti o file non registrati.

## Separazione per postazione

Ogni postazione gestisce solo i propri file e la propria cartella Drive:

```
ARPHE Projects/
├── PC_PERSONALE/
│   └── <progetto-video>/
└── PC_SEGRETERIA/
    └── <progetto-video>/
```

Non esiste alcuna pulizia trasversale fra `PC_PERSONALE` e `PC_SEGRETERIA`.

## Ciclo di vita locale

1. Un output viene registrato dalla postazione che lo produce.
2. I file idonei restano nel periodo attivo previsto dalla categoria.
3. Possono entrare nella quarantena locale solo se sono registrati, invariati, non protetti e non referenziati da Resolve.
4. Restano in quarantena per **15 giorni completi** dal momento dello spostamento.
5. Solo dopo la scadenza è possibile il purge, e soltanto con policy, inventario e approvazione correnti della stessa postazione.

Il purge non viene mai ereditato dall'altra postazione e rimane disabilitato finché non è attivato e approvato localmente.

## File da tenere

Un render o un output approvato può ricevere un hold esplicito `USER_KEEP`.

- Il hold usa solo l'ID registrato dell'artefatto, mai un percorso libero.
- Se il file è già in quarantena, viene prima ripristinato in modo verificato e poi trattenuto.
- Il rilascio rimuove solo `USER_KEEP`; ricomincia un nuovo periodo attivo prima di qualsiasi futura quarantena.
- I file con hold non vengono puliti né localmente né dalla futura sincronizzazione Drive.

## Drive

Drive ospita esclusivamente gli output approvati dei progetti video ARPHE. La futura pulizia Drive resta separata dalla quarantena locale e richiede una policy dedicata. Non elimina automaticamente file Drive non riconosciuti, esterni ai progetti video o appartenenti all'altra postazione.

## Garanzie

- Nessuna cancellazione su file sconosciuti, cambiati, ambigui o fuori dalle root gestite.
- Nessuna cancellazione di media protetti o importati in Resolve.
- Ogni operazione è registrata con postazione, artefatto e risultato.
