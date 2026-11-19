"""
Classify the business risk of an action.

Order: explicit 'risk' in the tool specification wins.
Otherwise the risk is derived from tool name and arguments,
so generic tools (get/create/submit) are covered as well.
"""

from typing import Any

from Governance.config import RISK_LEVELS


READ_PREFIXES = ("get", "find", "list", "read", "search", "lookup", "fetch")


def classify_risk(
    tool_spec: dict[str, Any] | None,
    args: dict[str, Any] | None
) -> str:

    tool_spec = tool_spec or {}
    args = args or {}

    explicit = tool_spec.get("risk")
    if explicit is not None:
        if explicit not in RISK_LEVELS:
            raise ValueError(f"Unknown risk level '{explicit}'.")
        return explicit

    name = str(tool_spec.get("name", "")).lower()
    doctype = str(args.get("doctype", "")).lower()

    if "payment" in name or doctype == "payment entry":
        return "payment"

    if name.startswith(READ_PREFIXES):
        return "read"

    if "submit" in name or args.get("docstatus") == 1:
        return "submit"

    return "draft"


def initial_samples(
    tool_spec: dict[str, Any] | None,
    cfg: dict[str, Any]
) -> int:
    """
    Number of samples for the first preparation round.
    Read-only steps are not gated and need one sample.
    """

    if classify_risk(tool_spec, {}) == "read":
        return 1

    return int(cfg["sampling"]["n_initial"])
