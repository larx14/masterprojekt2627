"""
Manueller Test, Schritt 1: die Governance-Bausteine einzeln.

Prüft Risiko, harte Regeln, Fingerprint/Konfidenz und die
Entscheidungslogik (policy.decide) mit festen Beispielen.
Kein LLM, kein ERPNext, keine Datenbank.

Ausführen im Repo-Root (venv aktiv):
    python Tests/manual/governance_schritt1_bausteine.py

Jede Zeile zeigt: OK/FEHLER | Fall | erwartet | tatsächlich
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Governance.config import get_config
from Governance.confidence import score
from Governance.fingerprint import INVALID, MISSING, fingerprint
from Governance.policy import decide
from Governance.risk import classify_risk
from Governance.rules import check_rules


cfg = get_config()
fehler = 0


def check(fall, erwartet, tatsaechlich):
    global fehler
    ok = erwartet == tatsaechlich
    fehler += not ok
    print(f"  {'OK    ' if ok else 'FEHLER'} | {fall:45} | erwartet {erwartet!r:24} | ist {tatsaechlich!r}")


def po(supplier="Mühle Schmidt", qty=50, rate=0.8, **extra):
    return {"tool": "create_purchase_order",
            "args": {"supplier": supplier,
                     "items": [{"item_code": "MEHL-550", "qty": qty, "rate": rate}]},
            "missing_info": [], "valid": True, "confidence": 0.9, **extra}


# ---------------------------------------------------------------
print("\nA) Risiko (risk.classify_risk)")
check("get_list",                      "read",    classify_risk({"name": "get_list"}, {}))
check("create_purchase_order",         "draft",   classify_risk({"name": "create_purchase_order"}, {}))
check("insert mit docstatus 1",        "submit",  classify_risk({"name": "insert_doc"}, {"docstatus": 1}))
check("submit_purchase_order",         "submit",  classify_risk({"name": "submit_purchase_order"}, {}))
check("Doctype Payment Entry",         "payment", classify_risk({"name": "insert_doc"}, {"doctype": "Payment Entry"}))
check("explizites risk im Tool gewinnt", "submit", classify_risk({"name": "get_x", "risk": "submit"}, {}))

# ---------------------------------------------------------------
print("\nB) Harte Regeln (rules.check_rules)  [Limit 1000 €, Preisabw. 15 %]")
r = cfg["rules"]
facts = {"known_suppliers": ["Mühle Schmidt"], "last_prices": {"MEHL-550": 0.80}}
check("normale PO (40 €)",             [],                      check_rules(po(), "draft", facts, r))
check("neuer Lieferant",               ["new_supplier"],        check_rules(po(supplier="Neu GmbH"), "draft", facts, r))
check("1500 x 0,80 = 1200 €",          ["amount_over_limit"],   check_rules(po(qty=1500), "draft", facts, r))
check("genau 1000 € (nicht drüber)",   [],                      check_rules(po(qty=1250), "draft", facts, r))
check("Preis 0,95 statt 0,80 (+19 %)", ["price_deviation"],     check_rules(po(rate=0.95), "draft", facts, r))
check("Preis 0,90 statt 0,80 (+12,5 %)", [],                    check_rules(po(rate=0.90), "draft", facts, r))
check("read wird nie blockiert",       [],                      check_rules(po(supplier="Neu GmbH", qty=5000), "read", facts, r))
check("ohne facts feuert nichts",      [],                      check_rules(po(supplier="Neu GmbH"), "draft", {}, r))
check("mehrere Regeln gleichzeitig",   ["new_supplier", "amount_over_limit"],
      check_rules(po(supplier="Neu GmbH", qty=1500), "draft", facts, r))

# ---------------------------------------------------------------
print("\nC) Fingerprint und Konfidenz (fingerprint / confidence.score)")
ign = cfg["ignore_fields"]
check("nur 'reason' anders -> gleich",      True,  fingerprint(po(reason="a"), ign) == fingerprint(po(reason="b"), ign))
check("Groß-/Kleinschreibung egal",         True,  fingerprint(po(), ign) == fingerprint(po(supplier=" mühle schmidt "), ign))
check("50 == 50.0",                         True,  fingerprint(po(qty=50), ign) == fingerprint(po(qty=50.0), ign))
check("anderer Lieferant -> verschieden",   False, fingerprint(po(), ign) == fingerprint(po(supplier="Bio-Mühle"), ign))
check("missing_info -> MISSING",            MISSING, fingerprint(po(missing_info=["supplier"]), ign))
check("valid False -> INVALID",             INVALID, fingerprint(po(valid=False), ign))

s = score([po()] * 8 + [po(supplier="Bio-Mühle")] * 2, ign)
check("8 + 2 -> Konfidenz",                 0.8, s["conf_consistency"])
check("8 + 2 -> Cluster",                   2,   s["n_clusters"])
s = score([po()] * 5 + [po(supplier="Bio-Mühle")] * 5, ign)
check("5 + 5 -> Gleichstand",               True, s["tie"])

# ---------------------------------------------------------------
print("\nD) Entscheidung (policy.decide)  [draft 0.6 | submit 0.8 | payment immer]")


def sc(conf, n=10, clusters=2, winner="A", tie=False):
    return {"conf_consistency": conf, "n": n, "n_clusters": clusters,
            "winner_key": winner, "tie": tie}


faelle = [
    # Fall,                         scored,                    Risiko,   Regeln,           Stufe, erwartet
    ("read immer auto",             sc(0.3),                   "read",   [],               "L2", "auto"),
    ("uneinig, n=5 -> nachsampeln", sc(0.6, n=5),              "draft",  [],               "L2", "more_samples"),
    ("einig, n=5 -> kein Nachsampeln", sc(1.0, n=5, clusters=1), "draft", [],              "L2", "auto"),
    ("Mehrheit fehlende Infos",     sc(0.8, winner=MISSING),   "draft",  [],               "L2", "needs_human"),
    ("Mehrheit ungültig",           sc(0.8, winner=INVALID),   "draft",  [],               "L2", "escalate"),
    ("harte Regel auf L3",          sc(1.0, clusters=1),       "draft",  ["new_supplier"], "L3", "escalate"),
    ("L1: 10/10 trotzdem Freigabe", sc(1.0, clusters=1),       "draft",  [],               "L1", "escalate"),
    ("L3: 5/10 trotzdem auto",      sc(0.5),                   "submit", [],               "L3", "auto"),
    ("L2 Gleichstand",              sc(0.5, tie=True),         "draft",  [],               "L2", "escalate"),
    ("L2 draft 0.6 = Schwelle",     sc(0.6),                   "draft",  [],               "L2", "auto"),
    ("L2 draft 0.5 < Schwelle",     sc(0.5),                   "draft",  [],               "L2", "escalate"),
    ("L2 submit 0.8 = Schwelle",    sc(0.8),                   "submit", [],               "L2", "auto"),
    ("L2 submit 0.7 < Schwelle",    sc(0.7),                   "submit", [],               "L2", "escalate"),
    ("L2 payment 10/10",            sc(1.0, clusters=1),       "payment", [],              "L2", "escalate"),
]

for fall, scored, risk, hits, level, erwartet in faelle:
    decision, reason, _ = decide(scored, risk, hits, level, cfg)
    check(fall, erwartet, decision)

print(f"\n{'Alles OK.' if fehler == 0 else f'{fehler} FEHLER.'}\n")
sys.exit(1 if fehler else 0)
