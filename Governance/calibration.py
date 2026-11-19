"""
Evaluation: calibration curve, ECE and AUROC.

Input: decision log records with a confidence field
(conf_consistency or conf_verbal) and a boolean 'correct'.
Pure functions; fetch_records() reads from Postgres.
"""

from typing import Any


def _pairs(records, conf_field):
    return [
        (float(r[conf_field]), bool(r["correct"]))
        for r in records
        if r.get(conf_field) is not None and r.get("correct") is not None
    ]


def reliability(records: list[dict[str, Any]], conf_field="conf_consistency", n_bins=10):
    """
    Return one entry per non-empty bin:
    {bin_low, bin_high, mean_confidence, accuracy, count}
    """

    pairs = _pairs(records, conf_field)
    bins = []

    for b in range(n_bins):
        low, high = b / n_bins, (b + 1) / n_bins
        members = [
            (c, ok) for c, ok in pairs
            if low <= c < high or (b == n_bins - 1 and c == high)
        ]
        if members:
            bins.append({
                "bin_low": low,
                "bin_high": high,
                "mean_confidence": sum(c for c, _ in members) / len(members),
                "accuracy": sum(ok for _, ok in members) / len(members),
                "count": len(members),
            })

    return bins


def ece(records, conf_field="conf_consistency", n_bins=10) -> float | None:
    """Expected Calibration Error (lower is better)."""

    bins = reliability(records, conf_field, n_bins)
    total = sum(b["count"] for b in bins)

    if total == 0:
        return None

    return sum(
        b["count"] / total * abs(b["accuracy"] - b["mean_confidence"])
        for b in bins
    )


def auroc(records, conf_field="conf_consistency") -> float | None:
    """
    Probability that a correct decision gets a higher confidence
    than a wrong one (ties count half). None if only one class.
    """

    pairs = _pairs(records, conf_field)
    pos = [c for c, ok in pairs if ok]
    neg = [c for c, ok in pairs if not ok]

    if not pos or not neg:
        return None

    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0
        for p in pos for n in neg
    )

    return wins / (len(pos) * len(neg))


def fetch_records(scenario_prefix: str | None = None) -> list[dict[str, Any]]:
    """Load labelled records from Postgres (see Governance.report.fetch)."""

    from Governance.report import fetch

    return [r for r in fetch(scenario=scenario_prefix, include_read=True)
            if r.get("correct") is not None]
