# Resolve retirement archive-first — implementation plan

1. Estendere config, esempio e installer con `CAP_RESOLVE_RETIREMENT=false`, archive root e
   registry per-workstation; aggiungere test di migrazione e isolamento.
2. Aggiungere un registry atomico per proposte e archivi, fingerprint deterministico e policy
   `30 giorni + ultimi 3`; testare schema, workstation mismatch e classificazione retention.
3. Implementare prepare: validazione ARPHÈ, save, export `.drp`, hash, last-modified e render-lock;
   nessuna rimozione. Testare tutti i fail-closed.
4. Implementare approvazione tecnica ed execute idempotente per timeline e progetto, con verifica
   precondizioni e postcondizioni. Testare mutazioni, archivio alterato, target corrente e recovery
   dopo errore.
5. Implementare recovery come import sotto nome `ARPHE_RECOVERY_...`, senza overwrite.
6. Esporre i cinque tool MCP, aggiornare capability report e documentazione.
7. Eseguire suite Creative e Windows completa, installare soltanto sul PC personale con gate
   spento e verificare inspection read-only. Un gate distruttivo live resta PENDING finché esiste
   un target disposable e Resolve è raggiungibile.
