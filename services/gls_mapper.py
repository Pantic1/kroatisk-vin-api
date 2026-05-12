from typing import Dict, Any
from config.model import Company, Order


def map_order_to_gls_payload(order: Order, company: Company) -> Dict[str, Any]:
    """
    Eksempel-body. Tilpas felter til jeres GLS-kontrakt:
    - serviceCode: fx "PARCEL" eller specifik produktkode
    - receiver: navn/adresse/postnr/by/land
    - reference: order.id eller ordrenr.
    - parcels: 1 eller flere. Her laver vi 1 pakke og summerer vægt.
    """
    print("Mapping order to GLS payload", order.id)
    # Fald tilbage hvis vægte ikke findes – sæt en sikker default
    # (Bedst er at have vægt pr. produkt/linje)
    weight_grams = 0
    for it in order.items or []:
        # forvent fx it.weight_grams; ellers default 200g pr. stk
        w = getattr(it, "weight_grams", None)
        qty = float(getattr(it, "quantity", 1) or 1)
        weight_grams += (w if isinstance(w, (int, float))
                         and w > 0 else 200) * qty

    if weight_grams <= 0:
        weight_grams = 500  # minimum 0.5 kg default

    payload = {
        "serviceCode": "PARCEL",   # eller specifik service som "SHOPDELIVERYSERVICE"
        "reference": str(order.id),
        "receiver": {
            "name": company.name if company else "Kunde",
            "address1": company.address if company else "",
            "zipCode": company.zip if company else "",
            "city": company.city if company else "",
            "countryCode": getattr(company, "country_code", "DK"),
            "email": getattr(company, "email", None),
            "phone": getattr(company, "phone", None),
        },
        "parcels": [
            {
                "weightInGrams": int(weight_grams),
                "contents": "Varer",
            }
        ],
        # Du afleverer i pakkeshop:
        "sender": {
            "name": "Matcha Prime",   # dit firmanavn
            "address1": "Møgelgårdsvej 18",
            "zipCode": "8520",
            "city": "Lystrup",
            "countryCode": "DK",
            "email": "info@matchaprime.dk",
            "phone": "+45 61731810",
        },
        # pakkeshop du selv afleverer pakken i
        "dropOffPointId": "2080099081",
    }
    return payload
