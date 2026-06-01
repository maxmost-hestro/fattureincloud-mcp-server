"""
Tools di SCRITTURA per il magazzino / articoli FIC.

ATTENZIONE: questi tool scrivono sulla company FIC di PRODUZIONE (COMPANY_ID in .env).
Operazioni potenzialmente distruttive, protette da DOPPIA BARRIERA:
  1. env flag globale FIC_ALLOW_WRITE deve valere "true";
  2. ogni tool richiede confirm=true; senza confirm esegue un DRY-RUN (anteprima prima->dopo).
Le scritture avvengono una alla volta (un articolo per chiamata): nessuna API batch.

FIC non espone un endpoint di movimento di magazzino giornalizzato: carico/scarico/rettifica
si realizzano come read-modify-write del valore di giacenza. L'audit trail resta nei file di
carico/scarico di prep-bilancio e nei log del server (vedi sotto).

CAMPO GIACENZA: STOCK_FIELD = 'stock_initial', scelto per semantica FIC (stock_current e'
tipicamente derivato/non scrivibile). NON ancora verificato empiricamente: al 2026-06-01 il
token OAuth di produzione e' read-only (FIC risponde 403 NO_PERMISSION sulle modify), quindi il
test dry-run -> set -> re-read non e' stato completabile. Per abilitare la scrittura serve un
token con scope di scrittura prodotti (vedi auth_setup.py: aggiungere 'products:a' e ri-autorizzare).
Dopo l'abilitazione, eseguire il test su un articolo non critico e confermare/correggere
STOCK_FIELD in questo unico punto.
"""

import os
import logging

from mcp.types import Tool, TextContent
from fattureincloud_python_sdk.api import products_api
from fattureincloud_python_sdk.models.product import Product
from fattureincloud_python_sdk.models.modify_product_request import ModifyProductRequest
from fattureincloud_python_sdk.models.create_product_request import CreateProductRequest

from ..config import COMPANY_ID, get_api_client

logger = logging.getLogger("fattureincloud-mcp")

# Campo giacenza scrivibile onorato da FIC (vedi docstring).
STOCK_FIELD = "stock_initial"


def _write_allowed() -> bool:
    """True solo se l'env flag globale FIC_ALLOW_WRITE vale esattamente 'true'."""
    return os.getenv("FIC_ALLOW_WRITE", "false").strip().lower() == "true"


def _num(value) -> float:
    return float(value) if value is not None else 0.0


def _text(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=msg)]


def _disabled_msg() -> list[TextContent]:
    return _text(
        "SCRITTURA RIFIUTATA: scrittura disabilitata (FIC_ALLOW_WRITE non e' 'true').\n"
        "Per abilitare: avviare il server con -e FIC_ALLOW_WRITE=true (solo sui profili che "
        "devono scrivere). I profili read-only restano protetti."
    )


def _get_product(api, product_id: int) -> Product:
    """Legge un articolo (read della read-modify-write)."""
    return api.get_product(company_id=COMPANY_ID, product_id=product_id, fieldset="detailed").data


def _summary(p: Product) -> str:
    return (
        f"ID {p.id} | {p.code or 'N/A'} | {p.name or 'N/A'}\n"
        f"  categoria={p.category or 'N/A'} | misura={p.measure or 'N/A'}\n"
        f"  net_cost={_num(p.net_cost):.2f} | net_price={_num(p.net_price):.2f}\n"
        f"  stock_initial={_num(p.stock_initial):.2f} | stock_current={_num(p.stock_current):.2f} | in_stock={p.in_stock}"
    )


# ---------------------------------------------------------------------------
# product_update_stock
# ---------------------------------------------------------------------------
async def handle_product_update_stock(arguments: dict) -> list[TextContent]:
    product_id = arguments.get("product_id")
    operation = arguments.get("operation")
    quantity = arguments.get("quantity")
    note = arguments.get("note")
    confirm = arguments.get("confirm", False)

    if product_id is None or operation is None or quantity is None:
        return _text("Errore: 'product_id', 'operation' e 'quantity' sono obbligatori.")
    if operation not in ("set", "carico", "scarico"):
        return _text("Errore: 'operation' deve essere 'set', 'carico' o 'scarico'.")

    with get_api_client() as api_client:
        api = products_api.ProductsApi(api_client)
        try:
            product = _get_product(api, product_id)
            q0 = _num(getattr(product, STOCK_FIELD))

            if operation == "set":
                q1 = float(quantity)
            elif operation == "carico":
                q1 = q0 + float(quantity)
            else:  # scarico
                q1 = q0 - float(quantity)

            if q1 < 0:
                return _text(
                    f"Errore: lo scarico porterebbe la giacenza sotto zero "
                    f"({q0:.2f} - {float(quantity):.2f} = {q1:.2f}). Operazione annullata."
                )

            head = (
                f"product_update_stock [{operation}] articolo {product_id} "
                f"({product.name or 'N/A'})\n"
                f"Campo giacenza: {STOCK_FIELD}\n"
                f"Prima -> dopo: {q0:.2f} -> {q1:.2f}"
                + (f"\nNota: {note}" if note else "")
            )

            if not confirm:
                return _text("DRY-RUN (nessuna scrittura)\n" + head + "\n\n" + _summary(product))

            if not _write_allowed():
                return _disabled_msg()

            setattr(product, STOCK_FIELD, q1)
            api.modify_product(
                company_id=COMPANY_ID,
                product_id=product_id,
                modify_product_request=ModifyProductRequest(data=product),
            )

            updated = _get_product(api, product_id)
            q_final = _num(getattr(updated, STOCK_FIELD))
            logger.info(
                "FIC WRITE product_update_stock id=%s field=%s op=%s %.2f->%.2f (finale=%.2f) note=%s",
                product_id, STOCK_FIELD, operation, q0, q1, q_final, note or "",
            )
            return _text(
                "SCRITTURA ESEGUITA\n" + head
                + f"\nValore riletto da FIC ({STOCK_FIELD}): {q_final:.2f}\n\n"
                + _summary(updated)
            )

        except Exception as e:
            return _text(f"Errore FIC: {str(e)}")


# ---------------------------------------------------------------------------
# product_update_category
# ---------------------------------------------------------------------------
async def handle_product_update_category(arguments: dict) -> list[TextContent]:
    product_id = arguments.get("product_id")
    category = arguments.get("category")
    confirm = arguments.get("confirm", False)

    if product_id is None or category is None:
        return _text("Errore: 'product_id' e 'category' sono obbligatori.")

    with get_api_client() as api_client:
        api = products_api.ProductsApi(api_client)
        try:
            product = _get_product(api, product_id)
            cat0 = product.category or "(nessuna)"
            head = (
                f"product_update_category articolo {product_id} ({product.name or 'N/A'})\n"
                f"Categoria prima -> dopo: {cat0} -> {category}"
            )

            if not confirm:
                return _text("DRY-RUN (nessuna scrittura)\n" + head + "\n\n" + _summary(product))

            if not _write_allowed():
                return _disabled_msg()

            product.category = category
            api.modify_product(
                company_id=COMPANY_ID,
                product_id=product_id,
                modify_product_request=ModifyProductRequest(data=product),
            )
            updated = _get_product(api, product_id)
            logger.info(
                "FIC WRITE product_update_category id=%s category '%s'->'%s'",
                product_id, cat0, category,
            )
            return _text("SCRITTURA ESEGUITA\n" + head + "\n\n" + _summary(updated))

        except Exception as e:
            return _text(f"Errore FIC: {str(e)}")


# ---------------------------------------------------------------------------
# product_update_fields
# ---------------------------------------------------------------------------
_EDITABLE_FIELDS = ["net_cost", "net_price", "name", "code", "measure", "notes"]


async def handle_product_update_fields(arguments: dict) -> list[TextContent]:
    product_id = arguments.get("product_id")
    confirm = arguments.get("confirm", False)

    if product_id is None:
        return _text("Errore: 'product_id' e' obbligatorio.")

    changes = {f: arguments[f] for f in _EDITABLE_FIELDS if f in arguments and arguments[f] is not None}
    if not changes:
        return _text(
            "Errore: indicare almeno uno tra " + ", ".join(_EDITABLE_FIELDS) + " da modificare."
        )

    with get_api_client() as api_client:
        api = products_api.ProductsApi(api_client)
        try:
            product = _get_product(api, product_id)
            lines = []
            for f, new_val in changes.items():
                old_val = getattr(product, f)
                lines.append(f"  {f}: {old_val} -> {new_val}")
            head = (
                f"product_update_fields articolo {product_id} ({product.name or 'N/A'})\n"
                + "\n".join(lines)
            )

            if not confirm:
                return _text("DRY-RUN (nessuna scrittura)\n" + head + "\n\n" + _summary(product))

            if not _write_allowed():
                return _disabled_msg()

            for f, new_val in changes.items():
                setattr(product, f, new_val)
            api.modify_product(
                company_id=COMPANY_ID,
                product_id=product_id,
                modify_product_request=ModifyProductRequest(data=product),
            )
            updated = _get_product(api, product_id)
            logger.info(
                "FIC WRITE product_update_fields id=%s changes=%s",
                product_id, {f: changes[f] for f in changes},
            )
            return _text("SCRITTURA ESEGUITA\n" + head + "\n\n" + _summary(updated))

        except Exception as e:
            return _text(f"Errore FIC: {str(e)}")


# ---------------------------------------------------------------------------
# product_create
# ---------------------------------------------------------------------------
async def handle_product_create(arguments: dict) -> list[TextContent]:
    name = arguments.get("name")
    confirm = arguments.get("confirm", False)

    if not name:
        return _text("Errore: 'name' e' obbligatorio.")

    fields = {
        "name": name,
        "code": arguments.get("code"),
        "category": arguments.get("category"),
        "net_cost": arguments.get("net_cost"),
        "net_price": arguments.get("net_price"),
        "measure": arguments.get("measure"),
        STOCK_FIELD: arguments.get("stock_initial"),
    }
    fields = {k: v for k, v in fields.items() if v is not None}

    head = "product_create nuovo articolo:\n" + "\n".join(f"  {k}={v}" for k, v in fields.items())

    if not confirm:
        return _text("DRY-RUN (nessuna scrittura)\n" + head)

    if not _write_allowed():
        return _disabled_msg()

    with get_api_client() as api_client:
        api = products_api.ProductsApi(api_client)
        try:
            new_product = Product(**fields)
            response = api.create_product(
                company_id=COMPANY_ID,
                create_product_request=CreateProductRequest(data=new_product),
            )
            created = response.data
            logger.info("FIC WRITE product_create id=%s name='%s'", created.id, name)
            return _text("SCRITTURA ESEGUITA (articolo creato)\n\n" + _summary(created))

        except Exception as e:
            return _text(f"Errore FIC: {str(e)}")


# ---------------------------------------------------------------------------
# product_delete
# ---------------------------------------------------------------------------
async def handle_product_delete(arguments: dict) -> list[TextContent]:
    product_id = arguments.get("product_id")
    confirm = arguments.get("confirm", False)

    if product_id is None:
        return _text("Errore: 'product_id' e' obbligatorio.")

    with get_api_client() as api_client:
        api = products_api.ProductsApi(api_client)
        try:
            product = _get_product(api, product_id)
            head = f"product_delete articolo {product_id}:\n" + _summary(product)

            if not confirm:
                return _text(
                    "DRY-RUN (nessuna cancellazione)\n" + head
                    + "\n\nNOTA: FIC puo' rifiutare se l'articolo e' usato in documenti."
                )

            if not _write_allowed():
                return _disabled_msg()

            api.delete_product(company_id=COMPANY_ID, product_id=product_id)
            logger.info("FIC WRITE product_delete id=%s name='%s'", product_id, product.name or "")
            return _text("CANCELLAZIONE ESEGUITA\n" + head)

        except Exception as e:
            # Tipicamente FIC rifiuta se l'articolo e' referenziato in documenti.
            return _text(
                f"Errore FIC (cancellazione non eseguita): {str(e)}\n"
                "Probabile causa: l'articolo e' usato in uno o piu' documenti."
            )


def get_product_write_tools():
    """Tool di scrittura magazzino (protetti da FIC_ALLOW_WRITE + confirm)."""
    return [
        Tool(
            name="product_update_stock",
            description="SCRITTURA: carico/scarico/rettifica giacenza di un articolo FIC "
                        "(read-modify-write; nessun movimento giornalizzato lato API). Richiede "
                        "FIC_ALLOW_WRITE=true e confirm=true; senza confirm esegue un dry-run con "
                        "anteprima prima->dopo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "ID articolo FIC"},
                    "operation": {"type": "string", "enum": ["set", "carico", "scarico"]},
                    "quantity": {"type": "number", "description": "Quantita' (assoluta per 'set', delta per carico/scarico)"},
                    "note": {"type": "string", "description": "Nota libera per il log"},
                    "confirm": {"type": "boolean", "description": "true = esegue; assente/false = dry-run"}
                },
                "required": ["product_id", "operation", "quantity"]
            }
        ),
        Tool(
            name="product_update_category",
            description="SCRITTURA: cambia la categoria di un articolo FIC. Richiede "
                        "FIC_ALLOW_WRITE=true e confirm=true; senza confirm esegue un dry-run.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "category": {"type": "string"},
                    "confirm": {"type": "boolean"}
                },
                "required": ["product_id", "category"]
            }
        ),
        Tool(
            name="product_update_fields",
            description="SCRITTURA: modifica costo/prezzo/anagrafica (net_cost, net_price, name, "
                        "code, measure, notes) di un articolo FIC via read-modify-write. Richiede "
                        "FIC_ALLOW_WRITE=true e confirm=true; senza confirm esegue un dry-run.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "net_cost": {"type": "number"},
                    "net_price": {"type": "number"},
                    "name": {"type": "string"},
                    "code": {"type": "string"},
                    "measure": {"type": "string"},
                    "notes": {"type": "string"},
                    "confirm": {"type": "boolean"}
                },
                "required": ["product_id"]
            }
        ),
        Tool(
            name="product_create",
            description="SCRITTURA: crea un nuovo articolo FIC (es. carico di voce nuova). Richiede "
                        "FIC_ALLOW_WRITE=true e confirm=true; senza confirm esegue un dry-run.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "code": {"type": "string"},
                    "category": {"type": "string"},
                    "net_cost": {"type": "number"},
                    "net_price": {"type": "number"},
                    "measure": {"type": "string"},
                    "stock_initial": {"type": "number"},
                    "confirm": {"type": "boolean"}
                },
                "required": ["name"]
            }
        ),
        Tool(
            name="product_delete",
            description="SCRITTURA: cancella l'anagrafica di un articolo FIC. Richiede "
                        "FIC_ALLOW_WRITE=true e confirm=true; senza confirm esegue un dry-run. "
                        "FIC rifiuta se l'articolo e' usato in documenti.",
            inputSchema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer"},
                    "confirm": {"type": "boolean"}
                },
                "required": ["product_id"]
            }
        ),
    ]


def get_product_write_handlers():
    """Handler di scrittura magazzino."""
    return {
        "product_update_stock": handle_product_update_stock,
        "product_update_category": handle_product_update_category,
        "product_update_fields": handle_product_update_fields,
        "product_create": handle_product_create,
        "product_delete": handle_product_delete,
    }
