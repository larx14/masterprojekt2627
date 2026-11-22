"""
Drei generische, lesende ERPNext-Tools (MVP):

    erp_search  Dokumente eines DocTypes mit Filtern suchen
    erp_get     ein Dokument über seinen Namen holen
    erp_count   Anzahl passender Dokumente

Alle Tools liefern dieselbe Ergebnis-Hülle, damit der Condition Evaluator
überall mit denselben result_fields arbeiten kann:

    {"found": bool, "count": int, "name": str | None, "data": list}

Einstiegspunkt für den Executor: run_read_tool(tool, args)
"""

from Agent.tools import erpnext_client as client
from Agent.tools.erpnext_client import ERPNextError
from Agent.tools.registry import AVAILABLE_DOCTYPES, render_registry_overview

LIMIT = 20
RESULT_FIELDS = {"found": "bool", "count": "int", "name": "str", "data": "list"}


def get_read_tool_specs() -> list[dict]:
    """Tool-Katalog für Planner und Action Preparer."""

    overview = render_registry_overview()
    filter_help = (
        'filters: list of [field, operator, value], e.g. '
        '[["supplier_name", "like", "%Müller%"]]. Use [] for no filter.'
    )

    return [
        {
            "name": "erp_search",
            "description": f"Search documents of one DocType (max {LIMIT} rows). "
                           f"{filter_help}\n{overview}",
            "risk": "read",
            "parameters": {"doctype": "str", "filters": "list"},
            "result_fields": RESULT_FIELDS,
        },
        {
            "name": "erp_get",
            "description": f"Fetch one document by its exact name (ID).\n{overview}",
            "risk": "read",
            "parameters": {"doctype": "str", "name": "str"},
            "result_fields": RESULT_FIELDS,
        },
        {
            "name": "erp_count",
            "description": f"Count documents of one DocType. {filter_help}\n{overview}",
            "risk": "read",
            "parameters": {"doctype": "str", "filters": "list"},
            "result_fields": RESULT_FIELDS,
        },
    ]


def _envelope(data: list[dict], count: int | None = None) -> dict:
    count = len(data) if count is None else count
    name = data[0].get("name") if data else None
    return {"found": count > 0, "count": count, "name": name, "data": data}


def run_read_tool(tool: str, args: dict) -> dict:
    """
    Führt ein Read-Tool aus. Rückgabe im Format der step_results:
        {"status": "completed", "result": {...}}
        {"status": "failed", "result": None, "errors": [...]}

    "Nichts gefunden" ist kein Fehler: completed mit found=False.
    """

    doctype = args.get("doctype")
    if doctype not in AVAILABLE_DOCTYPES:
        return {"status": "failed", "result": None,
                "errors": [f"DocType '{doctype}' is not available."]}

    try:
        if tool == "erp_search":
            rows = client.get_list(
                doctype, args["filters"], AVAILABLE_DOCTYPES[doctype], LIMIT
            )
            result = _envelope(rows)

        elif tool == "erp_get":
            doc = client.get_doc(doctype, args["name"])
            result = _envelope([doc] if doc else [])

        elif tool == "erp_count":
            result = _envelope([], client.get_count(doctype, args["filters"]))

        else:
            return {"status": "failed", "result": None,
                    "errors": [f"Unknown tool '{tool}'."]}

    except (ERPNextError, KeyError) as exc:
        return {"status": "failed", "result": None, "errors": [repr(exc)]}

    return {"status": "completed", "result": result}