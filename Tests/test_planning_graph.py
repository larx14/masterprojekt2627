
"""
Integration test for the Planner, Plan Validator,
Condition Evaluator and Action Preparer.

Uses the configured LLM and mock tool definitions.
Does not execute ERPNext operations.
"""

import json

from Agent.graph import build_planning_graph
from Tests.mock_tools import MOCK_TOOLS


def test_planner_validator_integration():
    """
    Verify that the planning pipeline produces a valid plan
    and prepares action candidates for Governance.
    """

    graph = build_planning_graph()

    initial_state = {
        "instruction": (
            "Create a new customer named Example GmbH "
            "and prepare a sales order for 5 units of Item A."
        ),
        "available_tools": MOCK_TOOLS,
        "facts": {},
        "artifacts": {},
        "step_results": {},
        "history": [],
    }

    result = graph.invoke(initial_state)

    print("\nFINAL STATUS:")
    print(result.get("status"))

    print("\nBUSINESS GOAL:")
    print(result.get("goal"))

    print("\nVALIDATED PLAN:")
    print(
        json.dumps(
            result.get("plan", []),
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\nPREPARED CANDIDATES:")
    print(
        json.dumps(
            result.get("candidates", []),
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\nVALIDATION ERRORS:")
    print(
        json.dumps(
            result.get("validation_errors", []),
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\nDECISION HISTORY:")
    print(
        json.dumps(
            result.get("history", []),
            indent=2,
            ensure_ascii=False,
        )
    )

    # Verify the current workflow status.
    assert result["status"] == "action_prepared"

    # Verify that the Plan Validator accepted the plan.
    assert result["plan_valid"] is True
    assert result["validation_errors"] == []

    # Verify that the plan contains executable steps.
    assert len(result["plan"]) > 0

    allowed_tools = {
        tool["name"]
        for tool in MOCK_TOOLS
    }

    for step in result["plan"]:
        assert step["tool"] in allowed_tools

    # Verify that the first step is ready for preparation.
    assert result["current_step"] == 0

    first_step = result["plan"][0]

    assert first_step["tool"] == "find_customer"

    # Verify that the Action Preparer generated candidates.
    candidates = result["candidates"]

    assert len(candidates) > 0

    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate["valid"]
    ]

    assert len(valid_candidates) > 0

    candidate = valid_candidates[0]

    assert candidate["tool"] == first_step["tool"]
    assert candidate["tool"] == "find_customer"

    assert candidate["args"]["customer_name"] == (
        "Example GmbH"
    )

    assert candidate["missing_info"] == []

    # Governance has not selected an action yet.
    assert result["prepared_action"] == {}

    # Verify that no ERPNext operation was executed.
    assert result.get("step_results", {}) == {}

    # Verify the audit history.
    events = [
        entry["event"]
        for entry in result["history"]
    ]

    assert "plan_created" in events
    assert "plan_validated" in events
    assert "condition_evaluated" in events
    assert "candidates_prepared" in events

    assert "tool_executed" not in events


if __name__ == "__main__":
    test_planner_validator_integration()
    print("\nINTEGRATION TEST PASSED")
