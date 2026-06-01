# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it-IT/1.0.0/)
e il progetto aderisce al [Semantic Versioning](https://semver.org/lang/it/).

## [1.3.0] - 2026-06-01

### Added
- **`get_quotes`** (nuovo modulo `quotes.py`): tool **read-only** dedicato ai PREVENTIVI (issued_documents `type="quote"`). Per ogni preventivo: numero, data, cliente, oggetto, validita' (`next_due_date`), data "visto dal cliente" (`seen_date`), importi (imponibile/totale) e link al PDF. Filtri: `from_date`, `to_date`, `client_name`, `limit`.

  **Motivazione del cambiamento.** Prima i preventivi erano *tecnicamente* leggibili ma in modo sporco: `get_invoices` cicla tutti i tipi di documento emesso (`invoice`, `credit_note`, `order`, `quote`, `proforma`...) e li restituisce in un unico elenco etichettato genericamente come "fatture", senza i campi tipici del preventivo (validita', stato "visto", oggetto) e senza poterli filtrare per tipo. Questo rendeva i preventivi di fatto inutilizzabili in modo affidabile (rischio di confondere un preventivo con una fattura emessa). Il nuovo tool li isola e li espone con la semantica corretta, gemello read-only di `get_received_credit_notes`. Nessuna scrittura, nessun problema di scope (token `issued_documents:r` sufficiente).

- **5 tool di SCRITTURA magazzino** (nuovo modulo `products_write.py`): `product_update_stock` (carico/scarico/rettifica giacenza), `product_update_category`, `product_update_fields` (net_cost/net_price/name/code/measure/notes), `product_create`, `product_delete`. Pattern **read-modify-write** (FIC non ha movimenti di magazzino giornalizzati). Pensati per lo step carico/scarico di `prep-bilancio`.
  - **Guardrail (doppia barriera):** env flag globale `FIC_ALLOW_WRITE` (default off) + parametro `confirm` per ogni tool. Senza `confirm` ogni tool esegue un **dry-run** con anteprima "prima -> dopo"; con `confirm` ma senza `FIC_ALLOW_WRITE=true` la scrittura e' **rifiutata**. Scarico bloccato sotto zero. Ogni scrittura effettiva e' loggata. Una scrittura per chiamata, nessun batch.
  - **Campo giacenza:** `STOCK_FIELD="stock_initial"` (scelta semantica FIC). **Non ancora verificato empiricamente:** al 2026-06-01 il token OAuth di produzione e' read-only e FIC risponde `403 NO_PERMISSION` sulle modifiche. Per abilitare la scrittura serve ri-autorizzare il token con scope di scrittura prodotti (`products:a` in `auth_setup.py`), poi completare il test su un articolo non critico e confermare `STOCK_FIELD`.

Totale tool: **28** (10 categorie).

[1.3.0]: https://github.com/maxmost-hestro/fattureincloud-mcp-server/compare/v1.2.0...v1.3.0

## [1.2.0] - 2026-06-01

### Added
- **`get_products`** e **`get_product_categories`**: nuovo modulo `products.py` con due tool **read-only** per il catalogo articoli / magazzino (SDK `ProductsApi.list_products` + `InfoApi.list_product_categories` con `context="products"`). Per ogni articolo: categoria, unita' di misura, costo unitario (`net_cost`/`average_cost`), giacenza (`stock_initial`/`stock_current`), prezzo; riepilogo per categoria con valore giacenza = `sum(stock_current * net_cost)`. Nessuna scrittura su FIC. Pensati per il progetto `prep-bilancio`: valorizzazione delle rimanenze di magazzino al 31/12. Totale tool: **22** (8 categorie).

[1.2.0]: https://github.com/maxmost-hestro/fattureincloud-mcp-server/compare/v1.1.0...v1.2.0

## [1.1.0] - 2026-06-01

### Added
- **`get_received_credit_notes`**: nuovo tool per le note di credito PASSIVE ricevute dai fornitori (tipo documento `passive_credit_note`). Gemello di `get_received_invoices` (stessa paginazione intelligente, filtro fornitore e formato output), include sempre descrizione completa e righe di dettaglio per consentire il matching con le fatture originali. Pensato per il progetto `prep-bilancio`: verifica degli storni su fatture passive (resi, errori, difettosita) ed esclusione dei relativi cespiti. Totale tool: **20**.

[1.1.0]: https://github.com/maxmost-hestro/fattureincloud-mcp-server/compare/v1.0.0...v1.1.0

## [1.0.0] - 2026-03-14

### Added
- **20 tools** organizzati in 7 categorie
- **Fatture emesse**: lista con filtri e dettaglio singola fattura
- **Pagamenti**: fatture scadute e dashboard riepilogo pagamenti
- **Clienti**: anagrafica completa e fatture per cliente
- **Spese**: fatture ricevute, dettaglio, non pagate, aggregazione mensile
- **Analytics**: fatturato mensile, per cliente (Pareto), statistiche annuali con breakdown trimestrale
- **Info azienda**: dati aziende associate all'account
- **Solleciti e analisi crediti**:
  - Netting FIFO automatico delle note di credito
  - Aging report con fasce standard (1-30, 31-60, 61-90, 90+ giorni)
  - Dati strutturati per generazione solleciti
  - Analisi comportamento pagamenti cliente (DSO, trend, rating)
  - Coda priorita' solleciti con score pesato
- Paginazione automatica su tutte le chiamate API
- Doppia modalita' di trasporto: stdio e HTTP/SSE
- Setup OAuth2 interattivo tramite `auth_setup.py`
- Deploy Docker con Dockerfile pronto
- Documentazione completa in italiano

[1.0.0]: https://github.com/maxmost-hestro/fattureincloud-mcp-server/releases/tag/v1.0.0
