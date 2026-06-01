"""
Tools per gestione spese e fatture ricevute.
"""

from datetime import datetime, timedelta
from collections import defaultdict
from mcp.types import Tool, TextContent
from fattureincloud_python_sdk.api import received_documents_api

from ..config import COMPANY_ID, get_api_client


async def handle_get_received_invoices(arguments: dict) -> list[TextContent]:
    """Fatture ricevute da fornitori."""
    from_date = arguments.get("from_date")
    to_date = arguments.get("to_date")
    supplier_name = arguments.get("supplier_name")
    limit = arguments.get("limit", 50)

    with get_api_client() as api_client:
        api = received_documents_api.ReceivedDocumentsApi(api_client)

        try:
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")
            if not from_date:
                from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

            # Se c'è un filtro fornitore e il periodo è > 120 giorni,
            # faccio query mese per mese per recuperare tutte le fatture
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
            to_dt = datetime.strptime(to_date, "%Y-%m-%d")
            days_diff = (to_dt - from_dt).days

            all_expenses = []

            if supplier_name and days_diff > 120:
                # Query mese per mese CON PAGINAZIONE
                current_date = from_dt
                while current_date <= to_dt:
                    # Primo e ultimo giorno del mese
                    first_day = current_date.replace(day=1)
                    # Ultimo giorno del mese
                    if current_date.month == 12:
                        last_day = current_date.replace(day=31)
                    else:
                        next_month = current_date.replace(month=current_date.month + 1, day=1)
                        last_day = next_month - timedelta(days=1)

                    # Non superare to_date
                    if last_day > to_dt:
                        last_day = to_dt

                    q = f"date >= '{first_day.strftime('%Y-%m-%d')}' and date <= '{last_day.strftime('%Y-%m-%d')}'"

                    # Loop paginazione per questo mese
                    page = 1
                    while True:
                        response = api.list_received_documents(
                            company_id=COMPANY_ID,
                            type="expense",
                            q=q,
                            page=page,
                            per_page=100,
                            fieldset="detailed"
                        )

                        if response.data:
                            all_expenses.extend(response.data)

                        # Verifica se ci sono altre pagine
                        if page >= response.last_page:
                            break

                        page += 1

                    # Prossimo mese
                    if current_date.month == 12:
                        current_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
                    else:
                        current_date = current_date.replace(month=current_date.month + 1, day=1)
            else:
                # Query singola CON PAGINAZIONE
                q = f"date >= '{from_date}' and date <= '{to_date}'"

                # Loop paginazione
                page = 1
                while True:
                    response = api.list_received_documents(
                        company_id=COMPANY_ID,
                        type="expense",
                        q=q,
                        page=page,
                        per_page=100,
                        fieldset="detailed"
                    )

                    if response.data:
                        all_expenses.extend(response.data)

                    # Verifica se ci sono altre pagine
                    if page >= response.last_page:
                        break

                    page += 1

            # Filtro per fornitore in Python (case-insensitive, partial match)
            if supplier_name:
                expenses = [
                    exp for exp in all_expenses
                    if exp.entity and supplier_name.lower() in exp.entity.name.lower()
                ]
                # Limito ai primi N risultati
                expenses = expenses[:limit]
            else:
                expenses = all_expenses[:limit]

            if not expenses:
                output = "Nessuna fattura ricevuta trovata."
            else:
                total_net = sum(exp.amount_net or 0 for exp in expenses)
                total_vat = sum(exp.amount_vat or 0 for exp in expenses)
                total_gross = sum(exp.amount_gross or 0 for exp in expenses)
                output = f"Trovate {len(expenses)} fatture ricevute:\n"
                output += f"  Imponibile totale: {total_net:.2f} EUR\n"
                output += f"  IVA totale: {total_vat:.2f} EUR\n"
                output += f"  Totale: {total_gross:.2f} EUR\n\n"

                for exp in expenses:
                    doc_id = exp.id or 'N/A'
                    doc_date = exp.var_date.strftime("%Y-%m-%d") if exp.var_date else 'N/A'
                    output += f"- ID {doc_id} del {doc_date}\n"

                    # Fornitore con dettagli
                    if exp.entity:
                        output += f"  Fornitore: {exp.entity.name}\n"
                        if exp.entity.vat_number:
                            output += f"  P.IVA: {exp.entity.vat_number}\n"
                        if exp.entity.tax_code and exp.entity.tax_code != exp.entity.vat_number:
                            output += f"  C.F.: {exp.entity.tax_code}\n"
                    else:
                        output += f"  Fornitore: N/A\n"

                    # Numero fattura fornitore
                    if exp.invoice_number:
                        output += f"  N. Fattura: {exp.invoice_number}\n"

                    # Importi
                    output += f"  Imponibile: {exp.amount_net or 0:.2f} EUR\n"
                    output += f"  IVA: {exp.amount_vat or 0:.2f} EUR\n"
                    output += f"  Totale: {exp.amount_gross or 0:.2f} EUR\n"

                    # Categoria e centro di costo
                    if exp.category:
                        output += f"  Categoria: {exp.category}\n"
                    if exp.rc_center:
                        output += f"  Centro di costo: {exp.rc_center}\n"

                    # Deducibilità
                    if exp.tax_deductibility is not None and exp.tax_deductibility != 100:
                        output += f"  Deducibilità fiscale: {exp.tax_deductibility}%\n"
                    if exp.vat_deductibility is not None and exp.vat_deductibility != 100:
                        output += f"  Deducibilità IVA: {exp.vat_deductibility}%\n"

                    # E-invoice
                    if exp.e_invoice:
                        output += f"  Fattura elettronica: Sì\n"

                    # Pagamenti - solo se ci sono scadenze
                    if exp.payments_list and len(exp.payments_list) > 0:
                        for payment in exp.payments_list:
                            status_map = {'paid': 'Pagato', 'not_paid': 'Da pagare', 'reversed': 'Stornato'}
                            status = status_map.get(payment.status, payment.status)
                            output += f"  Pagamento: {payment.amount:.2f} EUR - Scadenza: {payment.due_date} - {status}\n"

                    # Descrizione
                    if hasattr(exp, 'description') and exp.description:
                        output += f"  Descrizione: {exp.description}\n"

                    output += "\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


async def handle_get_received_invoice(arguments: dict) -> list[TextContent]:
    """Dettaglio fattura ricevuta."""
    invoice_id = arguments.get("invoice_id")

    if not invoice_id:
        return [TextContent(type="text", text="Errore: invoice_id mancante")]

    with get_api_client() as api_client:
        api = received_documents_api.ReceivedDocumentsApi(api_client)

        try:
            response = api.get_received_document(
                company_id=COMPANY_ID,
                document_id=invoice_id,
                fieldset="detailed"
            )

            exp = response.data
            if not exp:
                return [TextContent(type="text", text="Fattura non trovata")]

            output = f"FATTURA RICEVUTA ID {exp.id}\n"
            output += f"{'=' * 60}\n\n"

            # Intestazione
            output += f"Data: {exp.var_date.strftime('%Y-%m-%d') if exp.var_date else 'N/A'}\n"
            if exp.invoice_number:
                output += f"N. Fattura fornitore: {exp.invoice_number}\n"
            if exp.e_invoice:
                output += f"Fattura elettronica: Sì\n"

            # Fornitore completo
            output += f"\nFORNITORE:\n"
            if exp.entity:
                output += f"  Nome: {exp.entity.name}\n"
                if exp.entity.vat_number:
                    output += f"  P.IVA: {exp.entity.vat_number}\n"
                if exp.entity.tax_code:
                    output += f"  C.F.: {exp.entity.tax_code}\n"
                if exp.entity.address_street:
                    output += f"  Indirizzo: {exp.entity.address_street}\n"
                    if exp.entity.address_postal_code and exp.entity.address_city:
                        output += f"           {exp.entity.address_postal_code} {exp.entity.address_city}"
                        if exp.entity.address_province:
                            output += f" ({exp.entity.address_province})"
                        output += "\n"
                if exp.entity.email:
                    output += f"  Email: {exp.entity.email}\n"
                if exp.entity.certified_email:
                    output += f"  PEC: {exp.entity.certified_email}\n"
                if exp.entity.phone:
                    output += f"  Tel: {exp.entity.phone}\n"

            # Importi
            output += f"\nIMPORTI:\n"
            output += f"  Imponibile: {exp.amount_net or 0:.2f} EUR\n"
            output += f"  IVA: {exp.amount_vat or 0:.2f} EUR\n"
            if exp.amount_withholding_tax and exp.amount_withholding_tax > 0:
                output += f"  Ritenuta d'acconto: {exp.amount_withholding_tax:.2f} EUR\n"
            if exp.amount_other_withholding_tax and exp.amount_other_withholding_tax > 0:
                output += f"  Altra ritenuta: {exp.amount_other_withholding_tax:.2f} EUR\n"
            output += f"  TOTALE: {exp.amount_gross or 0:.2f} EUR\n"

            # Deducibilità
            if exp.tax_deductibility is not None or exp.vat_deductibility is not None:
                output += f"\nDEDUCIBILITÀ:\n"
                if exp.tax_deductibility is not None:
                    output += f"  Fiscale: {exp.tax_deductibility}%\n"
                if exp.vat_deductibility is not None:
                    output += f"  IVA: {exp.vat_deductibility}%\n"

            # Categoria e centro di costo
            if exp.category or exp.rc_center:
                output += f"\nCLASSIFICAZIONE:\n"
                if exp.category:
                    output += f"  Categoria: {exp.category}\n"
                if exp.rc_center:
                    output += f"  Centro di costo: {exp.rc_center}\n"
                if exp.amortization:
                    output += f"  Ammortamento: {exp.amortization}\n"

            # Righe di dettaglio
            if exp.items_list and len(exp.items_list) > 0:
                output += f"\nRIGHE DI DETTAGLIO:\n"
                for item in exp.items_list:
                    output += f"  - {item.name}\n"
                    if item.qty and item.qty != 1:
                        output += f"    Quantità: {item.qty}"
                        if item.measure:
                            output += f" {item.measure}"
                        output += "\n"
                    output += f"    Importo: {item.net_price:.2f} EUR\n"
                    if item.vat and item.vat.value:
                        output += f"    IVA: {item.vat.value}%\n"

            # Pagamenti
            if exp.payments_list and len(exp.payments_list) > 0:
                output += f"\nPAGAMENTI:\n"
                for payment in exp.payments_list:
                    status_map = {'paid': 'Pagato', 'not_paid': 'Da pagare', 'reversed': 'Stornato'}
                    status = status_map.get(payment.status, payment.status)
                    output += f"  - Importo: {payment.amount:.2f} EUR\n"
                    output += f"    Scadenza: {payment.due_date}\n"
                    output += f"    Stato: {status}\n"
                    if payment.paid_date:
                        output += f"    Pagato il: {payment.paid_date}\n"
                    if payment.payment_terms:
                        output += f"    Termini: {payment.payment_terms.days} giorni\n"

            # Descrizione
            if exp.description:
                output += f"\nDESCRIZIONE:\n{exp.description}\n"

            # Allegato
            if exp.attachment_url:
                output += f"\nALLEGATO:\n{exp.attachment_url}\n"

            # Date di creazione/modifica
            if exp.created_at or exp.updated_at:
                output += f"\nINFO SISTEMA:\n"
                if exp.created_at:
                    output += f"  Creato: {exp.created_at}\n"
                if exp.updated_at:
                    output += f"  Modificato: {exp.updated_at}\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


async def handle_get_received_credit_notes(arguments: dict) -> list[TextContent]:
    """Note di credito ricevute dai fornitori (passive_credit_note).

    Gemello di handle_get_received_invoices: cambia solo il tipo documento e le
    etichette, e include SEMPRE descrizione e righe di dettaglio per il matching
    con le fatture originali (es. esclusione cespiti stornati da NC)."""
    from_date = arguments.get("from_date")
    to_date = arguments.get("to_date")
    supplier_name = arguments.get("supplier_name")
    limit = arguments.get("limit", 50)

    with get_api_client() as api_client:
        api = received_documents_api.ReceivedDocumentsApi(api_client)

        try:
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")
            if not from_date:
                from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

            # Se c'è un filtro fornitore e il periodo è > 120 giorni,
            # faccio query mese per mese per recuperare tutte le note di credito
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
            to_dt = datetime.strptime(to_date, "%Y-%m-%d")
            days_diff = (to_dt - from_dt).days

            all_expenses = []

            if supplier_name and days_diff > 120:
                # Query mese per mese CON PAGINAZIONE
                current_date = from_dt
                while current_date <= to_dt:
                    # Primo e ultimo giorno del mese
                    first_day = current_date.replace(day=1)
                    # Ultimo giorno del mese
                    if current_date.month == 12:
                        last_day = current_date.replace(day=31)
                    else:
                        next_month = current_date.replace(month=current_date.month + 1, day=1)
                        last_day = next_month - timedelta(days=1)

                    # Non superare to_date
                    if last_day > to_dt:
                        last_day = to_dt

                    q = f"date >= '{first_day.strftime('%Y-%m-%d')}' and date <= '{last_day.strftime('%Y-%m-%d')}'"

                    # Loop paginazione per questo mese
                    page = 1
                    while True:
                        response = api.list_received_documents(
                            company_id=COMPANY_ID,
                            type="passive_credit_note",
                            q=q,
                            page=page,
                            per_page=100,
                            fieldset="detailed"
                        )

                        if response.data:
                            all_expenses.extend(response.data)

                        # Verifica se ci sono altre pagine
                        if page >= response.last_page:
                            break

                        page += 1

                    # Prossimo mese
                    if current_date.month == 12:
                        current_date = current_date.replace(year=current_date.year + 1, month=1, day=1)
                    else:
                        current_date = current_date.replace(month=current_date.month + 1, day=1)
            else:
                # Query singola CON PAGINAZIONE
                q = f"date >= '{from_date}' and date <= '{to_date}'"

                # Loop paginazione
                page = 1
                while True:
                    response = api.list_received_documents(
                        company_id=COMPANY_ID,
                        type="passive_credit_note",
                        q=q,
                        page=page,
                        per_page=100,
                        fieldset="detailed"
                    )

                    if response.data:
                        all_expenses.extend(response.data)

                    # Verifica se ci sono altre pagine
                    if page >= response.last_page:
                        break

                    page += 1

            # Filtro per fornitore in Python (case-insensitive, partial match)
            if supplier_name:
                expenses = [
                    exp for exp in all_expenses
                    if exp.entity and supplier_name.lower() in exp.entity.name.lower()
                ]
                # Limito ai primi N risultati
                expenses = expenses[:limit]
            else:
                expenses = all_expenses[:limit]

            if not expenses:
                output = "Nessuna nota di credito ricevuta trovata."
            else:
                total_net = sum(exp.amount_net or 0 for exp in expenses)
                total_vat = sum(exp.amount_vat or 0 for exp in expenses)
                total_gross = sum(exp.amount_gross or 0 for exp in expenses)
                output = f"Trovate {len(expenses)} note di credito ricevute:\n"
                output += f"  Imponibile totale: {total_net:.2f} EUR\n"
                output += f"  IVA totale: {total_vat:.2f} EUR\n"
                output += f"  Totale: {total_gross:.2f} EUR\n\n"

                for exp in expenses:
                    doc_id = exp.id or 'N/A'
                    doc_date = exp.var_date.strftime("%Y-%m-%d") if exp.var_date else 'N/A'
                    output += f"- ID {doc_id} del {doc_date}\n"

                    # Fornitore con dettagli
                    if exp.entity:
                        output += f"  Fornitore: {exp.entity.name}\n"
                        if exp.entity.vat_number:
                            output += f"  P.IVA: {exp.entity.vat_number}\n"
                        if exp.entity.tax_code and exp.entity.tax_code != exp.entity.vat_number:
                            output += f"  C.F.: {exp.entity.tax_code}\n"
                    else:
                        output += f"  Fornitore: N/A\n"

                    # Numero documento fornitore
                    if exp.invoice_number:
                        output += f"  N. documento: {exp.invoice_number}\n"

                    # Importi
                    output += f"  Imponibile: {exp.amount_net or 0:.2f} EUR\n"
                    output += f"  IVA: {exp.amount_vat or 0:.2f} EUR\n"
                    output += f"  Totale: {exp.amount_gross or 0:.2f} EUR\n"

                    # Categoria e centro di costo
                    if exp.category:
                        output += f"  Categoria: {exp.category}\n"
                    if exp.rc_center:
                        output += f"  Centro di costo: {exp.rc_center}\n"

                    # E-invoice
                    if exp.e_invoice:
                        output += f"  Fattura elettronica: Sì\n"

                    # Descrizione - SEMPRE presente, non troncata (serve per il matching)
                    if hasattr(exp, 'description') and exp.description:
                        output += f"  Descrizione: {exp.description}\n"

                    # Righe di dettaglio - SEMPRE presenti (servono per il matching)
                    if exp.items_list and len(exp.items_list) > 0:
                        output += f"  RIGHE DI DETTAGLIO:\n"
                        for item in exp.items_list:
                            output += f"  - {item.name}\n"
                            if item.qty and item.qty != 1:
                                output += f"    Quantità: {item.qty}"
                                if item.measure:
                                    output += f" {item.measure}"
                                output += "\n"
                            output += f"    Importo: {item.net_price:.2f} EUR\n"
                            if item.vat and item.vat.value:
                                output += f"    IVA: {item.vat.value}%\n"

                    output += "\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


async def handle_get_unpaid_received_invoices(arguments: dict) -> list[TextContent]:
    """Fatture ricevute non ancora pagate (da pagare)."""
    limit = arguments.get("limit", 100)

    with get_api_client() as api_client:
        api = received_documents_api.ReceivedDocumentsApi(api_client)

        try:
            # Recupera tutte le fatture ricevute (ultimi 5 anni per includere storiche non pagate)
            # FIX 2026-02-07: aumentato da 730 a 1825 giorni per catturare fatture vecchie
            from_date = (datetime.now() - timedelta(days=1825)).strftime("%Y-%m-%d")
            to_date = datetime.now().strftime("%Y-%m-%d")

            q = f"date >= '{from_date}' and date <= '{to_date}'"

            # Loop paginazione per recuperare TUTTE le fatture
            all_expenses = []
            page = 1

            while True:
                response = api.list_received_documents(
                    company_id=COMPANY_ID,
                    type="expense",
                    q=q,
                    page=page,
                    per_page=100,
                    fieldset="detailed"
                )

                if response.data:
                    all_expenses.extend(response.data)

                # Verifica se ci sono altre pagine
                if page >= response.last_page:
                    break

                page += 1

            # Filtra solo quelle non pagate
            unpaid = []
            for exp in all_expenses:
                # Una fattura è "da pagare" se:
                # 1. Ha payments_list definito
                # 2. Almeno un pagamento ha status='not_paid'
                if exp.payments_list and len(exp.payments_list) > 0:
                    has_unpaid = any(p.status == 'not_paid' for p in exp.payments_list)
                    if has_unpaid:
                        unpaid.append(exp)

            # Limita risultati
            unpaid = unpaid[:limit]

            if not unpaid:
                output = "Nessuna fattura ricevuta da pagare trovata."
            else:
                # Calcola totale da pagare
                total_to_pay = 0
                for exp in unpaid:
                    for payment in exp.payments_list:
                        if payment.status == 'not_paid':
                            total_to_pay += payment.amount

                output = f"Trovate {len(unpaid)} fatture ricevute DA PAGARE:\n"
                output += f"TOTALE DA PAGARE: {total_to_pay:.2f} EUR\n"
                output += f"{'=' * 60}\n\n"

                for exp in unpaid:
                    doc_id = exp.id or 'N/A'
                    doc_date = exp.var_date.strftime("%Y-%m-%d") if exp.var_date else 'N/A'

                    # Fornitore
                    supplier_name = exp.entity.name if exp.entity else 'N/A'

                    # Numero fattura
                    invoice_num = exp.invoice_number or 'N/A'

                    # Totale fattura
                    total = exp.amount_gross or 0

                    output += f"- ID {doc_id} del {doc_date}\n"
                    output += f"  Fornitore: {supplier_name}\n"
                    output += f"  N. Fattura: {invoice_num}\n"
                    output += f"  Totale fattura: {total:.2f} EUR\n"

                    # Dettaglio pagamenti da fare
                    for payment in exp.payments_list:
                        if payment.status == 'not_paid':
                            output += f"  DA PAGARE: {payment.amount:.2f} EUR - Scadenza: {payment.due_date}\n"

                    output += "\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


async def handle_get_expenses_by_month(arguments: dict) -> list[TextContent]:
    """Spese mensili aggregate."""
    year = arguments.get("year")
    months = arguments.get("months", 12)

    with get_api_client() as api_client:
        api = received_documents_api.ReceivedDocumentsApi(api_client)

        try:
            if not year:
                year = datetime.now().year

            # Calcola range date
            from_date = f"{year}-01-01"
            to_date = f"{year}-12-31"

            q = f"date >= '{from_date}' and date <= '{to_date}'"

            # Loop paginazione per recuperare TUTTE le fatture
            expenses = []
            page = 1

            while True:
                response = api.list_received_documents(
                    company_id=COMPANY_ID,
                    type="expense",
                    q=q,
                    page=page,
                    per_page=100,
                    fieldset="detailed"
                )

                if response.data:
                    expenses.extend(response.data)

                # Verifica se ci sono altre pagine
                if page >= response.last_page:
                    break

                page += 1

            # Aggrega per mese
            monthly_totals = defaultdict(float)
            monthly_counts = defaultdict(int)

            for exp in expenses:
                if exp.var_date:
                    month = exp.var_date.strftime("%Y-%m")
                    monthly_totals[month] += exp.amount_gross or 0
                    monthly_counts[month] += 1

            if not monthly_totals:
                output = f"Nessuna spesa trovata per l'anno {year}."
            else:
                # Ordina per mese
                sorted_months = sorted(monthly_totals.keys())
                if len(sorted_months) > months:
                    sorted_months = sorted_months[-months:]

                total_year = sum(monthly_totals[m] for m in sorted_months)

                output = f"SPESE MENSILI - Anno {year}\n"
                output += f"{'=' * 40}\n\n"

                for month in sorted_months:
                    month_name = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
                    output += f"{month_name}:\n"
                    output += f"  Fatture: {monthly_counts[month]}\n"
                    output += f"  Importo: {monthly_totals[month]:.2f} EUR\n\n"

                output += f"TOTALE ANNO: {total_year:.2f} EUR\n"
                output += f"MEDIA MENSILE: {total_year / len(sorted_months):.2f} EUR\n"

            return [TextContent(type="text", text=output)]

        except Exception as e:
            return [TextContent(type="text", text=f"Errore: {str(e)}")]


def get_expense_tools():
    """Restituisce la lista di tool per spese."""
    return [
        Tool(
        name="get_received_invoices",
        description="Fatture ricevute da fornitori con filtri",
        inputSchema={
            "type": "object",
            "properties": {
                "from_date": {
                    "type": "string",
                    "description": "Data inizio (YYYY-MM-DD), default: ultimi 90 giorni"
                },
                "to_date": {
                    "type": "string",
                    "description": "Data fine (YYYY-MM-DD), default: oggi"
                },
                "supplier_name": {
                    "type": "string",
                    "description": "Filtra per nome fornitore (ricerca parziale)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero massimo risultati, default: 50"
                }
            }
        }
        ),
        Tool(
            name="get_received_credit_notes",
            description="Note di credito ricevute dai fornitori (passive_credit_note). Usato per verificare storni/resi su fatture passive (es. controllo cespiti). Include descrizione e righe di dettaglio per il matching con le fatture originali.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_date": {
                        "type": "string",
                        "description": "Data inizio (YYYY-MM-DD), default: ultimi 90 giorni"
                    },
                    "to_date": {
                        "type": "string",
                        "description": "Data fine (YYYY-MM-DD), default: oggi"
                    },
                    "supplier_name": {
                        "type": "string",
                        "description": "Filtra per nome fornitore (ricerca parziale)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Numero massimo risultati, default: 50"
                    }
                }
            }
        ),
        Tool(
            name="get_received_invoice",
            description="Dettaglio completo di una fattura ricevuta",
            inputSchema={
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "integer",
                        "description": "ID della fattura ricevuta"
                    }
                },
                "required": ["invoice_id"]
            }
        ),
        Tool(
            name="get_unpaid_received_invoices",
            description="Fatture ricevute non ancora pagate (da pagare ai fornitori)",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Numero massimo risultati, default: 100"
                    }
                }
            }
        ),
        Tool(
            name="get_expenses_by_month",
            description="Spese mensili aggregate per anno",
            inputSchema={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Anno di riferimento, default: anno corrente"
                    },
                    "months": {
                        "type": "integer",
                        "description": "Numero di mesi da mostrare (ultimi N), default: 12"
                    }
                }
            }
        ),
    ]


def get_expense_handlers():
    """Restituisce il dizionario di handler per spese."""
    return {
        "get_received_invoices": handle_get_received_invoices,
        "get_received_credit_notes": handle_get_received_credit_notes,
        "get_received_invoice": handle_get_received_invoice,
        "get_unpaid_received_invoices": handle_get_unpaid_received_invoices,
        "get_expenses_by_month": handle_get_expenses_by_month,
    }
