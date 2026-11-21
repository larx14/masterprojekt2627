"""
ERPNext-Client: einzige Stelle, an der HTTP-Requests nach ERPNext gehen.
Bisher nur GET-Methoden. Dieser erpnext_client wird demnach von read_tools genutzt um bei ERPNext nach Dokumenten zu suchen

Umgebungsvariablen: ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET
"""

import json
import os
from typing import Any
from urllib.parse import quote

import requests

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

TIMEOUT = 15


class ERPNextError(Exception):
    """Netzwerkfehler oder Fehlerstatus von ERPNext."""


def _get(path: str, params: dict[str, Any] | None = None) -> requests.Response:
    url = os.environ["ERPNEXT_URL"].rstrip("/") + path
    headers = {
        "Authorization": f"token {os.environ['ERPNEXT_API_KEY']}:{os.environ['ERPNEXT_API_SECRET']}"
    }
    try:
        return requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ERPNextError(f"Request failed: {exc}") from exc

# Prüft HTTP-Status und JSON-Format der Antwort; bei Fehler ERPNextError.

def _json(response: requests.Response) -> Any:
    """Wirft ERPNextError bei Fehlerstatus oder ungültigem JSON, sonst Body als Python-Objekt."""
    if not response.ok:
        raise ERPNextError(f"HTTP {response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError as exc:
        raise ERPNextError("Response is not valid JSON.") from exc


#Bei fehlender Übergabe eines Paramters ist die Liste auf 10 Einträge begrenzt.
def get_list(doctype: str, filters: list, fields: list[str], limit: int = 0) -> list[dict]:
    params = {
        "filters": json.dumps(filters),
        "fields": json.dumps(fields),
        "limit_page_length": limit,
    }
    return _json(_get(f"/api/resource/{quote(doctype)}", params)).get("data", [])


def get_doc(doctype: str, name: str) -> dict | None:
    """Gibt das Dokument zurück, oder None wenn es nicht existiert."""
    response = _get(f"/api/resource/{quote(doctype)}/{quote(name, safe='')}")
    if response.status_code == 404:
        return None
    return _json(response).get("data")


def get_count(doctype: str, filters: list) -> int:
    params = {"doctype": doctype, "filters": json.dumps(filters)}
    return int(_json(_get("/api/method/frappe.client.get_count", params)).get("message", 0))