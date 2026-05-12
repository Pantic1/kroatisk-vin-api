# services/dinero_invoice.py
from typing import Optional
from services.dinero_client import get, post, DineroError
from services.dinero_mapper import build_contact_payload, build_invoice_payload

def find_contact_by_name(name: str) -> Optional[str]:
    # Brug queryFilter (fx ContactGuid via navn/email). Eksempel: filter på Name
    # /invoices understøtter queryFilter; bruger samme mønster på contacts i deres API.
    res = get("/contacts", params={"pageSize": 50, "queryFilter": f"Name+eq+'{name}'"})
    for c in res.get("Collection", []):
        if c.get("Name") == name:
            return c.get("Guid")
    return None

def create_contact(company) -> str:
    payload = build_contact_payload(company)
    res = post("/contacts", payload)
    return res.get("Guid") or res.get("GuidId") or res.get("ContactGuid")

def ensure_contact(company) -> str:
    guid = find_contact_by_name(company.name)
    if guid:
        return guid
    return create_contact(company)

def create_invoice_draft(order) -> dict:
    contact_guid = ensure_contact(order.company)
    payload = build_invoice_payload(contact_guid, order)
    res = post("/invoices", payload)  # draft invoice i "Salg"
    # svar indeholder typisk "Guid" for fakturaen
    return res

def book_invoice(invoice_guid: str) -> dict:
    # Book fakturaen (gør den regnskabsmæssig)
    # API’et har en booking-operation—typisk /invoices/{guid}/book eller separat body “book and send”
    # Vi bruger her “book and send” hvis tilgængelig, ellers “book”
    try:
        return post(f"/invoices/{invoice_guid}/book", {})
    except DineroError:
        # fallback: book+send
        return post(f"/invoices/{invoice_guid}/bookandsend", {"EmailTo": ""})
