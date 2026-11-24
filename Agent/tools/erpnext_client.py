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

def _post(
    path: str,
    data: dict[str, Any],
) -> requests.Response:
    """
    Send an authenticated POST request to ERPNext.
    """

    url = os.environ["ERPNEXT_URL"].rstrip("/") + path

    headers = {
        "Authorization": (
            f"token {os.environ['ERPNEXT_API_KEY']}:"
            f"{os.environ['ERPNEXT_API_SECRET']}"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        return requests.post(
            url,
            json=data,
            headers=headers,
            timeout=TIMEOUT,
        )

    except requests.Timeout as exc:
        raise ERPNextError(
            "Request timed out. The ERPNext operation "
            "may already have been completed."
        ) from exc

    except requests.RequestException as exc:
        raise ERPNextError(
            f"Request failed: {exc}"
        ) from exc



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

def create_doc(
    doctype: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a new draft document in ERPNext.

    ERPNext assigns the document name.
    """

    response = _post(
        f"/api/resource/{quote(doctype, safe='')}",
        data,
    )

    body = _json(response)
    document = body.get("data")

    if not isinstance(document, dict):
        raise ERPNextError(
            "ERPNext returned an invalid document."
        )

    return document

def submit_doc(
    doctype: str,
    name: str,
) -> dict[str, Any]:
    """
    Submit an existing ERPNext document.

    The document must exist and be in draft status.
    """

    document = get_doc(doctype, name)

    if document is None:
        raise ERPNextError(
            f"Document '{name}' does not exist."
        )

    if document.get("docstatus") != 0:
        raise ERPNextError(
            "Only draft documents can be submitted."
        )

    response = _post(
        "/api/method/frappe.client.submit",
        {"doc": document},
    )

    body = _json(response)
    submitted = body.get("message")

    if not isinstance(submitted, dict):
        raise ERPNextError(
            "ERPNext returned an invalid submit response."
        )

    if submitted.get("docstatus") != 1:
        raise ERPNextError(
            "ERPNext did not confirm document submission."
        )

    return submitted

def map_document(
    method: str,
    source_name: str,
    mapping_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Prepare a mapped ERPNext document without saving it.

    Mapping arguments are serialized because the Frappe
    mapping endpoint expects JSON-encoded arguments.
    """

    payload = {
        "method": method,
        "source_name": source_name,
    }

    if mapping_args:
        payload["args"] = json.dumps(mapping_args)

    response = _post(
        "/api/method/frappe.model.mapper.make_mapped_doc",
        payload,
    )

    body = _json(response)

    if not isinstance(body, dict):
        raise ERPNextError(
            "ERPNext returned an invalid mapping response."
        )

    document = body.get("message")

    if not isinstance(document, dict):
        raise ERPNextError(
            "ERPNext did not return a mapped document."
        )

    return document

def prepare_payment_entry(
    invoice_name: str,
    *,
    bank_account: str,
    reference_date: str | None = None,
) -> dict[str, Any]:
    """Request an unsaved Payment Entry for a Purchase Invoice.

    bank_account is the ERPNext company bank/cash GL Account name.
    This RPC must only be invoked through an approved mapping.
    """
    payload = {
        "dt": "Purchase Invoice",
        "dn": invoice_name,
        "bank_account": bank_account,
    }
    if reference_date is not None:
        payload["reference_date"] = reference_date
    response = _post(
        "/api/method/erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
        payload,
    )
    body = _json(response)
    if not isinstance(body, dict) or not isinstance(body.get("message"), dict):
        raise ERPNextError("ERPNext returned an invalid Payment Entry draft.")
    return body["message"]
