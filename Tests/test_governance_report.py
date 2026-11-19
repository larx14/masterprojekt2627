"""
Tests for the terminal report (no database).
"""

from Governance.report import build_report, render


def rec(level, decision, conf, correct=None, human=None, corrected=None, risk="draft"):
    return {"autonomy_level": level, "decision": decision, "conf_consistency": conf,
            "conf_verbal": 0.9, "correct": correct, "human_action": human,
            "corrected": corrected, "risk": risk, "n_samples": 10}


RECORDS = [
    rec("L2", "auto", 1.0, True),
    rec("L2", "auto", 1.0, False),
    rec("L2", "escalate", 0.6, False, "select", True),
    rec("L2", "escalate", 0.7, True, "approve", False),
    rec("L1", "escalate", 1.0, None, "approve", False, risk="submit"),
]


def test_rates_without_and_with_labels():
    r = build_report(RECORDS)
    l2 = r["by_level"]["L2"]
    assert l2["n"] == 4
    assert l2["auto_rate"] == 0.5
    assert l2["escalation_rate"] == 0.5
    assert l2["correction_rate"] == 0.5
    assert l2["unneeded_escalation_rate"] == 0.5
    assert l2["accuracy"] == 0.5
    assert l2["undetected_error_rate"] == 0.5
    assert r["by_level"]["L1"]["n_labelled"] == 0
    assert r["calibration"]["conf_consistency"]["ece"] is not None


def test_render_contains_sections():
    text = render(build_report(RECORDS))
    for part in ("NACH AUTONOMIESTUFE", "NACH RISIKO", "KALIBRIERUNG", "ECE", "Konsistenz"):
        assert part in text


def test_render_without_labels_and_empty():
    unlabelled = [{**r, "correct": None} for r in RECORDS]
    assert "Noch keine gelabelten" in render(build_report(unlabelled))
    assert "Keine Entscheidungen" in render(build_report([]))
