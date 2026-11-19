"""
Hard rules that force an escalation regardless of confidence.

They cover the weakness of consistency-based confidence:
an LLM that is consistently wrong still looks confident.

Each rule receives the action, its risk, the business facts
from the state and the rule configuration, and returns a
rule id when it fires. Rules without the data they need
do not fire (no guessing).
"""

from typing import Any, Callable


Rule = Callable[[dict, str, dict, dict], str | None]


def _amount(args: dict[str, Any]) -> float | None:
    """Total amount from explicit fields or item lines."""

    for field in ("grand_total", "total", "amount", "paid_amount"):
        value = args.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)

    items = args.get("items")
    if isinstance(items, list) and items:
        total = 0.0
        for item in items:
            if not isinstance(item, dict):
                return None
            qty, rate = item.get("qty"), item.get("rate")
            if not isinstance(qty, (int, float)) or not isinstance(rate, (int, float)):
                return None
            total += qty * rate
        return total

    return None


def rule_new_supplier(action, risk, facts, cfg):
    if not cfg.get("escalate_new_supplier"):
        return None

    supplier = action.get("args", {}).get("supplier")
    known = facts.get("known_suppliers")

    if supplier is None or not isinstance(known, list):
        return None

    if supplier not in known:
        return "new_supplier"

    return None


def rule_amount_limit(action, risk, facts, cfg):
    limit = cfg.get("max_amount")
    amount = _amount(action.get("args", {}))

    if limit is None or amount is None:
        return None

    if amount > limit:
        return "amount_over_limit"

    return None


def rule_price_deviation(action, risk, facts, cfg):
    max_dev = cfg.get("max_price_deviation")
    last_prices = facts.get("last_prices")
    items = action.get("args", {}).get("items")

    if max_dev is None or not isinstance(last_prices, dict) or not isinstance(items, list):
        return None

    for item in items:
        if not isinstance(item, dict):
            continue

        last = last_prices.get(item.get("item_code"))
        rate = item.get("rate")

        if not isinstance(last, (int, float)) or not isinstance(rate, (int, float)) or last == 0:
            continue

        if abs(rate - last) / last > max_dev:
            return "price_deviation"

    return None


RULES: list[Rule] = [
    rule_new_supplier,
    rule_amount_limit,
    rule_price_deviation,
]


def check_rules(
    action: dict[str, Any],
    risk: str,
    facts: dict[str, Any] | None,
    cfg: dict[str, Any]
) -> list[str]:
    """
    Return the ids of all hard rules that fire.
    Read-only actions are never blocked by rules.
    """

    if risk == "read":
        return []

    facts = facts or {}
    hits = []

    for rule in RULES:
        hit = rule(action, risk, facts, cfg)
        if hit:
            hits.append(hit)

    return hits
