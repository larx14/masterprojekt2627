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


def format_eur(value: float) -> str:
    """1200.5 -> '1.200,50 €' (German number format)."""
    text = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{text} €"


def action_amount(action: dict[str, Any] | None) -> float | None:
    """Total amount of an action, or None if it cannot be determined."""
    return _amount((action or {}).get("args") or {})


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


def _price_deviations(action, facts, cfg) -> list[tuple[str, float, float, float]]:
    """(item_code, rate, last_price, deviation) for every item above the limit."""

    max_dev = cfg.get("max_price_deviation")
    last_prices = facts.get("last_prices")
    items = action.get("args", {}).get("items")

    if max_dev is None or not isinstance(last_prices, dict) or not isinstance(items, list):
        return []

    found = []

    for item in items:
        if not isinstance(item, dict):
            continue

        last = last_prices.get(item.get("item_code"))
        rate = item.get("rate")

        if not isinstance(last, (int, float)) or not isinstance(rate, (int, float)) or last == 0:
            continue

        deviation = (rate - last) / last
        if abs(deviation) > max_dev:
            found.append((item.get("item_code"), rate, last, deviation))

    return found


def rule_price_deviation(action, risk, facts, cfg):
    return "price_deviation" if _price_deviations(action, facts, cfg) else None


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


def describe_hits(
    hits: list[str],
    action: dict[str, Any],
    facts: dict[str, Any] | None,
    cfg: dict[str, Any]
) -> list[str]:
    """
    German explanation with the concrete values for each rule hit,
    e.g. 'Betrag 1.200,00 € liegt über dem Limit von 1.000,00 €.'
    """

    facts = facts or {}
    details = []

    for hit in hits:
        if hit == "new_supplier":
            supplier = action.get("args", {}).get("supplier")
            details.append(f"Lieferant {supplier} ist noch nicht als bekannter Lieferant hinterlegt.")

        elif hit == "amount_over_limit":
            amount = action_amount(action)
            details.append(f"Betrag {format_eur(amount)} liegt über dem Limit "
                           f"von {format_eur(float(cfg['max_amount']))}.")

        elif hit == "price_deviation":
            for code, rate, last, deviation in _price_deviations(action, facts, cfg):
                details.append(f"{code}: Preis {format_eur(rate)} statt zuletzt {format_eur(last)} "
                               f"({deviation:+.0%}, erlaubt sind ±{cfg['max_price_deviation']:.0%}).")

        else:
            details.append(f"Regel {hit} greift.")

    return details
