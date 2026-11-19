"""
Format governance decisions as German chat messages.

format_for_chat(governance)  -> message after a decision/review
format_escalation(payload)   -> question for the human (interrupt payload)

Confidence is shown as votes (e.g. 8/10), not as a percentage:
it is a count of agreeing samples, not a probability.
"""

import json
from typing import Any


RISK_LABELS = {
    "read": "Lesen",
    "draft": "Entwurf",
    "submit": "Buchung",
    "payment": "Zahlung",
}

RULE_LABELS = {
    "new_supplier": "neuer Lieferant",
    "amount_over_limit": "Betrag über dem Limit",
    "price_deviation": "Preisabweichung zum letzten Einkauf",
}

LEVEL_LABELS = {
    "L1": "jede Änderung braucht eine Freigabe",
    "L2": "Konfidenz unter der Schwelle",
    "L3": "",
}


def votes(g: dict[str, Any]) -> str | None:
    """'8/10' from the governance record."""

    n = g.get("n_samples")
    distribution = g.get("distribution") or []

    if not n or not distribution:
        return None

    return f"{distribution[0]['count']}/{n}"


def summarize_action(action: dict[str, Any] | None) -> str:
    """Short business summary of a prepared action."""

    if not action:
        return "keine Aktion"

    args = action.get("args") or {}
    parts = []

    if args.get("doctype"):
        parts.append(str(args["doctype"]))

    if args.get("supplier"):
        parts.append(f"Lieferant {args['supplier']}")

    if args.get("customer"):
        parts.append(f"Kunde {args['customer']}")

    items = args.get("items")
    if isinstance(items, list):
        for item in items[:3]:
            if not isinstance(item, dict):
                continue
            line = f"{item.get('qty', '?')} × {item.get('item_code', '?')}"
            if item.get("rate") is not None:
                line += f" à {item['rate']} €"
            parts.append(line)
        if len(items) > 3:
            parts.append(f"+{len(items) - 3} weitere Positionen")

    if not parts:
        compact = json.dumps(args, ensure_ascii=False, default=str)
        parts.append(compact if len(compact) <= 120 else compact[:117] + "...")

    return f"{action.get('tool', '?')}: " + ", ".join(parts)


def _confidence_line(g: dict[str, Any]) -> str:
    v = votes(g)
    risk = RISK_LABELS.get(g.get("risk"), g.get("risk") or "?")
    return f"Konfidenz {v} (Risiko: {risk})" if v else f"Risiko: {risk}"


def _escalation_reason(g: dict[str, Any]) -> str:
    rule_hits = g.get("rule_hits") or []

    if rule_hits:
        return "Regel greift: " + ", ".join(RULE_LABELS.get(r, r) for r in rule_hits)

    if g.get("decision") == "needs_human":
        return "Mir fehlen Informationen"

    if (g.get("distribution") or [{}])[0].get("key") == "INVALID":
        return "Ich konnte keine gültige Aktion vorbereiten"

    level = g.get("autonomy_level")

    if level == "L2" and g.get("threshold") is not None and g.get("conf_consistency") is not None:
        if len(g.get("distribution") or []) > 1 and \
                g["distribution"][0]["count"] == g["distribution"][1]["count"]:
            return "Zwei Varianten liegen gleichauf"
        return (f"Ich bin mir nicht sicher genug "
                f"({votes(g)}, nötig sind {g['threshold']:.0%} Übereinstimmung)")

    return LEVEL_LABELS.get(level) or "Freigabe nötig"


def format_escalation(payload: dict[str, Any]) -> str:
    """Question for the human, built from the interrupt payload."""

    lines = []

    if payload.get("type") == "needs_human":
        missing = payload.get("missing_info") or []
        lines.append("Mir fehlen Informationen: " + (", ".join(missing) or "unbekannt") + ".")
        lines.append(f"Vorschlag bisher: {summarize_action(payload.get('proposal'))}")
        lines.append("Bitte ergänze die Angaben oder brich ab.")
        return "\n".join(lines)

    options = [o for o in payload.get("options", []) if o.get("executable", True)]
    top_votes = (payload.get("options") or [{}])[0].get("votes")
    risk = RISK_LABELS.get(payload.get("risk"), payload.get("risk") or "?")

    if payload.get("rule_hits"):
        reason = "Regel greift: " + ", ".join(RULE_LABELS.get(r, r) for r in payload["rule_hits"])
    elif payload.get("autonomy_level") == "L1":
        reason = "Auf Stufe L1 braucht jede Änderung eine Freigabe"
    elif not options:
        reason = "Ich konnte keine gültige Aktion vorbereiten"
    else:
        reason = f"Ich bin mir nicht sicher genug ({top_votes} Stimmen für die beste Variante)"

    lines.append(f"Ich brauche deine Entscheidung. {reason}. Risiko: {risk}.")

    for number, option in enumerate(options, start=1):
        lines.append(f"Option {number}: {summarize_action(option['action'])} "
                     f"({option['votes']} Stimmen)")

    if payload.get("error"):
        lines.append(f"Hinweis: {payload['error']}")

    lines.append("Antworte mit „freigeben“, einer Optionsnummer, einer Korrektur oder „abbrechen“.")
    return "\n".join(lines)


def format_for_chat(
    g: dict[str, Any],
    result: dict[str, Any] | None = None
) -> str:
    """
    Message after a governance decision.

    g:      state["governance"]
    result: optional executor result, e.g. {"name": "PUR-ORD-0012"}
    """

    decision = g.get("decision")
    human = g.get("human_action")
    action = summarize_action(g.get("chosen_action") or g.get("proposal"))
    doc = f" ({result['name']})" if result and result.get("name") else ""

    if human == "reject":
        comment = g.get("human_comment")
        return "Abgebrochen, die Aktion wurde nicht ausgeführt." + (f" Grund: {comment}" if comment else "")

    if human == "provide_info":
        return "Danke, ich bereite den Schritt mit den neuen Angaben neu vor."

    if human in ("approve", "select", "edit"):
        how = {"approve": "nach deiner Freigabe",
               "select": "mit der von dir gewählten Variante",
               "edit": "mit deiner Korrektur"}[human]
        return f"Ausgeführt {how}: {action}{doc}."

    if decision == "auto":
        return f"Ausgeführt: {action}{doc}. {_confidence_line(g)}, autonom entschieden."

    if decision in ("escalate", "needs_human"):
        return f"{_escalation_reason(g)}. {_confidence_line(g)}. Vorschlag: {action}."

    return f"Status: {decision or 'unbekannt'}."
