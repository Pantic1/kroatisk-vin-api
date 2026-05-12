# services/dinero_mapper.py
from typing import Dict, Any, List
from decimal import Decimal

from config.model import Company


def to_dk(n) -> float:
    # sikre float (Dinero forventer decimaler i JSON)
    try:
        return float(n)
    except Exception:
        return 0.0


def build_contact_payload(company: Company):
    return {
        "Name": company.name,
        "Street": company.address or "",
        "ZipCode": company.zip or "",
        "City": company.city or "",
        "CountryKey": "DK",
        "Email": getattr(company, "email", None),
        "Phone": getattr(company, "phone", None),
        "IsCustomer": True,
    }


def build_invoice_lines(items) -> List[Dict[str, Any]]:
    lines = []
    for it in items or []:
        desc = getattr(it, "name", None) or getattr(
            it, "product_name", None) or "Vare"
        qty = to_dk(getattr(it, "quantity", 1))
        price = to_dk(getattr(it, "price", 0))
        # Tilpas disse konti til din kontoplan i Dinero
        lines.append({
            "Description": desc,
            "Quantity": qty,
            "UnitPrice": price,        # ekskl. moms
            "AccountNumber": 1010,     # Salg af vareydelser (eksempel)
            "VatRate": 25,             # 25% moms
        })
    return lines


def build_invoice_payload(contact_guid: str, order) -> Dict[str, Any]:
    return {
        "ContactGuid": contact_guid,
        "ExternalReference": str(order.id),
        # Hvis du vil styre betalingsbetingelser: "PaymentTermsDays": 14,
        "Lines": build_invoice_lines(order.items),
    }
