import os
import requests
from typing import Dict, Any

GLS_BASE_URL = os.getenv("GLS_BASE_URL", "https://api.gls.dk/shipping")  # justér til korrekt endpoint
GLS_API_KEY  = os.getenv("GLS_API_KEY")  # eller client_id/secret alt efter jeres setup

class GLSCreateError(Exception):
    pass

def create_shipment(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Kalder GLS og opretter en forsendelse.
    Returnerer GLS' response som dict.
    """
    if not GLS_API_KEY:
        raise GLSCreateError("GLS_API_KEY mangler i miljøvariabler")

    url = f"{GLS_BASE_URL}/v1/shipments"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GLS_API_KEY}",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=20)
    print(resp)
    try:
        data = resp.json()
    except Exception:
        data = {}

    if not resp.ok:
        msg = data.get("message") or data.get("error") or resp.text
        print(msg)
        raise GLSCreateError(f"GLS fejl {resp.status_code}: {msg}")

    return data
