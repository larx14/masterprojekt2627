
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

    print("\nPREPARED CANDIDATES:")
    print(json.dumps(
        result.get("candidates", []),
        indent=2,
        ensure_ascii=False
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

    candidates = result["candidates"]

        
    assert len(candidates) > 0

    valid_candidates = [
            candidate
            for candidate in candidates
            if candidate["valid"]
        ]

    assert len(valid_candidates) > 0

    candidate = valid_candidates[0]

    assert candidate["tool"] == result["plan"][0]["tool"]
    assert candidate["tool"] == "find_customer"
    assert candidate["args"]["customer_name"] == "Example GmbH"

    assert result["prepared_action"] == {}
   
    events = [
        entry["event"]
        for entry in result["history"]
    ]

    assert "plan_created" in events
    assert "plan_validated" in events
    assert "candidates_prepared" in events


if __name__ == "__main__":
    test_complete_planning_pipeline()
    print("\nINTEGRATION TEST PASSED")
