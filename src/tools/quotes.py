"""
Tool read-only per i PREVENTIVI (issued_documents di tipo 'quote').

Gemello di expenses.get_received_credit_notes: stessa paginazione, filtro per
cliente e formato output, ma sui documenti emessi di tipo 'quote'. Esiste perche'
get_invoices recupera i preventivi mescolati a tutti gli altri tipi di documento
e li etichetta genericamente come "fatture", senza i campi tipici del preventivo
(validita', stato "visto", oggetto). Questo tool li espone in modo pulito e
distinguibile. Nessuna scrittura su FIC.
"""

from datetime import datetime, timedelta
from mcp.types import Tool, TextContent
from fattureincloud_python_sdk.api import issued_documents_api

from ..config import COMPANY_ID, get_api_client


def _fmt_date(value) -> str:
    if not value:
        return "N/A"
    try:
        return value.strftime("%Y-%m-%d")
    except AttributeError:
        return str(value)


async def handle_get_quotes(arguments: dict) -> list[TextContent]:
    """Elenco preventivi emessi (issued_documents type='quote')."""
    from_date = arguments.get("from_date")
    to_date = arguments.get("to_date")
    client_name = arguments.get("client_name")
    limit = arguments.get("limit", 50)

    with get_api_client() as api_client:
        api = issued_documents_api.IssuedDocumentsApi(api_client)

        try:
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")
            if not from_date:
                from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

            q = f"date >= '{from_date}' and date <= '{to_date}'"

            # Loop di paginazione completo (nessun troncamento sui grandi volumi)
            all_quotes = []
            page = 1
            while True:
                response = api.list_issued_documents(
                    company_id=COMPANY_ID,
                    type="quote",
                    q=q,
                    page=page,
                    per_page=100,
                    fieldset="detailed",
                )

                if response.data:
                    all_quotes.extend(response.data)

                if not response.last_page or page >= response.last_page:
                    break
                page += 1

            # Filtro cliente in Python (case-insensitive, partial match)
            if client_name:
                needle = client_name.lower()
                all_quotes = [
                    d for d in all_quotes
                    if d.entity and needle in (d.entity.name or "").lower()
                ]

            # Ordina per data decrescente (piu' recenti prima)
            all_quotes.sort(key=lambda d: (d.var_date or datetime.min.date()), reverse=True)

            quotes = all_quotes[:limit]

            if not quotes:
                return [TextContent(type="text", text="Nessun preventivo trovato con i filtri specificati.")]

            total_net = sum(d.amount_net or 0 for d in quotes)
            total_gross = sum(d.amount_gross or 0 for d in quotes)

            output = f"Trovati {len(quotes)} preventivi:\n"
            output += f"  Imponibile totale: {total_net:.2f} EUR\n"
            output += f"  Totale (ivato): {total_gross:.2f} EUR\n\n"

            for d in quotes:
                num = f"{d.number or 'N/A'}{d.numeration or ''}"
                output += f"- Preventivo n.{num} del {_fmt_date(d.var_date)}\n"
                if d.entity:
                    output += f"  Cliente: {d.entity.name or 'N/A'}\n"
                    if d.entity.vat_number:
                        output += f"  P.IVA: {d.entity.vat_number}\n"
                oggetto = d.visible_subject or d.subject
                if oggetto:
                    output += f"  Oggetto: {oggetto}\n"
                output += f"  Imponibile: {(d.amount_net or 0):.2f} EUR | Totale: {(d.amount_gross or 0):.2f} EUR\n"
                output += f"  Validita' (scadenza): {_fmt_date(d.next_due_date)}\n"
                output += f"  Visto dal cliente: {_fmt_date(d.seen_date)}\n"
                if d.url:
                    output += f"  Link: {d.url}\n"
                output += "\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


def get_quote_tools():
    """Tool read-only per i preventivi."""
    return [
        Tool(
            name="get_quotes",
            description="Elenco PREVENTIVI emessi (read-only). Per ogni preventivo: numero, data, "
                        "cliente, oggetto, validita' (next_due_date), data 'visto dal cliente' e "
                        "importi (imponibile/totale). Filtri: from_date, to_date, client_name, limit. "
                        "Tool dedicato perche' get_invoices mescola i preventivi con gli altri documenti.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "description": "Data inizio (YYYY-MM-DD), default 365gg fa"},
                    "to_date": {"type": "string", "description": "Data fine (YYYY-MM-DD), default oggi"},
                    "client_name": {"type": "string", "description": "Filtra per nome cliente (parziale)"},
                    "limit": {"type": "integer", "description": "Numero massimo preventivi, default 50"}
                }
            }
        ),
    ]


def get_quote_handlers():
    """Handler read-only per i preventivi."""
    return {
        "get_quotes": handle_get_quotes,
    }
