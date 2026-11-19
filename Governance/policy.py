"""
Decide what happens with a scored action.

Decisions:
- auto          execute without a human
- more_samples  disagreement, sample more candidates first
- escalate      a human must approve, select or correct
- needs_human   required information is missing

Autonomy levels:
- L1 assisted:   every write action needs approval
- L2 calibrated: risk-based confidence thresholds + hard rules
- L3 autonomous: only hard rules escalate
"""

from typing import Any

from Governance.config import AUTONOMY_LEVELS
from Governance.fingerprint import INVALID, MISSING


def decide(
    scored: dict[str, Any],
    risk: str,
    rule_hits: list[str],
    level: str,
    cfg: dict[str, Any]
) -> tuple[str, str, float | None]:
    """
    Return (decision, reason, threshold).
    """

    if level not in AUTONOMY_LEVELS:
        raise ValueError(f"Unknown autonomy level '{level}'.")

    threshold = cfg["thresholds"][risk] if level == "L2" else None
    conf = scored["conf_consistency"]
    n = scored["n"]
    n_max = int(cfg["sampling"]["n_max"])

    # 1. Read-only actions are always allowed.
    if risk == "read":
        return "auto", "Read-only action.", threshold

    # 2. Adaptive sampling: disagreement -> sample more first.
    #    Done on every level so calibration data is comparable.
    if conf < 1.0 and n < n_max:
        return (
            "more_samples",
            f"{scored['n_clusters']} variants in {n} samples.",
            threshold,
        )

    # 3. Content-related special cases.
    if scored["winner_key"] == MISSING:
        return "needs_human", "Most samples report missing information.", threshold

    if scored["winner_key"] == INVALID:
        return "escalate", "Most samples produced no valid action.", threshold

    # 4. Hard rules apply on every level.
    if rule_hits:
        return "escalate", f"Hard rules triggered: {', '.join(rule_hits)}.", threshold

    # 5. Autonomy level.
    if level == "L1":
        return "escalate", "L1: every write action requires approval.", threshold

    if level == "L3":
        return "auto", "L3: autonomous execution.", threshold

    if scored["tie"]:
        return "escalate", "Tie between the two largest variants.", threshold

    if conf >= threshold:
        return "auto", f"Confidence {conf:.2f} >= threshold {threshold:.2f} ({risk}).", threshold

    return "escalate", f"Confidence {conf:.2f} < threshold {threshold:.2f} ({risk}).", threshold
