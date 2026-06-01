# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it-IT/1.0.0/)
e il progetto aderisce al [Semantic Versioning](https://semver.org/lang/it/).

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
