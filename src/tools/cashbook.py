"""
Tools per prima nota (cashbook), conti di pagamento e F24.

Read-only. Servono per quadrare i flussi di cassa reali (banca, carte) con le
fatture attive/passive e con i costi del personale, che non transitano da fatture.

Scope OAuth richiesti: `cashbook:r` (prima nota) e `taxes:r` (F24). Con un token
senza questi scope Fatture in Cloud risponde 403 NO_PERMISSION: rieseguire
`auth_setup.py` dopo averli aggiunti a SCOPES.
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from collections import defaultdict
from datetime import datetime, timedelta
from mcp.types import Tool, TextContent
from fattureincloud_python_sdk.api import cashbook_api, info_api

from ..config import COMPANY_ID, ACCESS_TOKEN, get_api_client

API_BASE = "https://api-v2.fattureincloud.it"


def _fmt(x) -> str:
    return f"{float(x or 0):.2f}"


def _rest_get(path: str, **params) -> tuple[int, dict]:
    """GET grezzo sull'API v2 (usato dove l'SDK non deserializza correttamente)."""
    url = f"{API_BASE}/c/{COMPANY_ID}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            body = {}
        return e.code, body


async def handle_get_payment_accounts(arguments: dict) -> list[TextContent]:
    """Conti di pagamento (banche, carte, cassa) configurati in Fatture in Cloud."""
    with get_api_client() as api_client:
        api = info_api.InfoApi(api_client)
        try:
            response = api.list_payment_accounts(company_id=COMPANY_ID, fieldset="detailed")
            accounts = response.data or []
            output = f"Trovati {len(accounts)} conti di pagamento:\n\n"
            for a in accounts:
                kind = a.type.value if getattr(a, "type", None) else "-"
                iban = getattr(a, "iban", None) or ""
                output += f"- ID {a.id} | {a.name} | tipo: {kind}"
                if iban:
                    output += f" | IBAN: {iban}"
                if getattr(a, "virtual", None):
                    output += " | virtuale"
                output += "\n"
            return [TextContent(type="text", text=output)]
        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


async def handle_get_cashbook_entries(arguments: dict) -> list[TextContent]:
    """Movimenti di prima nota per periodo, con riepilogo per tipo e per conto."""
    from_date = arguments.get("from_date")
    to_date = arguments.get("to_date")
    entry_type = arguments.get("type")  # in | out | all
    payment_account_id = arguments.get("payment_account_id")
    limit = arguments.get("limit", 200)

    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")
    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    with get_api_client() as api_client:
        api = cashbook_api.CashbookApi(api_client)
        try:
            kwargs = {"company_id": COMPANY_ID, "date_from": from_date, "date_to": to_date}
            if entry_type and entry_type != "all":
                kwargs["type"] = entry_type
            if payment_account_id:
                kwargs["payment_account_id"] = int(payment_account_id)
            response = api.list_cashbook_entries(**kwargs)
            entries = response.data or []
        except Exception as e:
            msg = str(e)
            if "NO_PERMISSION" in msg or "403" in msg:
                return [TextContent(type="text", text=(
                    "Errore 403 NO_PERMISSION: il token OAuth non ha lo scope `cashbook:r`.\n"
                    "Aggiungere `cashbook:r` a SCOPES in auth_setup.py, rieseguire lo script e aggiornare FIC_ACCESS_TOKEN."))]
            return [TextContent(type="text", text=f"Errore: {msg}")]

    # Riepilogo per kind/type e per conto
    by_kind = defaultdict(lambda: {"n": 0, "in": 0.0, "out": 0.0})
    by_account = defaultdict(lambda: {"in": 0.0, "out": 0.0})
    tot_in = tot_out = 0.0
    for e in entries:
        kind = e.kind.value if getattr(e, "kind", None) else "?"
        a_in = float(e.amount_in or 0)
        a_out = float(e.amount_out or 0)
        by_kind[kind]["n"] += 1
        by_kind[kind]["in"] += a_in
        by_kind[kind]["out"] += a_out
        tot_in += a_in
        tot_out += a_out
        if a_in and getattr(e, "payment_account_in", None):
            by_account[e.payment_account_in.name]["in"] += a_in
        if a_out and getattr(e, "payment_account_out", None):
            by_account[e.payment_account_out.name]["out"] += a_out

    output = f"PRIMA NOTA {from_date} -> {to_date}\n{'=' * 60}\n"
    output += f"Movimenti: {len(entries)}\n"
    output += f"Entrate totali: {_fmt(tot_in)} EUR\nUscite totali: {_fmt(tot_out)} EUR\nSaldo periodo: {_fmt(tot_in - tot_out)} EUR\n\n"
    output += "PER TIPO DI MOVIMENTO (kind):\n"
    for k, v in sorted(by_kind.items(), key=lambda x: -(x[1]['in'] + x[1]['out'])):
        output += f"  {k:20} n={v['n']:4}  entrate={_fmt(v['in']):>12}  uscite={_fmt(v['out']):>12}\n"
    output += "\nPER CONTO:\n"
    for k, v in sorted(by_account.items(), key=lambda x: -(x[1]['in'] + x[1]['out'])):
        output += f"  {k:40} entrate={_fmt(v['in']):>12}  uscite={_fmt(v['out']):>12}\n"

    output += f"\nDETTAGLIO (max {limit}):\n"
    shown = sorted(entries, key=lambda e: (str(e.var_date or ""), e.id or 0))[:limit]
    for e in shown:
        kind = e.kind.value if getattr(e, "kind", None) else "?"
        acc = ""
        if getattr(e, "payment_account_out", None) and e.amount_out:
            acc = e.payment_account_out.name
        elif getattr(e, "payment_account_in", None) and e.amount_in:
            acc = e.payment_account_in.name
        doc = ""
        if getattr(e, "document", None) and getattr(e.document, "id", None):
            doc = f" [doc {e.document.id}]"
        output += (f"- {e.var_date} | {kind:17} | {(e.entity_name or '-')[:35]:35} | "
                   f"in {_fmt(e.amount_in):>10} | out {_fmt(e.amount_out):>10} | {acc}{doc}\n")
        if e.description:
            output += f"    {e.description[:100]}\n"
    if len(entries) > limit:
        output += f"... altri {len(entries) - limit} movimenti non mostrati (alza `limit` o restringi il periodo)\n"
    return [TextContent(type="text", text=output)]


async def handle_get_f24_list(arguments: dict) -> list[TextContent]:
    """Elenco F24 registrati (contributi, ritenute, imposte) via REST grezzo.

    Usa la REST diretta perche' il modello SDK `ListF24ResponseAggregatedData`
    non deserializza la risposta reale (errore di validazione pydantic).
    """
    from_date = arguments.get("from_date")
    to_date = arguments.get("to_date")
    limit = arguments.get("limit", 100)

    status, body = _rest_get("taxes", per_page=min(int(limit), 100), sort="-due_date")
    if status == 403:
        return [TextContent(type="text", text=(
            "Errore 403 NO_PERMISSION: il token OAuth non ha lo scope `taxes:r`.\n"
            "Aggiungere `taxes:r` a SCOPES in auth_setup.py, rieseguire lo script e aggiornare FIC_ACCESS_TOKEN."))]
    if status != 200:
        return [TextContent(type="text", text=f"Errore HTTP {status}: {body.get('error', body)}")]

    rows = body.get("data", []) or []
    if from_date:
        rows = [r for r in rows if (r.get("due_date") or "") >= from_date]
    if to_date:
        rows = [r for r in rows if (r.get("due_date") or "") <= to_date]

    total = sum(float(r.get("amount") or 0) for r in rows)
    output = f"F24 REGISTRATI ({len(rows)})"
    if from_date or to_date:
        output += f" - scadenza {from_date or '...'} -> {to_date or '...'}"
    output += f"\n{'=' * 60}\nTotale: {_fmt(total)} EUR\n"
    agg = body.get("aggregated_data") or {}
    if agg.get("amount"):
        output += f"(totale complessivo in archivio, senza filtri: {agg.get('amount')} EUR)\n"
    output += "\n"
    by_month = defaultdict(float)
    for r in rows:
        by_month[(r.get("due_date") or "")[:7]] += float(r.get("amount") or 0)
    output += "PER MESE DI SCADENZA:\n"
    for k, v in sorted(by_month.items(), reverse=True):
        output += f"  {k}: {_fmt(v)} EUR\n"
    output += "\nDETTAGLIO:\n"
    for r in rows:
        pa = (r.get("payment_account") or {}).get("name", "")
        output += (f"- {r.get('due_date')} | {r.get('status', '-'):8} | {_fmt(r.get('amount')):>12} EUR | "
                   f"{(r.get('description') or '')[:70]} | {pa}\n")
    output += ("\nNota: la data e' quella di registrazione; la data di versamento reale e' nella causale (DATA INCASSO). "
               "Un F24 puo' contenere anche imposte non di personale (IVA, ritenute professionisti): per la quadratura "
               "mensile del personale confrontare con i prospetti Centro Paghe.\n")
    return [TextContent(type="text", text=output)]


def get_cashbook_tools():
    """Restituisce la lista di tool per prima nota, conti e F24."""
    return [
        Tool(
            name="get_payment_accounts",
            description="Conti di pagamento configurati (conti correnti, carte, cassa) con ID e IBAN. Read-only.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_cashbook_entries",
            description=(
                "Prima nota (cashbook): movimenti di entrata/uscita per periodo con riepilogo per tipo "
                "(fattura emessa/ricevuta, F24, ricevuta, movimento manuale) e per conto. Serve per quadrare "
                "i flussi di cassa reali con fatture e costi del personale. Read-only. Richiede scope cashbook:r."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "description": "Data inizio (YYYY-MM-DD), default: ultimi 30 giorni"},
                    "to_date": {"type": "string", "description": "Data fine (YYYY-MM-DD), default: oggi"},
                    "type": {"type": "string", "enum": ["in", "out", "all"], "description": "Filtra entrate, uscite o tutto (default: all)"},
                    "payment_account_id": {"type": "integer", "description": "Filtra per conto (ID da get_payment_accounts)"},
                    "limit": {"type": "integer", "description": "Numero massimo movimenti nel dettaglio, default: 200"},
                },
            },
        ),
        Tool(
            name="get_f24_list",
            description=(
                "Elenco F24 registrati (contributi INPS, ritenute IRPEF, imposte) con importo, scadenza, stato e conto. "
                "Read-only. Richiede scope taxes:r."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "description": "Scadenza minima (YYYY-MM-DD)"},
                    "to_date": {"type": "string", "description": "Scadenza massima (YYYY-MM-DD)"},
                    "limit": {"type": "integer", "description": "Numero massimo risultati (max 100), default: 100"},
                },
            },
        ),
    ]


def get_cashbook_handlers():
    """Restituisce il dizionario di handler per prima nota, conti e F24."""
    return {
        "get_payment_accounts": handle_get_payment_accounts,
        "get_cashbook_entries": handle_get_cashbook_entries,
        "get_f24_list": handle_get_f24_list,
    }
