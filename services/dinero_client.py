# services/dinero_client.py
import os, requests
from typing import Dict, Any, Optional

DINERO_BASE = "https://api.dinero.dk/v1"

class DineroError(Exception): ...

def dinero_headers() -> Dict[str, str]:
    token = os.getenv("DINERO_ACCESS_TOKEN")
    if not token:
        raise DineroError("DINERO_ACCESS_TOKEN mangler")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def dinero_org() -> str:
    org = os.getenv("DINERO_ORG_ID")
    if not org:
        raise DineroError("DINERO_ORG_ID mangler")
    return org

def post(path: str, json: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{DINERO_BASE}/{dinero_org()}{path}"
    r = requests.post(url, headers=dinero_headers(), json=json, timeout=30)
    data = r.json() if r.content else {}
    if not r.ok:
        raise DineroError(data.get("message") or data.get("title") or str(data) or r.text)
    return data

def get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{DINERO_BASE}/{dinero_org()}{path}"
    r = requests.get(url, headers=dinero_headers(), params=params or {}, timeout=30)
    data = r.json() if r.content else {}
    if not r.ok:
        raise DineroError(data.get("message") or data.get("title") or str(data) or r.text)
    return data
