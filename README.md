# FattureInCloud MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Un server [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) completo che collega assistenti AI come Claude alla piattaforma di fatturazione [Fatture in Cloud](https://www.fattureincloud.it/).

**20 tools** organizzati in 7 categorie che vanno ben oltre il semplice wrapping delle API — aggiungendo paginazione automatica, netting delle note di credito, analisi aging, scoring comportamento pagamenti e dati strutturati per i workflow di sollecito.

---

## Perche' questo progetto

Le API di Fatture in Cloud sono potenti ma di basso livello: interroghi un tipo di documento alla volta, pagini manualmente e ottieni dati grezzi che richiedono post-elaborazione per qualsiasi insight di business reale.

Questo MCP server si interpone tra il tuo assistente AI e le API, aggiungendo un **layer di logica di business** che trasforma i dati contabili grezzi in informazioni operative — il tutto accessibile tramite linguaggio naturale.

### Cosa ottieni rispetto alle API standard

| Funzionalita' | API FIC | Questo MCP Server |
|---|---|---|
| Lista fatture | Un tipo di documento per chiamata, paginazione manuale | Tutti i tipi di documento in una chiamata, paginazione automatica su tutte le pagine |
| Stato pagamento | Array `payments_list` grezzo | Stato calcolato (pagata/parziale/non pagata), importo residuo, estrazione scadenza con logica di fallback |
| Gestione note di credito | Query separate, riconciliazione manuale | **Netting FIFO automatico** — le NC vengono abbinate alle fatture per cliente, dalla piu' vecchia |
| Fatture scadute | Nessun concetto nativo | Rilevamento intelligente con calcolo giorni di ritardo, raggruppate per gravita' |
| Aging report | Non disponibile | Fasce standard (1-30, 31-60, 61-90, 90+ giorni) con netting NC automatico |
| Analytics fatturato | Non disponibile | Mensile, trimestrale, annuale, per cliente — tutto pre-aggregato |
| Analytics spese | Non disponibile | Aggregazione mensile spese con filtro fornitore |
| Comportamento pagamenti cliente | Non disponibile | Calcolo DSO, % ritardi, trend anno su anno, rating affidabilita' |
| Priorita' solleciti | Non disponibile | Coda priorita' pesata: `importo * log(giorni) * sqrt(fatture)` |
| Dati per solleciti | Non disponibile | Output strutturato con contatti cliente + fatture scadute, pronto per generare email |

---

## Architettura

```
fattureincloud-mcp-server/
├── server.py              # Entry point — registra tutti i tools, supporta stdio + SSE + streamable-http
├── auth_setup.py          # Wizard interattivo per setup OAuth2
├── src/
│   ├── config.py          # Configurazione API (token OAuth2, company ID)
│   ├── utils.py           # Utility condivise (estrazione stato pagamento)
│   └── tools/
│       ├── invoices.py    # Documenti emessi (2 tools)
│       ├── payments.py    # Pagamenti e scadenze (2 tools)
│       ├── clients.py     # Gestione clienti (2 tools)
│       ├── expenses.py    # Documenti ricevuti e spese (4 tools)
│       ├── analytics.py   # Statistiche e report fatturato (3 tools)
│       ├── info.py        # Informazioni azienda (1 tool)
│       └── reminders.py   # Solleciti e analisi crediti (5 tools)
├── Dockerfile             # Container per deploy remoto
└── requirements.txt       # Dipendenze Python
```

### Modalita' di trasporto

| Modalita' | Caso d'uso | Comando |
|---|---|---|
| **stdio** (default) | Claude Code, Claude Desktop | `python server.py` |
| **streamable-http** | claude.ai, deploy remoto (MCP 2025-03-26) | `python server.py --transport streamable-http --port 3002` |
| **sse** | Legacy HTTP/SSE | `python server.py --transport sse --port 3002` |

---

## Riferimento Tools (20 totali)

### Fatture emesse (2 tools)

| Tool | Descrizione |
|---|---|
| `get_invoices` | Lista documenti emessi con filtri (intervallo date, nome cliente, stato pagamento). Interroga tutti i tipi di documento (fatture, note di credito, ricevute, ecc.) con paginazione automatica. |
| `get_invoice` | Dettaglio completo di una singola fattura: righe, piano pagamenti, stato e-invoice, allegati. |

### Pagamenti (2 tools)

| Tool | Descrizione |
|---|---|
| `get_overdue_invoices` | Tutte le fatture scadute non pagate, ordinate per giorni di ritardo. Scansiona fino a 5 anni di storico. |
| `get_payment_summary` | Dashboard pagamenti aggregata: totale fatturato, incassato, da incassare, numero e importo scaduti, con percentuali. |

### Clienti (2 tools)

| Tool | Descrizione |
|---|---|
| `get_clients` | Anagrafica clienti completa: dati fiscali, indirizzi, contatti, PEC, codice SDI, condizioni di pagamento predefinite. |
| `get_client_invoices` | Tutte le fatture per un cliente specifico con riepilogo pagamenti. |

### Spese (4 tools)

| Tool | Descrizione |
|---|---|
| `get_received_invoices` | Fatture ricevute da fornitori con paginazione intelligente (mese per mese per intervalli lunghi). |
| `get_received_invoice` | Dettaglio completo di una fattura ricevuta: righe, deducibilita', piano pagamenti. |
| `get_unpaid_received_invoices` | Fatture passive non ancora pagate — la tua dashboard debiti verso fornitori. |
| `get_expenses_by_month` | Aggregazione spese mensili per qualsiasi anno, con totali e medie. |

### Analytics (3 tools)

| Tool | Descrizione |
|---|---|
| `get_revenue_by_month` | Fatturato mensile per qualsiasi anno. |
| `get_revenue_by_client` | Fatturato per cliente (top N) con percentuali — la tua analisi di Pareto. |
| `get_yearly_stats` | Dashboard annuale completa: fatturato, clienti attivi, cliente top, medie, dettaglio trimestrale. |

### Info azienda (1 tool)

| Tool | Descrizione |
|---|---|
| `get_company_info` | Informazioni sulle aziende associate all'account. |

### Solleciti e analisi crediti (5 tools)

Qui sta il vero valore aggiunto. Questi tools implementano logica di business che non esiste nelle API FIC:

| Tool | Descrizione |
|---|---|
| `get_overdue_invoices_with_netting` | Fatture scadute con **netting FIFO automatico delle note di credito**. Raggruppa fatture e NC per cliente, applica i crediti alle fatture piu' vecchie, mostra fatture coperte totalmente o parzialmente. |
| `get_aging_report` | Analisi aging standard con 4 fasce (1-30, 31-60, 61-90, 90+ giorni). Include netting NC. Mostra il dettaglio delle posizioni critiche. |
| `get_reminder_data` | Dati strutturati per generare lettere di sollecito: anagrafica completa del cliente (nome, PEC, email, telefono, indirizzo) + tutte le fatture scadute con importi e giorni di ritardo. |
| `get_client_payment_behavior` | Analisi affidabilita' pagamenti su 3 anni: DSO (Days Sales Outstanding), % pagamenti in ritardo, trend anno su anno (migliora/peggiora/stabile) e rating da 1 a 5 stelle. |
| `get_reminder_priority_queue` | Lista prioritizzata dei clienti da sollecitare, con score: `importo * log(giorni_ritardo) * sqrt(num_fatture)`. Include livello urgenza (critico/alto/medio/basso) e contatti. |

### Netting Note di Credito — Come funziona

L'algoritmo `_apply_netting_fifo`:

1. Raggruppa note di credito e fatture per nome cliente (case-insensitive)
2. Ordina le fatture per data di emissione (piu' vecchie prima — FIFO)
3. Somma tutte le NC per cliente (usando `amount_net`)
4. Applica i crediti in sequenza:
   - Se credito >= importo fattura → fattura completamente coperta (esclusa dallo scaduto)
   - Se credito < importo fattura → riduce il saldo residuo
5. Tolleranza di 0.01 EUR per arrotondamenti floating-point

---

## Quick Start

### 1. Prerequisiti

- Python 3.11+
- Un account [Fatture in Cloud](https://www.fattureincloud.it/)
- Un'app OAuth2 registrata su [developers.fattureincloud.it](https://developers.fattureincloud.it)

### 2. Installazione

```bash
git clone https://github.com/maxmost-hestro/fattureincloud-mcp-server.git
cd fattureincloud-mcp-server

python -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 3. Configurazione

#### Opzione A: Setup interattivo (consigliato)

```bash
python auth_setup.py
```

Lo script:
- Apre il browser per l'autorizzazione OAuth2
- Scambia il codice per access/refresh token
- Rileva automaticamente il tuo company ID
- Salva tutto nel file `.env`

#### Opzione B: `.env` manuale

```bash
cp .env.example .env
# Modifica .env con le tue credenziali
```

### 4. Avvio

```bash
# Modalita' stdio (per Claude Code / Claude Desktop)
python server.py

# Streamable HTTP — richiesto da claude.ai (MCP spec 2025-03-26)
python server.py --transport streamable-http --host 0.0.0.0 --port 3002

# Legacy HTTP/SSE
python server.py --transport sse --host 0.0.0.0 --port 3002
```

### 5. Collegamento a Claude Code

Aggiungi al tuo `~/.claude.json` o alle impostazioni di Claude Code:

```json
{
  "mcpServers": {
    "fattureincloud": {
      "command": "python",
      "args": ["/path/to/fattureincloud-mcp-server/server.py"]
    }
  }
}
```

Poi chiedi a Claude cose come:
- *"Mostrami le fatture scadute"*
- *"Qual e' il fatturato 2025 per cliente?"*
- *"Chi devo sollecitare con priorita'?"*
- *"Analizza il comportamento di pagamento di ACME Srl"*
- *"Quanto abbiamo speso questo mese?"*
- *"Dammi l'aging report"*

---

## Variabili d'Ambiente

| Variabile | Descrizione | Obbligatoria |
|---|---|---|
| `FIC_ACCESS_TOKEN` | Token di accesso OAuth2 | Si |
| `FIC_COMPANY_ID` | ID azienda in Fatture in Cloud | Si |
| `FIC_COMPANY_NAME` | Nome azienda (solo visualizzazione) | No |
| `FIC_CLIENT_ID` | Client ID dell'app OAuth2 | Per `auth_setup.py` |
| `FIC_CLIENT_SECRET` | Client Secret dell'app OAuth2 | Per `auth_setup.py` |

### Scope OAuth2 richiesti

```
issued_documents:r    # Lettura fatture emesse
received_documents:r  # Lettura fatture ricevute
entities:r            # Lettura clienti/fornitori
settings:r            # Lettura impostazioni
situation:r           # Lettura situazione contabile
```

---

## Deploy con Docker

```bash
# Build
docker build -t fattureincloud-mcp .

# Run con streamable HTTP (default, per claude.ai)
docker run -d \
  --name fattureincloud-mcp \
  -p 3002:3002 \
  --env-file .env \
  fattureincloud-mcp

# Run con stdio (per Claude Code locale)
docker run -i --rm --env-file .env fattureincloud-mcp python server.py
```

---

## Workflow Solleciti

Il flusso consigliato per gestire i pagamenti scaduti:

```
1. get_overdue_invoices_with_netting
   → Lista pulita fatture scadute (note di credito gia' applicate)

2. get_aging_report
   → Situazione per fascia temporale (1-30, 31-60, 61-90, 90+ giorni)

3. get_reminder_priority_queue
   → Chi contattare per primo, ordinato per score di urgenza

4. get_reminder_data (per cliente)
   → Contatti + dettaglio fatture per la mail di sollecito

5. get_client_payment_behavior (opzionale)
   → DSO, trend e rating per calibrare il tono del sollecito
```

---

## Stack Tecnologico

| Componente | Versione | Scopo |
|---|---|---|
| Python | 3.11+ | Runtime |
| `fattureincloud-python-sdk` | 2.1.3 | Client ufficiale API FIC |
| `mcp` | latest | MCP SDK di Anthropic |
| `python-dotenv` | 1.0.1 | Configurazione da ambiente |
| `uvicorn` | 0.27+ | Server ASGI (modalita' HTTP/SSE) |
| `starlette` | 0.36+ | Web framework (modalita' HTTP/SSE) |

---

## Come Contribuire

Vedi [CONTRIBUTING.md](CONTRIBUTING.md) per le linee guida.

---

## Changelog

Vedi [CHANGELOG.md](CHANGELOG.md) per la storia delle modifiche.

---

## Licenza

Questo progetto e' distribuito sotto licenza MIT. Vedi [LICENSE](LICENSE) per i dettagli.

---

**Autore:** Massimo Mostallino — [massimo.mostallino@hestro.it](mailto:massimo.mostallino@hestro.it) — [hestro.it](https://www.hestro.it)
