"""
Tools per catalogo articoli / magazzino (read-only).

Gemello concettuale di expenses.get_received_credit_notes: usa SOLO la lettura
(list_products / list_product_categories), niente create/modify/delete.
Pensato per la valorizzazione delle rimanenze di magazzino al 31/12 da parte
del progetto prep-bilancio.
"""

from collections import defaultdict
from mcp.types import Tool, TextContent
from fattureincloud_python_sdk.api import products_api, info_api

from ..config import COMPANY_ID, get_api_client


def _num(value) -> float:
    """Converte un valore eventualmente None in float (0.0 se mancante)."""
    return float(value) if value is not None else 0.0


def _category_label(cat) -> str:
    """Estrae l'etichetta categoria sia da stringa che da oggetto SDK."""
    if cat is None:
        return ""
    if isinstance(cat, str):
        return cat
    return getattr(cat, "name", str(cat)) or ""


def _fetch_all_products(api) -> list:
    """Scarica TUTTI gli articoli con paginazione completa (no troncamento)."""
    all_products = []
    page = 1
    while True:
        response = api.list_products(
            company_id=COMPANY_ID,
            page=page,
            per_page=100,
            fieldset="detailed",
        )

        if response.data:
            all_products.extend(response.data)

        if not response.last_page or page >= response.last_page:
            break

        page += 1

    return all_products


async def handle_get_products(arguments: dict) -> list[TextContent]:
    """Catalogo articoli / magazzino FattureInCloud (read-only).

    Per ogni articolo riporta categoria, unita' di misura, costi (net_cost/
    average_cost), giacenze (stock_initial/stock_current) e prezzo. In testa un
    riepilogo per categoria con valore giacenza = sum(stock_current * net_cost).
    """
    category = arguments.get("category")
    search = arguments.get("search")
    in_stock_only = arguments.get("in_stock_only", False)
    limit = arguments.get("limit", 1000)

    with get_api_client() as api_client:
        api = products_api.ProductsApi(api_client)

        try:
            products = _fetch_all_products(api)

            # Filtro categoria (parziale, case-insensitive) in Python:
            # robusto rispetto alla q-syntax FIC e a categorie con apici/spazi.
            if category:
                needle = category.lower()
                products = [
                    p for p in products
                    if needle in _category_label(p.category).lower()
                ]

            # Filtro testuale su code/name/description
            if search:
                needle = search.lower()
                products = [
                    p for p in products
                    if needle in (p.code or "").lower()
                    or needle in (p.name or "").lower()
                    or needle in (p.description or "").lower()
                ]

            # Solo articoli con giacenza
            if in_stock_only:
                products = [
                    p for p in products
                    if (p.stock_current is not None and _num(p.stock_current) > 0)
                    or p.in_stock is True
                ]

            # Ordina per categoria, poi nome
            products.sort(key=lambda p: (
                _category_label(p.category).lower(),
                (p.name or "").lower(),
            ))

            products = products[:limit]

            if not products:
                return [TextContent(type="text", text="Nessun articolo trovato.")]

            # Riepilogo per categoria (n. articoli + valore giacenza)
            cat_count: dict = defaultdict(int)
            cat_value: dict = defaultdict(float)
            for p in products:
                label = _category_label(p.category) or "(senza categoria)"
                cat_count[label] += 1
                cat_value[label] += _num(p.stock_current) * _num(p.net_cost)

            total_value = sum(cat_value.values())

            output = f"Catalogo articoli / magazzino: {len(products)} articoli\n"
            output += f"Valore giacenza totale (stock_current x net_cost): {total_value:.2f} EUR\n\n"
            output += "RIEPILOGO PER CATEGORIA\n"
            output += "=" * 40 + "\n"
            for label in sorted(cat_count.keys(), key=str.lower):
                output += (
                    f"- {label}: {cat_count[label]} articoli | "
                    f"valore giacenza {cat_value[label]:.2f} EUR\n"
                )
            output += "\n"

            # Righe articolo
            output += "ARTICOLI\n"
            output += "=" * 40 + "\n"
            for p in products:
                label = _category_label(p.category) or "(senza categoria)"
                output += f"- ID {p.id or 'N/A'} | {p.code or 'N/A'} | {p.name or 'N/A'}\n"
                output += f"  Categoria: {label}\n"
                output += f"  Unita' di misura: {p.measure or 'N/A'}\n"
                output += (
                    f"  Costo: net_cost {_num(p.net_cost):.2f} EUR | "
                    f"average_cost {_num(p.average_cost):.2f} EUR\n"
                )
                output += (
                    f"  Giacenza: stock_initial {_num(p.stock_initial):.2f} | "
                    f"stock_current {_num(p.stock_current):.2f} | "
                    f"in_stock {p.in_stock}\n"
                )
                output += f"  Prezzo: net_price {_num(p.net_price):.2f} EUR\n"
                if p.notes:
                    output += f"  Note: {p.notes}\n"
                output += "\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


async def handle_get_product_categories(arguments: dict) -> list[TextContent]:
    """Elenco delle categorie magazzino presenti in FattureInCloud.

    Usa l'endpoint dedicato list_product_categories per la tassonomia ufficiale
    e arricchisce con conteggio articoli e valore giacenza per categoria,
    derivati da list_products.
    """
    with get_api_client() as api_client:
        try:
            # Tassonomia ufficiale dalle liste FIC
            info = info_api.InfoApi(api_client)
            # context="products": valore richiesto da FIC per la tassonomia
            # delle categorie articoli di magazzino (verificato contro l'API).
            cat_response = info.list_product_categories(
                company_id=COMPANY_ID, context="products"
            )
            official = [
                _category_label(c)
                for c in (cat_response.data or [])
                if _category_label(c)
            ]

            # Aggregati per categoria dagli articoli reali
            api = products_api.ProductsApi(api_client)
            products = _fetch_all_products(api)

            cat_count: dict = defaultdict(int)
            cat_value: dict = defaultdict(float)
            for p in products:
                label = _category_label(p.category) or "(senza categoria)"
                cat_count[label] += 1
                cat_value[label] += _num(p.stock_current) * _num(p.net_cost)

            # Unione: categorie ufficiali + eventuali categorie presenti solo sugli articoli
            all_labels = sorted(
                set(official) | set(cat_count.keys()),
                key=str.lower,
            )

            if not all_labels:
                return [TextContent(type="text", text="Nessuna categoria magazzino trovata.")]

            output = f"Categorie magazzino: {len(all_labels)}\n"
            output += "=" * 40 + "\n"
            for label in all_labels:
                count = cat_count.get(label, 0)
                value = cat_value.get(label, 0.0)
                in_official = " (ufficiale)" if label in official else " (solo articoli)"
                output += (
                    f"- {label}{in_official}: {count} articoli | "
                    f"valore giacenza {value:.2f} EUR\n"
                )

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


def get_product_tools():
    """Restituisce la lista di tool per catalogo articoli / magazzino."""
    return [
        Tool(
            name="get_products",
            description="Catalogo articoli / magazzino FattureInCloud (read-only). Per ogni articolo: "
                        "categoria, unita' di misura, costo unitario (net_cost/average_cost), giacenza "
                        "(stock_initial/stock_current), prezzo. Usato da prep-bilancio per la "
                        "valorizzazione delle rimanenze di magazzino al 31/12.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filtra per categoria (parziale)"},
                    "search": {"type": "string", "description": "Cerca in codice/nome/descrizione"},
                    "in_stock_only": {"type": "boolean", "description": "Solo articoli con giacenza > 0"},
                    "limit": {"type": "integer", "description": "Numero massimo articoli, default 1000"}
                }
            }
        ),
        Tool(
            name="get_product_categories",
            description="Elenco delle categorie magazzino presenti in FattureInCloud, con conteggio "
                        "articoli (tassonomia di riferimento per la classificazione delle rimanenze).",
            inputSchema={"type": "object", "properties": {}}
        ),
    ]


def get_product_handlers():
    """Restituisce il dizionario di handler per catalogo articoli / magazzino."""
    return {
        "get_products": handle_get_products,
        "get_product_categories": handle_get_product_categories,
    }
