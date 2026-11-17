
"""
Integration test for the complete planning pipeline.

Uses the configured LLM but does not execute ERPNext tools.
"""

import json

from Agent.graph import build_planning_graph
from Tests.mock_tools import MOCK_TOOLS as t

tools = t 
def test_complete_planning_pipeline():
    graph = build_planning_graph()

    initial_state = {
        "instruction": (
            "Create a new customer named Example GmbH "
            "and prepare a sales order for 5 units of Item A."
        ),
        "available_tools": tools ,
        "facts": {},
        "artifacts": {},
        "step_results": {},
        "history": []
    }

    result = graph.invoke(initial_state)

    print("\nFINAL STATUS:")
    print(result.get("status"))

    print("\nPLAN:")
    print(json.dumps(
        result.get("plan", []),
        indent=2
    ))

    print("\nPREPARED ACTION:")
    print(json.dumps(
        result.get("prepared_action", {}),
        indent=2
    ))

    print("\nDECISION EVENTS:")
    print([
        entry["event"]
        for entry in result.get("history", [])
    ])


     # Print validation errors for debugging
    print("\nVALIDATION ERRORS:")
    for error in result.get("validation_errors", []):
        print("-", error)

    assert result["status"] == "action_prepared"
    assert result["plan_valid"] is True

    action = result["prepared_action"]

    assert action["step_id"] == result["plan"][0]["id"]
    assert action["tool"] == result["plan"][0]["tool"]

    events = [
        entry["event"]
        for entry in result["history"]
    ]

    assert "plan_created" in events
    assert "plan_validated" in events
    assert "action_prepared" in events


if __name__ == "__main__":
    test_complete_planning_pipeline()
    print("\nINTEGRATION TEST PASSED")
