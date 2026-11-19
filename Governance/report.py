"""
Terminal report for the decision log.

    python -m Governance.report
    python -m Governance.report --level L2
    python -m Governance.report --scenario bp- --since 2026-12-01
    python -m Governance.report --include-read
    python -m Governance.report --json

Works without labels (decision, escalation and correction rates).
Accuracy, ECE and AUROC appear once records have 'correct' set.
"""

import argparse
import json
import sys
from collections import Counter
from typing import Any

from Governance.calibration import auroc, ece, reliability


FIELDS = (
    "created_at", "scenario_id", "step_id", "tool", "risk", "autonomy_level",
    "n_samples", "conf_consistency", "conf_verbal", "decision",
    "human_action", "corrected", "correct",
)

ESCALATED = ("escalate", "needs_human")
METHODS = (("conf_consistency", "Konsistenz"), ("conf_verbal", "Selbsteinschätzung"))


# ------------------------------------------------------------------ data

def fetch(level=None, scenario=None, since=None, risk=None, include_read=False):
    """Load records from Postgres (public.decision_log)."""

    from config.db_connection import db

    where, params = [], []

    if level:
        where.append("autonomy_level = %s"); params.append(level)
    if scenario:
        where.append("scenario_id LIKE %s"); params.append(scenario + "%")
    if since:
        where.append("created_at >= %s"); params.append(since)
    if risk:
        where.append("risk = %s"); params.append(risk)
    if not include_read:
        where.append("coalesce(risk, '') <> 'read'")

    query = f"SELECT {', '.join(FIELDS)} FROM public.decision_log"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at"

    rows = db.execute(query, params or None) or []
    return [dict(zip(FIELDS, row)) for row in rows]


# ------------------------------------------------------------------ metrics

def _rate(part, total):
    return part / total if total else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Rates for one group of records."""

    n = len(records)
    escalated = [r for r in records if r.get("decision") in ESCALATED]
    reviewed = [r for r in records if r.get("human_action")]
    labelled = [r for r in records if r.get("correct") is not None]
    auto_labelled = [r for r in labelled if r.get("decision") == "auto"]
    esc_reviewed = [r for r in escalated if r.get("human_action")]

    return {
        "n": n,
        "auto_rate": _rate(sum(r.get("decision") == "auto" for r in records), n),
        "escalation_rate": _rate(len(escalated), n),
        "correction_rate": _rate(sum(bool(r.get("corrected")) for r in reviewed), len(reviewed)),
        # escalations a human approved unchanged
        "unneeded_escalation_rate": _rate(
            sum(r.get("human_action") == "approve" for r in esc_reviewed), len(esc_reviewed)),
        "n_labelled": len(labelled),
        "accuracy": _rate(sum(bool(r["correct"]) for r in labelled), len(labelled)),
        # wrong actions executed without a human
        "undetected_error_rate": _rate(
            sum(not r["correct"] for r in auto_labelled), len(auto_labelled)),
        "mean_samples": (sum(r["n_samples"] for r in records if r.get("n_samples")) /
                         max(1, sum(1 for r in records if r.get("n_samples")))) if records else None,
    }


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    levels = sorted({r.get("autonomy_level") or "?" for r in records})
    risks = sorted({r.get("risk") or "?" for r in records})

    return {
        "total": summarize(records),
        "by_level": {lv: summarize([r for r in records if (r.get("autonomy_level") or "?") == lv])
                     for lv in levels},
        "by_risk": {rk: summarize([r for r in records if (r.get("risk") or "?") == rk])
                    for rk in risks},
        "decisions": dict(Counter(r.get("decision") for r in records)),
        "calibration": {
            field: {
                "bins": reliability(records, field),
                "ece": ece(records, field),
                "auroc": auroc(records, field),
            }
            for field, _ in METHODS
        },
        "confidence_distribution": dict(sorted(Counter(
            round(r["conf_consistency"], 1) for r in records
            if r.get("conf_consistency") is not None).items())),
    }


# ------------------------------------------------------------------ rendering

def _pct(value):
    return "–" if value is None else f"{value:.0%}"


def _num(value, digits=3):
    return "–" if value is None else f"{value:.{digits}f}"


def _table(headers, rows):
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)] if rows else [len(h) for h in headers]
    line = lambda cells: "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))
    out = [line(headers), line(["-" * w for w in widths])]
    out += [line(r) for r in rows]
    return "\n".join(out)


def _rate_rows(groups):
    return [
        [name, s["n"], _pct(s["auto_rate"]), _pct(s["escalation_rate"]),
         _pct(s["correction_rate"]), _pct(s["unneeded_escalation_rate"]),
         s["n_labelled"], _pct(s["accuracy"]), _pct(s["undetected_error_rate"])]
        for name, s in groups.items()
    ]


RATE_HEADERS = ["", "n", "auto", "eskaliert", "korrigiert", "unnötig esk.",
                "gelabelt", "korrekt", "unentdeckt falsch"]


def render(report: dict[str, Any], filters: str = "") -> str:
    out = []
    total = report["total"]

    out.append("=" * 72)
    out.append("GOVERNANCE-REPORT" + (f"  ({filters})" if filters else ""))
    out.append("=" * 72)

    if total["n"] == 0:
        out.append("Keine Entscheidungen für diese Auswahl.")
        return "\n".join(out)

    out.append(f"Entscheidungen: {total['n']}   gelabelt: {total['n_labelled']}   "
               f"Ø Samples: {_num(total['mean_samples'], 1)}")
    out.append("Verteilung: " + ", ".join(f"{k}: {v}" for k, v in report["decisions"].items()))

    out.append("\nNACH AUTONOMIESTUFE")
    out.append(_table(RATE_HEADERS, _rate_rows({"Gesamt": total, **report["by_level"]})))

    out.append("\nNACH RISIKO")
    out.append(_table(RATE_HEADERS, _rate_rows(report["by_risk"])))

    out.append("\nKONFIDENZ-VERTEILUNG (Konsistenz)")
    out.append(_table(["Konfidenz", "Anzahl"],
                      [[f"{k:.1f}", v] for k, v in report["confidence_distribution"].items()]))

    out.append("\nKALIBRIERUNG")
    if total["n_labelled"] == 0:
        out.append("Noch keine gelabelten Entscheidungen (Spalte 'correct' ist leer).")
    else:
        for field, label in METHODS:
            cal = report["calibration"][field]
            out.append(f"\n{label}:  ECE {_num(cal['ece'])}   AUROC {_num(cal['auroc'])}")
            rows = [
                [f"{b['bin_low']:.1f}–{b['bin_high']:.1f}", _num(b["mean_confidence"], 2),
                 _pct(b["accuracy"]), b["count"],
                 f"{b['accuracy'] - b['mean_confidence']:+.2f}"]
                for b in cal["bins"]
            ]
            out.append(_table(["Bin", "Ø Konfidenz", "korrekt", "n", "Abweichung"], rows)
                       if rows else "keine Werte")
        out.append("\nAbweichung < 0: überkonfident, > 0: unterkonfident.")

    out.append("\nLegende: unnötig esk. = eskaliert, aber unverändert freigegeben; "
               "unentdeckt falsch = autonom ausgeführt und falsch.")
    return "\n".join(out)


# ------------------------------------------------------------------ cli

def main(argv=None):
    parser = argparse.ArgumentParser(description="Governance-Report aus decision_log")
    parser.add_argument("--level", choices=["L1", "L2", "L3"])
    parser.add_argument("--scenario", help="Präfix der scenario_id, z. B. bp-")
    parser.add_argument("--since", help="ab Datum, z. B. 2026-12-01")
    parser.add_argument("--risk", choices=["read", "draft", "submit", "payment"])
    parser.add_argument("--include-read", action="store_true",
                        help="auch reine Lese-Aktionen einbeziehen")
    parser.add_argument("--json", action="store_true", help="Ausgabe als JSON")
    args = parser.parse_args(argv)

    records = fetch(args.level, args.scenario, args.since, args.risk, args.include_read)
    report = build_report(records)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return

    filters = ", ".join(f"{k}={v}" for k, v in vars(args).items()
                        if v and k not in ("json",))
    print(render(report, filters))


if __name__ == "__main__":
    sys.exit(main())
