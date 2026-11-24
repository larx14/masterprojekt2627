"""Generic submission for existing ERPNext draft documents.

Requires Agent.tools.erpnext_client.get_doc(doctype, name) -> dict and
Agent.tools.erpnext_client.submit_doc(doctype, name) -> dict.
Return format matches run_read_tool: status/result/errors.
"""

from typing import Any

from Agent.tools import erpnext_client as client
from Agent.tools.erpnext_client import ERPNextError
from Agent.tools.erp_create import SUPPORTED_DOCTYPES

RESULT_FIELDS = {
    "submitted": "bool",
    "doctype": "str",
    "name": "str",
    "docstatus": "int",
}


def get_submit_tool_specs() -> list[dict[str, Any]]:
    """Return the generic submit tool spec for Planner and Action Preparer."""
    return [{
        "name": "erp_submit",
        "description": (
            "Submit exactly one existing ERPNext draft by DocType and document "
            "name. Supported DocTypes: Material Request, Purchase Order, "
            "Purchase Receipt, Purchase Invoice, Payment Entry. "
            "Only use a verified document name returned by an earlier step. "
            "Submission may have financial or inventory side effects."
        ),
        "risk": "submit",
        "parameters": {"doctype": "str", "name": "str"},
        "result_fields": RESULT_FIELDS,
    }]


def _validate_args(args: dict[str, Any]) -> tuple[str, str]:
    """Validate the requested document identity."""
    if not isinstance(args, dict) or set(args) != {"doctype", "name"}:
        raise ValueError("Expected exactly 'doctype' and 'name'.")
    doctype = args["doctype"]
    name = args["name"]
    if not isinstance(doctype, str) or doctype not in SUPPORTED_DOCTYPES:
        raise ValueError(f"DocType '{doctype}' is not allowed for submission.")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Document name must be a nonempty string.")
    return doctype, name


def run_submit_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Submit one verified draft; never automatically retry a write."""
    if tool != "erp_submit":
        return {"status": "failed", "result": None,
                "errors": [f"Unknown tool '{tool}'."]}

    try:
        doctype, name = _validate_args(args)
    except (ValueError, TypeError) as exc:
        return {"status": "failed", "result": None, "errors": [str(exc)]}

    try:
        existing = client.get_doc(doctype, name)
        if not isinstance(existing, dict) or existing.get("name") != name:
            return {"status": "failed", "result": None,
                    "errors": ["The target document was not found or did not match."]}

        if type(existing.get("docstatus")) is not int or existing["docstatus"] != 0:
            return {"status": "failed", "result": None,
                    "errors": ["Only draft documents (docstatus 0) can be submitted."]}

        document = client.submit_doc(doctype, name)
    except ERPNextError as exc:
        return {"status": "unconfirmed", "result": None,
                "errors": [f"ERPNext submission failed or outcome is unknown: {exc}. Reconcile before retrying."]}

    if (not isinstance(document, dict)
            or document.get("name") != name
            or type(document.get("docstatus")) is not int
            or document["docstatus"] != 1):
        return {"status": "unconfirmed", "result": None,
                "errors": ["ERPNext did not confirm submission; reconcile before retrying."]}

    return {
        "status": "completed",
        "result": {
            "submitted": True,
            "doctype": doctype,
            "name": name,
            "docstatus": 1,
        },
    }
