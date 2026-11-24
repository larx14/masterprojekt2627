"""Generic draft creation for an allowlisted set of ERPNext DocTypes.

Requires Agent.tools.erpnext_client.create_doc(doctype, data) -> dict.
Return format matches run_read_tool: status/result/errors.
"""

from copy import deepcopy
from typing import Any

from Agent.tools import erpnext_client as client
from Agent.tools.erpnext_client import ERPNextError

# Preliminary MVP (Purchase-to-Pay)
SUPPORTED_DOCTYPES = frozenset({
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Payment Entry",
    "Supplier", 
})

RESULT_FIELDS = {
    "created": "bool",
    "doctype": "str",
    "name": "str",
    "docstatus": "int",
    "data": "dict",
}

_FORBIDDEN_FIELDS = frozenset({
    "name", "doctype", "docstatus", "owner", "creation", "modified",
    "modified_by", "workflow_state", "amended_from",
})


def get_create_tool_specs() -> list[dict[str, Any]]:
    """Return the generic create tool spec for Planner and Action Preparer."""
    return [{
        "name": "erp_create",
        "description": (
            "Create a draft ERPNext document (docstatus 0). Supported DocTypes: "
            "Material Request, Purchase Order, Purchase Receipt, "
            "Purchase Invoice, Payment Entry. Use verified field names and "
            "business values. For documents based on earlier documents, "
            "preserve source-document and source-row references. "
            "This tool never submits documents."
        ),
        "risk": "draft",
        "parameters": {"doctype": "str", "data": "dict"},
        "result_fields": RESULT_FIELDS,
    }]


def _validate_args(args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Enforce basic tool-contract checks before calling ERPNext."""
    if not isinstance(args, dict):
        raise ValueError("Arguments must be an object.")
    if set(args) != {"doctype", "data"}:
        raise ValueError("Expected exactly 'doctype' and 'data'.")

    doctype = args["doctype"]
    data = args["data"]
    if not isinstance(doctype, str) or doctype not in SUPPORTED_DOCTYPES:
        raise ValueError(f"DocType '{doctype}' is not allowed for creation.")
    if not isinstance(data, dict) or not data:
        raise ValueError("Document data must be a nonempty object.")
    if any(field in data for field in _FORBIDDEN_FIELDS):
        raise ValueError("Document data contains a protected field.")
    if any(not isinstance(field, str) for field in data):
        raise ValueError("Document field names must be strings.")

    # A separate DocType-specific schema / policy validator is required
    # before enabling write operations on a production ERPNext instance.
    return doctype, deepcopy(data)


def run_create_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Create one draft; never submit or automatically retry a write."""
    if tool != "erp_create":
        return {"status": "failed", "result": None,
                "errors": [f"Unknown tool '{tool}'."]}

    try:
        doctype, data = _validate_args(args)
    except (ValueError, TypeError) as exc:
        return {"status": "failed", "result": None, "errors": [str(exc)]}

    try:
        document = client.create_doc(doctype, data)
    except ERPNextError as exc:
        # Remote write outcome may be uncertain after transport failure.
        return {"status": "failed", "result": None,
                "errors": [f"ERPNext create failed or outcome is unknown: {exc}"]}

    if not isinstance(document, dict):
        return {"status": "unconfirmed", "result": None,
                "errors": ["ERPNext returned a non-object response; check for an existing document before retrying."]}

    name = document.get("name")
    docstatus = document.get("docstatus")
    if not isinstance(name, str) or not name or type(docstatus) is not int or docstatus != 0:
        return {"status": "unconfirmed", "result": None,
                "errors": ["ERPNext did not confirm a named draft; reconcile before retrying."]}

    return {
        "status": "completed",
        "result": {
            "created": True,
            "doctype": doctype,
            "name": name,
            "docstatus": 0,
            "data": deepcopy(document),
        },
    }
