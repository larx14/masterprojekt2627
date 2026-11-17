
"""
Integration test for conditional step routing.

This test uses simulated execution results.
It does not invoke the Planner, LLM or ERPNext.
"""

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState
from Agent.nodes.condition_evaluator_node import condition_evaluator
from Agent.nodes.skip_step_node import skip_step


def route_condition(state: PlanningState) -> str:
    outcome = state.get("condition_result")

    if outcome == "false":
        return "skip"

    return "end"


def build_test_graph():
    builder = StateGraph(PlanningState)

    builder.add_node("condition_evaluator", condition_evaluator)
    builder.add_node("skip_step", skip_step)

    builder.add_edge(START, "condition_evaluator")

    builder.add_conditional_edges(
        "condition_evaluator",
        route_condition,
        {
            "skip": "skip_step",
            "end": END
        }
    )

    builder.add_edge("skip_step", "condition_evaluator")

    return builder.compile()


def test_existing_customer_skips_creation():
    graph = build_test_graph()

    state = {
        "plan_valid": True,
        "current_step": 1,
        "plan": [
            {
                "id": "step_1",
                "tool": "find_customer",
                "status": "completed",
                "depends_on": [],
                "execution_condition": None
            },
            {
                "id": "step_2",
                "tool": "create_customer",
                "status": "pending",
                "depends_on": ["step_1"],
                "execution_condition": {
                    "all": [{
                        "source_step": "step_1",
                        "field": "customer_exists",
                        "operator": "eq",
                        "value": False
                    }],
                    "any": []
                }
            },
            {
                "id": "step_3",
                "tool": "find_item",
                "status": "pending",
                "depends_on": [],
                "execution_condition": None
            }
        ],
        "step_results": {
            "step_1": {
                "status": "completed",
                "result": {
                    "customer_exists": True,
                    "customer_id": "CUST-0001"
                }
            }
        },
        "history": []
    }

    output = graph.invoke(state)

    assert output["plan"][1]["status"] == "skipped"
    assert output["current_step"] == 2
    assert output["condition_result"] == "true"
    assert output["status"] == "condition_met"

    events = [
        event["event"]
        for event in output["history"]
    ]

    assert "step_skipped" in events


if __name__ == "__main__":
    test_existing_customer_skips_creation()
    print("CONDITIONAL ROUTING TEST PASSED")
