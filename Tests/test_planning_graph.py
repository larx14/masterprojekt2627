
"""
Integration test for the Planner and Plan Validator.

Uses the configured LLM and mock tool definitions.
Does not execute ERPNext operations.
"""

import json

from Agent.graph import build_planning_graph
from Tests.mock_tools import MOCK_TOOLS 



def test_planner_validator_integration():
    """
    Verify that the Planner generates a plan and
    the Plan Validator validates its structure.
    """

    graph = build_planning_graph()

    initial_state = {
        "instruction": (
            "Create a new customer named Example GmbH "
            "and prepare a sales order for 5 units of Item A."
        ),
        "available_tools": MOCK_TOOLS,
        "history": [],
    }

    result = graph.invoke(initial_state)

    print("\nFINAL STATUS:")
    print(result.get("status"))

    print("\nBUSINESS GOAL:")
    print(result.get("goal"))

    print("\nPROPOSED STEPS:")
    print(json.dumps(
        result.get("proposed_steps", []),
        indent=2,
        ensure_ascii=False
    ))

    print("\nVALIDATION ERRORS:")
    print(json.dumps(
        result.get("validation_errors", []),
        indent=2,
        ensure_ascii=False
    ))

    print("\nDECISION HISTORY:")
    print(json.dumps(
        result.get("history", []),
        indent=2,
        ensure_ascii=False
    ))

    # Verify that planning completed successfully.
    assert result["status"] == "action_prepared", (
        f"Unexpected workflow status: {result.get('status')}"
     )

    assert result["plan_valid"] is True
    assert result["validation_errors"] == []

    assert result["prepared_action"]["tool"] == "find_customer"
    assert result["prepared_action"]["args"]["customer_name"] == "Example GmbH"

    # Verify that the validator approved the plan.
    assert result["plan_valid"] is True
    assert result["validation_errors"] == []

    # Verify that the plan is not empty.
    assert len(result["plan"]) > 0

    # Verify that all tools exist in the catalog.
    allowed_tools = {
        tool["name"] for tool in MOCK_TOOLS
    }

    for step in result["plan"]:
        assert step["tool"] in allowed_tools

    # Verify that both nodes produced audit events.
    events = [
        entry["event"]
        for entry in result["history"]
    ]

    assert "plan_created" in events
    assert "plan_validated" in events
    assert "condition_evaluated" in events
    assert "action_prepared" in events

    # Verify that no action was prepared or executed.
    # Verify that the first action was prepared correctly.
    assert result["prepared_action"]["step_id"] == result["plan"][0]["id"]
    assert result["prepared_action"]["tool"] == "find_customer"
    assert result["prepared_action"]["args"]["customer_name"] == "Example GmbH"

    # Verify that no ERPNext operation was executed.
    assert result.get("step_results", {}) == {}


if __name__ == "__main__":
    test_planner_validator_integration()
    print("\nINTEGRATION TEST PASSED")
