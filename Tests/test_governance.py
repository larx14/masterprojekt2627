"""
Unit tests for the governance layer (pure functions).

No LLM, ERPNext or database connection is required.
"""

import pytest

from Governance.calibration import auroc, ece, reliability
from Governance.confidence import score
from Governance.config import get_config
from Governance.fingerprint import INVALID, MISSING, canon, fingerprint
from Governance.policy import decide
from Governance.risk import classify_risk, initial_samples
from Governance.rules import check_rules


CFG = get_config()


def cand(supplier="Mühle Schmidt", qty=50, rate=0.8, **extra):
    base = {
        "tool": "create_purchase_order",
        "args": {
            "supplier": supplier,
            "items": [{"item_code": "MEHL-550", "qty": qty, "rate": rate}],
        },
        "missing_info": [],
        "valid": True,
        "confidence": 0.9,
        "reason": "test",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------- fingerprint

def test_canon_normalises_numbers_strings_and_order():
    a = {"b": 50, "a": " Mehl ", "items": [{"x": 2}, {"x": 1}]}
    b = {"items": [{"x": 1.0}, {"x": 2.0}], "a": "mehl", "b": 50.0}
    assert canon(a) == canon(b)


def test_fingerprint_ignores_free_text():
    a = cand(reason="weil A")
    b = cand(reason="weil B")
    a["args"]["remarks"] = "bitte schnell"
    ignore = CFG["ignore_fields"]
    assert fingerprint(a, ignore) == fingerprint(b, ignore)


def test_fingerprint_distinguishes_business_values():
    assert fingerprint(cand(qty=50)) != fingerprint(cand(qty=500))
    assert fingerprint(cand()) != fingerprint(cand(supplier="Bio-Mühle"))


def test_fingerprint_special_keys():
    assert fingerprint(cand(missing_info=["supplier"])) == MISSING
    assert fingerprint(cand(valid=False)) == INVALID


# ---------------------------------------------------------------- confidence

def test_score_majority_and_verbal_confidence():
    cands = [cand()] * 7 + [cand(supplier="Bio-Mühle", confidence=0.95)] * 3
    s = score(cands)
    assert s["conf_consistency"] == 0.7
    assert s["conf_verbal"] == pytest.approx(0.9)
    assert s["n_clusters"] == 2
    assert s["representative"]["args"]["supplier"] == "Mühle Schmidt"
    assert not s["tie"]


def test_score_detects_tie():
    s = score([cand()] * 5 + [cand(qty=500)] * 5)
    assert s["tie"]


def test_score_requires_candidates():
    with pytest.raises(ValueError):
        score([])


# ---------------------------------------------------------------- risk

@pytest.mark.parametrize("spec,args,expected", [
    ({"name": "x", "risk": "submit"}, {}, "submit"),
    ({"name": "get_list"}, {"doctype": "Item"}, "read"),
    ({"name": "find_supplier"}, {}, "read"),
    ({"name": "create_doc"}, {"doctype": "Purchase Order"}, "draft"),
    ({"name": "create_doc"}, {"doctype": "Purchase Order", "docstatus": 1}, "submit"),
    ({"name": "submit_doc"}, {}, "submit"),
    ({"name": "create_doc"}, {"doctype": "Payment Entry"}, "payment"),
])
def test_classify_risk(spec, args, expected):
    assert classify_risk(spec, args) == expected


def test_initial_samples():
    assert initial_samples({"name": "get_list"}, CFG) == 1
    assert initial_samples({"name": "create_doc"}, CFG) == CFG["sampling"]["n_initial"]


# ---------------------------------------------------------------- rules

RULES = {"max_amount": 1000, "max_price_deviation": 0.15, "escalate_new_supplier": True}


def test_rules_do_not_fire_without_data():
    assert check_rules(cand(), "draft", {}, RULES) == []


def test_rule_new_supplier():
    facts = {"known_suppliers": ["Mühle Schmidt"]}
    assert check_rules(cand(), "draft", facts, RULES) == []
    assert check_rules(cand(supplier="Neu GmbH"), "draft", facts, RULES) == ["new_supplier"]


def test_rule_amount_limit():
    assert check_rules(cand(qty=2000, rate=1.0), "draft", {}, RULES) == ["amount_over_limit"]


def test_rule_price_deviation():
    facts = {"last_prices": {"MEHL-550": 0.8}}
    assert check_rules(cand(rate=0.85), "draft", facts, RULES) == []
    assert check_rules(cand(rate=1.2), "draft", facts, RULES) == ["price_deviation"]


def test_rules_ignore_read_actions():
    assert check_rules(cand(qty=99999), "read", {}, RULES) == []


# ---------------------------------------------------------------- policy

def scored(conf_count, n, key="x", tie=False):
    return {"conf_consistency": conf_count / n, "n": n, "n_clusters": 2,
            "winner_key": key, "tie": tie}


def test_read_is_always_auto():
    assert decide(scored(3, 5), "read", [], "L1", CFG)[0] == "auto"


def test_adaptive_sampling_on_disagreement():
    assert decide(scored(4, 5), "draft", [], "L2", CFG)[0] == "more_samples"
    # unanimous -> no further sampling
    assert decide(scored(5, 5), "draft", [], "L2", CFG)[0] == "auto"
    # max reached -> decide
    assert decide(scored(8, 10), "draft", [], "L2", CFG)[0] == "auto"


@pytest.mark.parametrize("level,risk,count,expected", [
    ("L1", "draft", 10, "escalate"),
    ("L3", "submit", 6, "auto"),
    ("L2", "draft", 6, "auto"),       # 0.6 >= 0.6
    ("L2", "submit", 7, "escalate"),  # 0.7 < 0.8
    ("L2", "submit", 9, "auto"),
    ("L2", "payment", 10, "escalate"),
])
def test_autonomy_levels(level, risk, count, expected):
    assert decide(scored(count, 10), risk, [], level, CFG)[0] == expected


def test_hard_rules_escalate_on_every_level():
    for level in ("L2", "L3"):
        assert decide(scored(10, 10), "draft", ["new_supplier"], level, CFG)[0] == "escalate"


def test_missing_and_invalid_clusters():
    assert decide(scored(10, 10, key=MISSING), "draft", [], "L3", CFG)[0] == "needs_human"
    assert decide(scored(10, 10, key=INVALID), "draft", [], "L3", CFG)[0] == "escalate"


def test_tie_escalates_on_l2():
    assert decide(scored(5, 10, tie=True), "read", [], "L2", CFG)[0] == "auto"
    assert decide(scored(5, 10, tie=True), "draft", [], "L2", CFG)[0] == "escalate"


def test_unknown_level_raises():
    with pytest.raises(ValueError):
        decide(scored(5, 5), "draft", [], "L9", CFG)


# ---------------------------------------------------------------- calibration

def test_calibration_metrics():
    records = (
        [{"conf_consistency": 1.0, "correct": True}] * 9
        + [{"conf_consistency": 1.0, "correct": False}]
        + [{"conf_consistency": 0.5, "correct": False}] * 4
        + [{"conf_consistency": 0.5, "correct": True}] * 1
    )
    bins = reliability(records)
    assert [b["count"] for b in bins] == [5, 10]
    assert bins[1]["accuracy"] == 0.9
    assert ece(records) == pytest.approx((5 * 0.3 + 10 * 0.1) / 15)
    # 10 correct vs 5 wrong; ties count half: (9*0.5 + 9*4 + 1*4*0.5) / 50
    assert auroc(records) == pytest.approx(0.85)


def test_calibration_without_labels():
    assert ece([{"conf_consistency": 1.0}]) is None
    assert auroc([{"conf_consistency": 1.0, "correct": True}]) is None


# ---------------------------------------------------------------- chat format

from Governance.chat_format import format_escalation, format_for_chat  # noqa: E402

ACTION = {"tool": "create_purchase_order",
          "args": {"supplier": "Mühle Schmidt",
                   "items": [{"item_code": "MEHL-550", "qty": 50, "rate": 0.8}]}}


def gov(**extra):
    base = {"decision": "auto", "risk": "draft", "autonomy_level": "L2",
            "n_samples": 10, "conf_consistency": 0.9, "threshold": 0.6,
            "distribution": [{"key": "a", "count": 9}, {"key": "b", "count": 1}],
            "rule_hits": [], "chosen_action": ACTION, "proposal": ACTION}
    base.update(extra)
    return base


def test_chat_auto():
    text = format_for_chat(gov(), {"name": "PUR-ORD-0012"})
    assert "9/10" in text and "Entwurf" in text and "PUR-ORD-0012" in text
    assert "autonom" in text


def test_chat_escalation_low_confidence():
    text = format_for_chat(gov(decision="escalate", risk="submit", threshold=0.8,
                               conf_consistency=0.6,
                               distribution=[{"key": "a", "count": 6}, {"key": "b", "count": 4}]))
    assert "6/10" in text and "nicht sicher genug" in text


def test_chat_rule_and_human_actions():
    assert "neuer Lieferant" in format_for_chat(gov(decision="escalate", rule_hits=["new_supplier"]))
    assert "gewählten Variante" in format_for_chat(gov(human_action="select"))
    assert "Abgebrochen" in format_for_chat(gov(human_action="reject", human_comment="zu teuer"))


def test_escalation_question_lists_executable_options():
    payload = {"type": "escalate", "risk": "submit", "confidence": 0.6, "rule_hits": [],
               "options": [
                   {"votes": "6/10", "action": ACTION, "executable": True},
                   {"votes": "3/10", "action": {**ACTION, "args": {"supplier": "Bio-Mühle"}},
                    "executable": True},
                   {"votes": "1/10", "action": {}, "executable": False},
               ]}
    text = format_escalation(payload)
    assert "Option 1" in text and "Option 2" in text and "Option 3" not in text
    assert "50 × MEHL-550" in text and "(6/10 Stimmen)" in text


def test_escalation_question_missing_info():
    text = format_escalation({"type": "needs_human", "missing_info": ["supplier"], "proposal": ACTION})
    assert "supplier" in text and "fehlen" in text
    assert "„supplier: <Wert>“" in text


# ---------------------------------------------------------------- chat details

from Governance.rules import describe_hits, format_eur  # noqa: E402


def test_format_eur_german():
    assert format_eur(1200) == "1.200,00 €"
    assert format_eur(0.8) == "0,80 €"


def test_describe_hits_contains_values():
    rules = CFG["rules"]
    facts = {"known_suppliers": ["Mühle Schmidt"], "last_prices": {"MEHL-550": 0.80}}

    (amount,) = describe_hits(["amount_over_limit"], cand(qty=1500), facts, rules)
    assert "1.200,00 €" in amount and "1.000,00 €" in amount

    (price,) = describe_hits(["price_deviation"], cand(rate=0.95), facts, rules)
    assert "0,95 €" in price and "0,80 €" in price and "+19%" in price

    (supplier,) = describe_hits(["new_supplier"], cand(supplier="Neu GmbH"), facts, rules)
    assert "Neu GmbH" in supplier


def test_price_rule_unchanged_after_refactor():
    facts = {"last_prices": {"MEHL-550": 0.80}}
    assert check_rules(cand(rate=0.95), "draft", facts, CFG["rules"]) == ["price_deviation"]
    assert check_rules(cand(rate=0.90), "draft", facts, CFG["rules"]) == []


def test_escalation_shows_context_rule_details_and_total():
    payload = {"type": "escalate", "risk": "draft", "autonomy_level": "L2",
               "step_description": "Mehl nachbestellen",
               "rule_hits": ["amount_over_limit"],
               "rule_details": ["Betrag 1.200,00 € liegt über dem Limit von 1.000,00 €."],
               "options": [{"votes": "5/5", "executable": True,
                            "action": {**ACTION, "args": {**ACTION["args"],
                                       "items": [{"item_code": "MEHL-550", "qty": 1500, "rate": 0.8}]}}}]}
    text = format_escalation(payload)
    assert text.startswith("Schritt: Mehl nachbestellen")
    assert "1.200,00 € liegt über dem Limit" in text
    assert "Summe 1.200,00 €" in text and "0,80 €" in text


def test_escalation_options_show_only_difference():
    other = {**ACTION, "args": {**ACTION["args"], "supplier": "Bio-Mühle"}}
    payload = {"type": "escalate", "risk": "submit", "autonomy_level": "L2", "rule_hits": [],
               "options": [{"votes": "6/10", "action": ACTION, "executable": True},
                           {"votes": "4/10", "action": other, "executable": True}]}
    lines = format_escalation(payload).splitlines()
    assert any(l.startswith("Gemeinsam:") and "50 × MEHL-550" in l and "Summe 40,00 €" in l
               for l in lines)
    assert "Option 1: Lieferant Mühle Schmidt (6/10 Stimmen)" in lines
    assert "Option 2: Lieferant Bio-Mühle (4/10 Stimmen)" in lines


def test_escalation_payment_and_tie_reasons():
    base = {"type": "escalate", "autonomy_level": "L2", "rule_hits": []}
    pay = format_escalation({**base, "risk": "payment",
                             "options": [{"votes": "5/5", "action": ACTION, "executable": True}]})
    assert "Zahlungen brauchen immer eine Freigabe" in pay

    other = {**ACTION, "args": {**ACTION["args"], "supplier": "Bio-Mühle"}}
    tie = format_escalation({**base, "risk": "draft",
                             "options": [{"votes": "5/10", "action": ACTION, "executable": True},
                                         {"votes": "5/10", "action": other, "executable": True}]})
    assert "gleichauf" in tie


def test_chat_after_select_shows_executed_variant():
    other = {**ACTION, "args": {**ACTION["args"], "supplier": "Bio-Mühle"}}
    text = format_for_chat(gov(decision="escalate", human_action="select", final_action=other))
    assert "Bio-Mühle" in text and "Mühle Schmidt" not in text
