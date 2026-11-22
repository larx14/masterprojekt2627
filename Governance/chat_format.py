"""
Format governance decisions as German chat messages.

format_for_chat(governance)  -> message after a decision/review
format_escalation(payload)   -> question for the human (interrupt payload)

Confidence is shown as votes (e.g. 8/10), not as a percentage:
it is a count of agreeing samples, not a probability.
"""

import json
from typing import Any

from Governance.rules import action_amount, format_eur


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


def _num(value: Any) -> str:
    """50 -> '50', 2.5 -> '2,5'."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", ",")


def summarize_action(
    action: dict[str, Any] | None,
    with_tool: bool = True,
    with_total: bool = True,
) -> str:
    """Short business summary of a prepared action, incl. total amount."""

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
            line = f"{_num(item.get('qty', '?'))} × {item.get('item_code', '?')}"
            if isinstance(item.get("rate"), (int, float)):
                line += f" à {format_eur(item['rate'])}"
            parts.append(line)
        if len(items) > 3:
            parts.append(f"+{len(items) - 3} weitere Positionen")

    if not parts and args:
        compact = json.dumps(args, ensure_ascii=False, default=str)
        parts.append(compact if len(compact) <= 120 else compact[:117] + "...")

    if with_total:
        total = action_amount(action)
        if total is not None:
            parts.append(f"Summe {format_eur(total)}")

    text = ", ".join(parts)

    if with_tool:
        return f"{action.get('tool', '?')}: {text}" if text else str(action.get("tool", "?"))

    return text


def _diff_keys(actions: list[dict[str, Any]]) -> list[str]:
    """Argument names whose values differ between the actions ('tool' if the tool differs)."""

    def dump(value):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

    keys = []
    if len({str(a.get("tool")) for a in actions}) > 1:
        keys.append("tool")

    names = []
    for a in actions:
        for key in (a.get("args") or {}):
            if key not in names:
                names.append(key)

    for key in names:
        if len({dump((a.get("args") or {}).get(key)) for a in actions}) > 1:
            keys.append(key)

    return keys


def _subset(action: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    args = action.get("args") or {}
    return {"tool": action.get("tool"), "args": {k: args[k] for k in keys if k in args}}


def _confidence_line(g: dict[str, Any]) -> str:
    v = votes(g)
    risk = RISK_LABELS.get(g.get("risk"), g.get("risk") or "?")
    return f"Konfidenz {v} (Risiko: {risk})" if v else f"Risiko: {risk}"


def _escalation_reason(g: dict[str, Any]) -> str:
    """Reason for an escalation, from the governance record (after the decision)."""

    rule_hits = g.get("rule_hits") or []

    if g.get("rule_details"):
        return "Freigabe nötig: " + " ".join(g["rule_details"]).rstrip(".")

    if rule_hits:
        return "Regel greift: " + ", ".join(RULE_LABELS.get(r, r) for r in rule_hits)

    if g.get("decision") == "needs_human":
        return "Mir fehlen Informationen"

    distribution = g.get("distribution") or []

    if distribution and distribution[0].get("key") == "INVALID":
        return "Ich konnte keine gültige Aktion vorbereiten"

    level = g.get("autonomy_level")

    if level == "L2" and g.get("risk") == "payment":
        return "Zahlungen brauchen immer eine Freigabe"

    if level == "L2" and g.get("threshold") is not None and g.get("conf_consistency") is not None:
        if len(distribution) > 1 and distribution[0]["count"] == distribution[1]["count"]:
            return "Zwei Varianten liegen gleichauf"
        return (f"Ich bin mir nicht sicher genug "
                f"({votes(g)}, nötig sind {g['threshold']:.0%} Übereinstimmung)")

    return LEVEL_LABELS.get(level) or "Freigabe nötig"


def _sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else text + "."


def format_escalation(payload: dict[str, Any]) -> str:
    """Question for the human, built from the interrupt payload."""

    lines = []

    if payload.get("step_description"):
        lines.append(f"Schritt: {payload['step_description']}")

    # Missing information: ask a concrete question.
    if payload.get("type") == "needs_human":
        missing = payload.get("missing_info") or []
        lines.append("Mir fehlen Angaben für diesen Schritt: " + (", ".join(missing) or "unbekannt") + ".")
        lines.append(f"Bisheriger Vorschlag: {summarize_action(payload.get('proposal'))}")
        example = missing[0] if missing else "Feld"
        lines.append(f"Bitte antworte mit den fehlenden Angaben, z. B. „{example}: <Wert>“, "
                     f"oder mit „abbrechen“.")
        return "\n".join(lines)

    options = [o for o in payload.get("options", []) if o.get("executable", True)]
    risk = RISK_LABELS.get(payload.get("risk"), payload.get("risk") or "?")
    top_votes = (payload.get("options") or [{}])[0].get("votes")

    # Why a human has to decide.
    if payload.get("rule_details"):
        reason = "Freigabe nötig: " + " ".join(payload["rule_details"])
    elif payload.get("rule_hits"):
        reason = "Regel greift: " + ", ".join(RULE_LABELS.get(r, r) for r in payload["rule_hits"])
    elif payload.get("autonomy_level") == "L1":
        reason = "Auf Stufe L1 braucht jede Änderung eine Freigabe"
    elif not options:
        reason = "Ich konnte keine gültige Aktion vorbereiten"
    elif len(options) > 1 and options[0].get("votes") == options[1].get("votes"):
        reason = f"Zwei Varianten liegen gleichauf ({options[0]['votes']} zu {options[1]['votes']} Stimmen)"
    elif payload.get("risk") == "payment":
        reason = "Zahlungen brauchen immer eine Freigabe"
    else:
        reason = f"Ich bin mir nicht sicher genug ({top_votes} Stimmen für die beste Variante)"

    lines.append(f"Ich brauche deine Entscheidung. {_sentence(reason)} Risiko: {risk}.")

    # Options: common part once, then only the differences.
    if len(options) == 1:
        o = options[0]
        lines.append(f"Vorschlag: {summarize_action(o['action'])} ({o['votes']} Stimmen)")

    elif len(options) > 1:
        actions = [o["action"] for o in options]
        diff = _diff_keys(actions)
        totals = [action_amount(a) for a in actions]
        same_total = len(set(totals)) == 1 and totals[0] is not None

        if diff:
            common = [k for k in (actions[0].get("args") or {}) if k not in diff]
            common_text = summarize_action(_subset(actions[0], common),
                                           with_tool="tool" not in diff, with_total=False)
            if same_total:
                common_text += (", " if common_text else "") + f"Summe {format_eur(totals[0])}"
            if common_text:
                lines.append(f"Gemeinsam: {common_text}")

        for number, (option, total) in enumerate(zip(options, totals), start=1):
            if diff:
                text = summarize_action(_subset(option["action"], diff),
                                        with_tool="tool" in diff, with_total=False)
                if not same_total and total is not None:
                    text += (", " if text else "") + f"Summe {format_eur(total)}"
            else:
                text = summarize_action(option["action"])
            lines.append(f"Option {number}: {text or '–'} ({option['votes']} Stimmen)")

    if payload.get("error"):
        lines.append(f"Hinweis: {payload['error']}")

    if len(options) > 1:
        lines.append("Antworte mit „freigeben“, einer Optionsnummer, einer Korrektur oder „abbrechen“.")
    else:
        lines.append("Antworte mit „freigeben“, einer Korrektur oder „abbrechen“.")

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
    # After a review the executed action can differ from the proposal (select/edit).
    executed = g.get("final_action") or g.get("chosen_action") or g.get("proposal")
    action = summarize_action(executed)
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
