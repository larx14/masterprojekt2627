"""
Manueller Test, Schritt 2: Gate + Human Review im Mini-Graphen.

Ein Fake-Preparer liefert feste Kandidaten (statt LLM-Samples),
dann laufen der echte governance_gate und human_review.
Bei einer Eskalation fragt das Skript DICH im Terminal.
Der Executor ist ein Fake und schreibt nichts ins ERP.

Ausführen im Repo-Root (venv aktiv):
    python Tests/manual/governance_schritt2_graph.py              -> Menü
    python Tests/manual/governance_schritt2_graph.py 2            -> Szenario 2 auf L2
    python Tests/manual/governance_schritt2_graph.py 1 --level L1 -> Szenario 1 auf L1
    python Tests/manual/governance_schritt2_graph.py 1 --db       -> Log in die echte Postgres-DB

Ohne --db landet das Decision-Log nur im Speicher und wird am Ende angezeigt.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from Agent.nodes.governance_gate_node import governance_gate, route_after_governance
from Agent.nodes.human_review_node import human_review, route_after_review
from Agent.state import PlanningState
from Governance import decision_log
from Governance.channels import EscalationChannel, run_with_escalation
from Governance.chat_format import RISK_LABELS, RULE_LABELS, format_escalation, format_for_chat
from Governance.config import get_config
from Governance.state_fields import GovernanceFields


class State(PlanningState, GovernanceFields, total=False):
    pass


# ---------------------------------------------------------------- Bausteine

def po(supplier="Mühle Schmidt", qty=50, rate=0.8, missing=None):
    return {"tool": "create_purchase_order",
            "args": {"supplier": supplier,
                     "items": [{"item_code": "MEHL-550", "qty": qty, "rate": rate}]},
            "missing_info": missing or [], "valid": True,
            "confidence": 0.9, "reason": "Mehlbestand niedrig"}


def payment(amount=400):
    return {"tool": "create_payment_entry",
            "args": {"party": "Mühle Schmidt", "paid_amount": amount},
            "missing_info": [], "valid": True, "confidence": 0.95, "reason": "Rechnung fällig"}


def tool(name, risk):
    return [{"name": name, "risk": risk, "parameters": {}}]


FACTS = {"known_suppliers": ["Mühle Schmidt", "Bio-Mühle"],
         "last_prices": {"MEHL-550": 0.80}}

# runden = eine Kandidatenliste pro Preparer-Aufruf
SZENARIEN = {
    1: dict(name="Einig: 5x dieselbe PO",
            erwartung="L2: auto | L1: Freigabe | L3: auto",
            tools=tool("create_purchase_order", "draft"),
            runden=[[po()] * 5]),
    2: dict(name="Uneinig 3/2 -> nachsampeln -> 6/10 bei submit",
            erwartung="L2: 2. Preparer-Runde, dann Eskalation (0.6 < 0.8), 2 Optionen",
            tools=tool("create_purchase_order", "submit"),
            runden=[[po()] * 3 + [po(supplier="Bio-Mühle")] * 2] * 2),
    3: dict(name="Gleichstand 5/5",
            erwartung="L2: nachsampeln, dann Eskalation wegen Gleichstand",
            tools=tool("create_purchase_order", "draft"),
            runden=[[po()] * 3 + [po(supplier="Bio-Mühle")] * 2,
                    [po()] * 2 + [po(supplier="Bio-Mühle")] * 3]),
    4: dict(name="Fehlende Infos (Lieferant unklar)",
            erwartung="needs_human -> 'info {\"supplier\": \"Mühle Schmidt\"}' -> neu vorbereitet -> auto",
            tools=tool("create_purchase_order", "draft"),
            runden=[[po(supplier=None, missing=["supplier"])] * 5, [po()] * 5]),
    5: dict(name="Neuer Lieferant (harte Regel)",
            erwartung="Eskalation auf JEDER Stufe, auch L3",
            tools=tool("create_purchase_order", "draft"),
            runden=[[po(supplier="Neu GmbH")] * 5]),
    6: dict(name="Betrag 1200 € (harte Regel)",
            erwartung="Eskalation auf jeder Stufe (amount_over_limit)",
            tools=tool("create_purchase_order", "draft"),
            runden=[[po(qty=1500)] * 5]),
    7: dict(name="Preis +19 % zum letzten Einkauf (harte Regel)",
            erwartung="Eskalation auf jeder Stufe (price_deviation)",
            tools=tool("create_purchase_order", "draft"),
            runden=[[po(rate=0.95)] * 5]),
    8: dict(name="Zahlung 400 €, 5/5 einig",
            erwartung="L2: Eskalation (payment immer) | L3: auto",
            tools=tool("create_payment_entry", "payment"),
            runden=[[payment()] * 5]),
}


# ---------------------------------------------------------------- Kanal

def _value(text):
    """'80' -> 80, '0.8' -> 0.8, sonst Text."""
    text = text.strip().strip('"\'')
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            pass
    return text


def parse_fields(text, missing):
    """
    Liest Eingaben wie:
      supplier=Mühle Schmidt, qty=80   (oder supplier: Mühle Schmidt)
      {"supplier": "Mühle Schmidt"}   (auch mit Word-/Handy-Anführungszeichen)
      Mühle Schmidt                   (nur wenn genau ein Feld fehlt)
    Gibt {} zurück, wenn nichts Brauchbares drinsteht.
    """
    text = text.strip()
    if not text:
        return {}

    if text.startswith("{"):
        cleaned = (text.replace("\u201c", '"').replace("\u201d", '"')
                       .replace("\u201e", '"').replace("'", '"'))
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    sep_char = "=" if "=" in text else (":" if ":" in text else None)
    if sep_char:
        data = {}
        for part in text.split(","):
            key, sep, value = part.partition(sep_char)
            if not sep or not key.strip():
                return {}
            data[key.strip()] = _value(value)
        return data

    if len(missing) == 1:
        return {missing[0]: _value(text)}

    return {}


# ---------------------------------------------------------------- Diagnose

def _fmt(value):
    if value is None or value == "" or value == []:
        return "(leer)"
    return value


def _explain(payload, threshold):
    """Deutscher Grund, warum nicht autonom ausgeführt wurde."""
    options = payload.get("options") or []
    top = options[0] if options else {}
    votes = top.get("votes", "?")
    conf = payload.get("confidence")
    risk = payload.get("risk")
    level = payload.get("autonomy_level")

    if payload.get("type") == "needs_human":
        return (f"Die Mehrheit der Samples ({votes}) meldet fehlende Informationen: "
                f"{', '.join(payload.get('missing_info') or []) or 'unbekannt'}.")
    if payload.get("rule_hits"):
        names = ", ".join(RULE_LABELS.get(r, r) for r in payload["rule_hits"])
        return f"Harte Regel greift ({names}). Gilt auf jeder Stufe, egal wie hoch die Konfidenz ist."
    if level == "L1":
        return "Stufe L1: Jede schreibende Aktion braucht eine Freigabe, egal wie hoch die Konfidenz ist."
    if top.get("key") == "INVALID":
        return f"Die Mehrheit der Samples ({votes}) hat keine gültige Aktion erzeugt."
    if len(options) > 1 and options[0].get("votes") == options[1].get("votes"):
        return f"Gleichstand zwischen den beiden besten Varianten ({options[0]['votes']} zu {options[1]['votes']})."
    if risk == "payment":
        return "Zahlungen werden auf L2 immer eskaliert (Schwelle 1.01 ist nicht erreichbar)."
    if conf is not None and threshold is not None:
        return (f"Konfidenz {conf:.2f} ({votes}) liegt unter der Schwelle {threshold:.2f} "
                f"für Risiko '{risk}'.")
    return payload.get("reason") or "unbekannt"


def show_details(payload):
    risk = payload.get("risk")
    level = payload.get("autonomy_level")
    threshold = get_config()["thresholds"].get(risk) if level == "L2" else None
    options = payload.get("options") or []
    conf = payload.get("confidence")

    print("\n--- PROBLEM " + "-" * 52)
    print(f"  Entscheidung : {payload.get('type')}")
    print(f"  Grund        : {_explain(payload, threshold)}")
    print(f"  Konfidenz    : {options[0]['votes'] if options else '?'}"
          + (f" = {conf:.2f}" if isinstance(conf, (int, float)) else ""))
    print(f"  Schwelle     : " + (f"{threshold:.2f} ({risk}, Stufe L2)" if threshold is not None
                                  else f"keine (Stufe {level})"))
    print(f"  Risiko       : {RISK_LABELS.get(risk, risk)} ({risk})")
    print(f"  Regeln       : " + (", ".join(RULE_LABELS.get(r, r) for r in payload.get("rule_hits") or [])
                                  or "keine"))
    if payload.get("missing_info"):
        print(f"  Fehlt        : {', '.join(payload['missing_info'])}")
    if payload.get("error"):
        print(f"  Letzte Eingabe ungültig: {payload['error']}")

    # Welche Argumente unterscheiden sich zwischen den Optionen?
    all_args = [o["action"].get("args") or {} for o in options]
    keys = sorted({k for a in all_args for k in a})
    diff = [k for k in keys if len({json.dumps(a.get(k), sort_keys=True, default=str) for a in all_args}) > 1]

    print("\n--- OPTIONEN " + "-" * 51)
    if diff:
        print(f"  Unterschied zwischen den Optionen: {', '.join(diff)}")

    nr = 0
    for o in options:
        a = o["action"]
        if o.get("executable", True):
            nr += 1
            head = f"  [{nr}] {o['votes']} Stimmen"
        else:
            kind = "unvollständig" if o.get("key") == "MISSING" else "ungültig"
            head = f"  [–] {o['votes']} Stimmen  ({kind}, nicht wählbar)"
        print(head)
        print(f"      tool: {a.get('tool')}")
        total = 0.0
        for k, v in (a.get("args") or {}).items():
            mark = "  <- anders" if k in diff else ""
            if k == "items" and isinstance(v, list):
                print(f"      items:{mark}")
                for it in v:
                    if isinstance(it, dict) and isinstance(it.get("qty"), (int, float)) and isinstance(it.get("rate"), (int, float)):
                        line = it["qty"] * it["rate"]
                        total += line
                        print(f"        - {it.get('item_code')}: {it['qty']} × {it['rate']} € = {line:.2f} €")
                    else:
                        print(f"        - {it}")
            else:
                print(f"      {k}: {_fmt(v)}{mark}")
        if total:
            print(f"      Summe: {total:.2f} €")
        if o.get("missing_info"):
            print(f"      fehlt: {', '.join(o['missing_info'])}")
        if a.get("reason"):
            print(f"      Begründung LLM: {a['reason']}")
    print("-" * 64)


class TerminalChannel(EscalationChannel):
    """Fragt im Terminal, kann alle Antworttypen des human_review-Nodes."""

    HILFE = """  Eingaben:
    ok                              -> approve (Vorschlag freigeben)
    1 / 2 / 3                       -> select (Option Nummer x)
    edit supplier=Bio-Mühle         -> edit (Argument im Vorschlag überschreiben)
    info supplier=Mühle Schmidt     -> provide_info (fehlende Infos nachreichen)
    info Mühle Schmidt              -> geht auch, wenn genau ein Feld fehlt
    abbrechen [Grund]               -> reject
    json                            -> rohes Payload anzeigen
  Mehrere Felder mit Komma: edit supplier=Bio-Mühle, transaction_date=2026-12-01
  JSON geht auch: info {"supplier": "Mühle Schmidt"}"""

    KURZHILFE = ("  Antwort: ok | 1/2/3 | edit feld=wert | info feld=wert | "
                 "abbrechen [Grund] | json | hilfe")

    def ask(self, payload):
        print("\n" + "=" * 64)
        print("ESKALATION – Details für dich (Entwickler-Sicht)")
        show_details(payload)

        # Direkt über der Eingabe: das, was der Nutzer im Chat bekäme.
        print("\n--- CHAT-NACHRICHT an den Nutzer " + "-" * 31)
        for line in format_escalation(payload).splitlines():
            print(f"  {line}")
        print("-" * 64)
        print(self.KURZHILFE)

        executable = [o for o in payload.get("options", []) if o.get("executable", True)]

        while True:
            raw = input("> ").strip()
            cmd, _, rest = raw.partition(" ")

            if cmd in ("ok", "freigeben", "approve"):
                return {"action": "approve"}
            if cmd.isdigit() and 1 <= int(cmd) <= len(executable):
                return {"action": "select", "index": executable[int(cmd) - 1]["index"]}
            if cmd in ("abbrechen", "reject"):
                return {"action": "reject", "comment": rest or None}
            if cmd in ("edit", "info"):
                missing = payload.get("missing_info") or []
                data = parse_fields(rest, missing if cmd == "info" else [])
                if not data:
                    print(f"  Konnte {rest!r} nicht lesen.")
                    if cmd == "info" and missing:
                        print(f"  Fehlende Felder: {', '.join(missing)}")
                        print(f"  Beispiel: info {missing[0]}=Mühle Schmidt")
                    else:
                        print("  Beispiel: edit supplier=Bio-Mühle")
                    continue
                print(f"  -> verstanden als {json.dumps(data, ensure_ascii=False)}")
                if cmd == "info":
                    return {"action": "provide_info", "info": data}
                args = {**(payload.get("proposal") or {}).get("args", {}), **data}
                return {"action": "edit", "args": args}
            if cmd in ("hilfe", "help", "?"):
                print(self.HILFE)
                continue
            if cmd == "json":
                print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
                continue
            print("  Unbekannte Eingabe.")


# ---------------------------------------------------------------- Graph

def build(runden):
    runden = list(runden)

    def fake_preparer(state):
        neu = runden.pop(0) if len(runden) > 1 else runden[0]
        print(f"\n[Preparer] liefert {len(neu)} Kandidaten "
              f"(bisher {len(state.get('candidates') or [])})")
        return {"candidates": (state.get("candidates") or []) + neu,
                "status": "action_prepared"}

    def fake_executor(state):
        a = state["prepared_action"]
        print(f"\n[Executor] WÜRDE AUSFÜHREN: {a.get('tool')} {json.dumps(a.get('args'), ensure_ascii=False)}")
        return {"status": "executed", "candidates": []}

    b = StateGraph(State)
    b.add_node("action_preparer", fake_preparer)
    b.add_node("governance_gate", governance_gate)
    b.add_node("human_review", human_review)
    b.add_node("executor", fake_executor)

    b.add_edge(START, "action_preparer")
    b.add_edge("action_preparer", "governance_gate")
    b.add_conditional_edges("governance_gate", route_after_governance, {
        "sample": "action_preparer", "execute": "executor",
        "review": "human_review", "stop": END})
    b.add_conditional_edges("human_review", route_after_review, {
        "execute": "executor", "prepare": "action_preparer", "stop": END})
    b.add_edge("executor", END)

    return b.compile(checkpointer=InMemorySaver())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("szenario", nargs="?", type=int)
    p.add_argument("--level", default="L2", choices=["L1", "L2", "L3"])
    p.add_argument("--db", action="store_true", help="Decision-Log in Postgres schreiben")
    a = p.parse_args()

    if a.szenario not in SZENARIEN:
        for nr, s in SZENARIEN.items():
            print(f"  {nr}  {s['name']}")
        a.szenario = int(input("Szenario-Nr.: "))

    s = SZENARIEN[a.szenario]
    print(f"\n### Szenario {a.szenario}: {s['name']}  |  Stufe {a.level}")
    print(f"### Erwartung: {s['erwartung']}")

    memory = None
    if not a.db:
        memory = decision_log.MemoryBackend()
        decision_log.set_backend(memory)

    plan = [{"id": "step_1", "tool": s["tools"][0]["name"], "description": s["name"],
             "depends_on": [], "execution_condition": None, "reason": "manueller Test",
             "status": "pending"}]
    state = {"plan": plan, "current_step": 0, "plan_valid": True,
             "available_tools": s["tools"], "autonomy_level": a.level,
             "trigger": "manual", "scenario_id": f"manual_{a.szenario}",
             "facts": dict(FACTS), "history": []}
    config = {"configurable": {"thread_id": f"manual-{a.szenario}-{a.level}"}}

    result = run_with_escalation(build(s["runden"]), state, config, lambda _: TerminalChannel())

    print("\n" + "=" * 64)
    print(f"ENDSTATUS: {result.get('status')}")
    if result.get("governance"):
        print(f"Chat-Antwort: {format_for_chat(result['governance'])}")

    if memory is not None:
        print("\nDecision-Log (nur im Speicher):")
        for rec in memory.records.values():
            print(json.dumps({k: rec.get(k) for k in (
                "decision", "reason", "risk", "autonomy_level", "n_samples",
                "conf_consistency", "conf_verbal", "threshold", "rule_hits",
                "human_action", "corrected", "final_action")},
                ensure_ascii=False, indent=2))
    else:
        print("\nDecision-Log wurde in public.decision_log geschrieben.")


if __name__ == "__main__":
    main()
