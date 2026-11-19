"""
Normalise prepared actions into comparable fingerprints.

Two candidates with the same fingerprint describe the same
business decision and end up in the same cluster.
"""

import json
from typing import Any, Iterable


MISSING = "MISSING"
INVALID = "INVALID"


def canon(value: Any, ignore_fields: Iterable[str] = ()) -> Any:
    """
    Normalise a value recursively:
    - dicts: sorted keys, ignored and empty fields removed
    - lists: elements normalised and sorted (order-independent)
    - numbers: float rounded to two decimals (50 == 50.0)
    - strings: stripped and lower-cased
    """

    ignore = set(ignore_fields)

    if isinstance(value, dict):
        return {
            key: canon(val, ignore)
            for key, val in sorted(value.items())
            if key not in ignore and val is not None
        }

    if isinstance(value, (list, tuple)):
        items = [canon(item, ignore) for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(item, sort_keys=True)
        )

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return round(float(value), 2)

    if isinstance(value, str):
        return value.strip().lower()

    return value


def fingerprint(
    candidate: dict[str, Any],
    ignore_fields: Iterable[str] = ()
) -> str:
    """
    Return a deterministic string key for a candidate.

    Candidates reporting missing information or failing
    validation get special keys and form their own clusters.
    """

    if candidate.get("missing_info"):
        return MISSING

    if not candidate.get("valid", True):
        return INVALID

    key = {
        "tool": candidate.get("tool"),
        "args": canon(candidate.get("args", {}), ignore_fields),
    }

    return json.dumps(key, sort_keys=True, ensure_ascii=False)
