"""
Cluster sampled candidates and compute confidence scores.

Stage 1 of arXiv 2411.02454: confidence = share of the largest
cluster (self-consistency). The LLM's verbalised confidence is
kept as a second signal for the calibration comparison.
"""

from collections import defaultdict
from statistics import mean
from typing import Any, Iterable

from Governance.fingerprint import fingerprint


def score(
    candidates: list[dict[str, Any]],
    ignore_fields: Iterable[str] = ()
) -> dict[str, Any]:
    """
    Group candidates by fingerprint and score the winning cluster.
    """

    if not candidates:
        raise ValueError("At least one candidate is required.")

    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for candidate in candidates:
        clusters[fingerprint(candidate, ignore_fields)].append(candidate)

    # Stable ranking: size first, then first appearance.
    order = {key: index for index, key in enumerate(clusters)}
    ranked = sorted(
        clusters.items(),
        key=lambda item: (-len(item[1]), order[item[0]])
    )

    n = len(candidates)
    winner_key, winner = ranked[0]

    verbal = [
        c["confidence"]
        for c in winner
        if isinstance(c.get("confidence"), (int, float))
        and not isinstance(c.get("confidence"), bool)
    ]

    tie = len(ranked) > 1 and len(ranked[1][1]) == len(winner)

    return {
        "winner_key": winner_key,
        "representative": winner[0],
        "conf_consistency": len(winner) / n,
        "conf_verbal": mean(verbal) if verbal else None,
        "tie": tie,
        "n": n,
        "n_clusters": len(ranked),
        "distribution": [
            {"key": key, "count": len(members)}
            for key, members in ranked
        ],
        "clusters": [
            {
                "key": key,
                "count": len(members),
                "representative": members[0],
            }
            for key, members in ranked
        ],
    }
