
"""
Integration test for the Planner and Plan Validator.

Uses the configured LLM and mock tool definitions.
Does not execute ERPNext operations.
"""

import json

from Agent.graph import build_planning_graph


MOCK_TOOLS = [
    {
        "name": "find_customer",
        "description": "Search for an existing customer.",
        "parameters": {"customer_name": "str"},
    },
    {
        "name": "create_customer",
        "description": "Create a customer record.",
        "parameters": {"customer_name": "str"},
    },
    {
        "name": "find_item",
        "description": "Search for an existing item.",
        "parameters": {"search": "str"},
    },
    {
        "name": "create_sales_order",
        "description": "Create a sales order.",
        "parameters": {
            "customer": "str",
            "items": "list",
        },
    },
]


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
    assert result["status"] == "plan_valid", (
        f"Unexpected workflow status: "
        f"{result.get('status')}"
    )

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

    # Verify that no action was prepared or executed.
    assert not result.get("prepared_action")


if __name__ == "__main__":
    test_planner_validator_integration()
    print("\nINTEGRATION TEST PASSED")
