
"""
Generic ERPNext document mapping tool. => THis is needed to create documents from other documents, e.g., Material Request -> Purchase Order

Uses approved ERPNext-internal mapping methods to prepare
target documents from existing source documents.

The Payment Entry preparation uses a dedicated ERPNext RPC endpoint.

This tool does not save or submit the mapped document.
Right now it only supports this mapping for MCP (Purchase to pay) 
"""

from typing import Any

from Agent.tools import erpnext_client as client
from Agent.tools.erpnext_client import ERPNextError
from Agent.tools.registry import (
    MAPPING_METHODS,
    render_mapping_overview,
)

PAYMENT_SOURCE = ("Purchase Invoice", "Payment Entry")
RESULT_FIELDS = {
    "mapped": "bool",
    "source_doctype": "str",
    "source_name": "str",
    "target_doctype": "str",
    "data": "dict",
}

def get_map_tool_specs() -> list[dict[str, Any]]:
    """Describe approved source-to-target document transformations."""
    return [{
        "name": "erp_map_document",
        "description": (
            "Prepare an unsaved target ERPNext document from a verified source. "
            "Only approved mappings are available. "
            "Purchase Invoice -> Payment Entry requires a verified bank_account "
            "(the company bank/cash GL Account, not a Bank Account record). "
            "Do not invent accounting data or payment references.\n"
            f"{render_mapping_overview()}\n- Purchase Invoice -> Payment Entry"
        ),
        "risk": "read",  # Governance should additionally consider target_doctype.
        "parameters": {
            "source_doctype": "str", "source_name": "str",
            "target_doctype": "str", "mapping_args": "dict",
        },
        "result_fields": RESULT_FIELDS,
    }]


def _validate_map_args(args: dict[str, Any]) -> tuple[str, str, str, str, dict]:
    if not isinstance(args, dict):
        raise ValueError("Mapping arguments must be a dictionary.")
    source = args.get("source_doctype")
    target = args.get("target_doctype")
    name = args.get("source_name")
    options = args.get("mapping_args", {})
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A valid source document name is required.")
    if not isinstance(options, dict):
        raise ValueError("Mapping options must be a dictionary.")
    if (source, target) == PAYMENT_SOURCE:
        if set(options) - {"bank_account", "reference_date"}:
            raise ValueError("Unsupported Payment Entry mapping options.")
        bank = options.get("bank_account")
        if not isinstance(bank, str) or not bank.strip():
            raise ValueError("A verified company bank/cash account is required.")
        if "reference_date" in options and (
            not isinstance(options["reference_date"], str)
            or not options["reference_date"].strip()
        ):
            raise ValueError("reference_date must be a non-empty string.")
        return "payment", name, source, target, options
    method = MAPPING_METHODS.get((source, target))
    if not method:
        raise ValueError("The requested document mapping is not allowed.")
    if options and (source, target) != ("Material Request", "Purchase Order"):
        raise ValueError("Mapping options are not supported for this transition.")
    if set(options) - {"supplier"}:
        raise ValueError("Unsupported mapping options were provided.")
    if "supplier" in options and (
        not isinstance(options["supplier"], str) or not options["supplier"].strip()
    ):
        raise ValueError("Supplier must be a non-empty string.")
    return method, name, source, target, options


def run_map_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Return the standard status/result envelope for an unsaved mapping."""
    if tool != "erp_map_document":
        return {"status": "failed", "result": None, "errors": [f"Unknown tool '{tool}'."]}
    try:
        method, source_name, source, target, options = _validate_map_args(args)
        if method == "payment":
            document = client.prepare_payment_entry(
                source_name,
                bank_account=options["bank_account"],
                reference_date=options.get("reference_date"),
            )
        else:
            document = client.map_document(
                method=method, source_name=source_name, mapping_args=options
            )
        if not isinstance(document, dict) or document.get("doctype") != target:
            raise ValueError("ERPNext returned an unexpected target DocType.")
        if document.get("docstatus", 0) != 0:
            raise ValueError("Mapped document is not a draft.")
        detail_field = "references" if target == "Payment Entry" else "items"
        if not isinstance(document.get(detail_field), list) or not document[detail_field]:
            raise ValueError(f"Mapped document has no {detail_field}.")
        return {
            "status": "completed",
            "result": {
                "mapped": True, "source_doctype": source,
                "source_name": source_name, "target_doctype": target,
                "data": document,
            },
        }
    except (ERPNextError, ValueError, KeyError, TypeError) as exc:
        return {"status": "failed", "result": None,
                "errors": [f"{type(exc).__name__}: {exc}"]}
