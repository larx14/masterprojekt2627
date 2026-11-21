
"""
LangGraph node: evaluator.

Verifies whether the expected ERPNext state
matches the actual state after execution.

Generic for all ERPNext doctypes.
Deterministic. No LLM call.
"""

from datetime import datetime, timezone
from typing import Any

from Agent.state import PlanningState
from Agent.tools.read_tools import run_read_tool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_verification_query(
    expected_state: dict[str, Any]
) -> dict[str, Any]:
    """
    Build an ERPNext search query from the expected state.
    """

    doctype = expected_state.get("doctype")
    identity = expected_state.get("identity")

    if not doctype:
        raise ValueError("Verification state has no doctype.")

    if not isinstance(identity, dict) or not identity:
        raise ValueError(
            "Verification state must contain a non-empty identity."
        )

    filters = [
        [field, "=", value]
        for field, value in identity.items()
    ]

    return {
        "doctype": doctype,
        "filters": filters
    }


def fetch_actual_state(
    expected_state: dict[str, Any]
) -> dict[str, Any]:
    """
    Retrieve the actual document from ERPNext.
    """

    query = build_verification_query(expected_state)

    return run_read_tool(
        "erp_search",
        query
    )


def compare_states(
    expected_state: dict[str, Any],
    actual_state: dict[str, Any]
) -> dict[str, Any]:
    """
    Compare expected and actual ERPNext values.

    Supports:
    - Create: expected_exists = True
    - Update: expected_exists = True
    - Delete: expected_exists = False
    """

    if actual_state.get("status") != "completed":
        return {
            "result": "unknown",
            "reason": "Could not retrieve actual ERPNext state.",
            "errors": actual_state.get("errors", []),
            "actual_state": actual_state,
            "differences": []
        }

    result_data = actual_state.get("result") or {}
    data = result_data.get("data")

    if not isinstance(data, list):
        return {
            "result": "unknown",
            "reason": "ERPNext returned an invalid search result.",
            "differences": []
        }

    expected_exists = expected_state.get(
        "expected_exists", True
    )

    # Check whether the document should exist.
    if not data:

        if expected_exists:
            return {
                "result": "mismatch",
                "reason": "Expected document does not exist.",
                "differences": [
                    "Document was not found in ERPNext."
                ]
            }

        return {
            "result": "verified",
            "reason": "Document does not exist as expected.",
            "differences": []
        }

    # More than one matching document is ambiguous.
    if len(data) > 1:
        return {
            "result": "mismatch",
            "reason": "Multiple matching documents found.",
            "differences": [
                f"Expected one document, found {len(data)}."
            ]
        }

    actual_document = data[0]

    # The document should no longer exist (e.g. Delete).
    if not expected_exists:
        return {
            "result": "mismatch",
            "reason": "Document still exists.",
            "differences": [
                "Expected document to be absent."
            ],
            "actual_document": actual_document
        }

    # Compare expected fields.
    expected_fields = expected_state.get(
        "expected_fields", {}
    )

    differences = []

    for field, expected_value in expected_fields.items():

        if field not in actual_document:
            differences.append({
                "field": field,
                "expected": expected_value,
                "actual": None,
                "reason": "Field missing from ERPNext response."
            })
            continue

        actual_value = actual_document[field]

        if actual_value != expected_value:
            differences.append({
                "field": field,
                "expected": expected_value,
                "actual": actual_value
            })

    if differences:
        return {
            "result": "mismatch",
            "reason": "Expected and actual values differ.",
            "differences": differences,
            "actual_document": actual_document
        }

    return {
        "result": "verified",
        "reason": "All expected fields match.",
        "differences": [],
        "actual_document": actual_document
    }


def evaluator(state: PlanningState) -> dict:
    """
    Verify the result of the executed plan step.
    """

    expected_state = state.get("expected_state")
    checked_at = _now()

    if not expected_state:
        comparison = {
            "result": "unknown",
            "reason": "No expected state was provided.",
            "differences": []
        }

    else:
        try:
            # 1. Retrieve actual ERPNext state.
            actual_state = fetch_actual_state(expected_state)

            # 2. Compare expected and actual state.
            comparison = compare_states(
                expected_state,
                actual_state
            )

        except Exception as exc:
            comparison = {
                "result": "unknown",
                "reason": f"{type(exc).__name__}: {exc}",
                "differences": []
            }

    verification_result = {
        **comparison,
        "expected_state": expected_state,
        "checked_at": checked_at
    }

    # 3. Determine graph status.
    status_mapping = {
        "verified": "verification_success",
        "mismatch": "verification_failed",
        "unknown": "verification_unknown"
    }

    # 4. Return updated LangGraph state.
    return {
        "verification_result": verification_result,
        "status": status_mapping.get(
            comparison["result"],
            "verification_unknown"
        ),
        "history": [{
            "event": "verification_completed",
            "result": comparison["result"],
            "reason": comparison["reason"],
            "timestamp": checked_at
        }]
    }
