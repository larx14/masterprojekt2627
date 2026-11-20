
"""
Integration tests for replanning and finalization.

ERPNext tools are not executed. LLM responses are mocked
to verify deterministic graph routing and state updates.
"""

from copy import deepcopy

from langgraph.graph import StateGraph, START, END

from Agent.models import Plan, PreparedAction
from Agent.state import PlanningState
from Agent.graph import (
    route_after_validation,
    route_after_condition,
)
from Agent.nodes import (
    replanner_node,
    action_preparer_node,
)
from Agent.nodes.replanner_node import (
    replanner,
    route_after_replanner,
)
from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.condition_evaluator_node import condition_evaluator
from Agent.nodes.skip_step_node import skip_step
from Agent.nodes.action_preparer_node import action_preparer
from Agent.nodes.finalizer_node import finalizer

from Tests.mock_tools import MOCK_TOOLS


class MockStructuredLLM:
    def __init__(self, response):
        self.response = response

    def invoke(self, prompt):
        return {
            "parsed": self.response,
            "raw": None,
            "parsing_error": None,
        }


class MockLLM:
    def __init__(self, response):
        self.response = response

    def with_structured_output(self, *args, **kwargs):
        return MockStructuredLLM(self.response)


def build_integration_graph():
    """
    Start at the Replanner to simulate a failed
    ERPNext operation before the normal planning flow.
    """

    builder = StateGraph(PlanningState)

    builder.add_node("replanner", replanner)
    builder.add_node("plan_validator", plan_validator)
    builder.add_node("condition_evaluator", condition_evaluator)
    builder.add_node("skip_step", skip_step)
    builder.add_node("action_preparer", action_preparer)
    builder.add_node("finalizer", finalizer)

    builder.add_edge(START, "replanner")

    builder.add_conditional_edges(
        "replanner",
        route_after_replanner,
        {
            "validate": "plan_validator",
            "stop": "finalizer",
        },
    )

    builder.add_conditional_edges(
        "plan_validator",
        route_after_validation,
        {
            "conditions": "condition_evaluator",
            "replan": "replanner",
            "stop": "finalizer",
        },
    )

    builder.add_conditional_edges(
        "condition_evaluator",
        route_after_condition,
        {
            "prepare": "action_preparer",
            "skip": "skip_step",
            "stop": "finalizer",
        },
    )

    builder.add_edge("skip_step", "condition_evaluator")
    builder.add_edge("action_preparer", END)
    builder.add_edge("finalizer", END)

    return builder.compile()


BASE_STATE = {
    "instruction": (
        "Create a sales order for Example GmbH: "
        "5 croissants."
    ),
    "goal": "A sales order for Example GmbH exists.",
    "available_tools": MOCK_TOOLS,
    "plan": [
        {
            "id": "step_1",
            "tool": "find_customer",
            "description": "Find customer Example GmbH.",
            "depends_on": [],
            "execution_condition": None,
            "reason": "Resolve the customer.",
            "status": "completed",
        },
        {
            "id": "step_2",
            "tool": "create_sales_order",
            "description": "Create the sales order.",
            "depends_on": ["step_1"],
            "execution_condition": None,
            "reason": "Fulfill the employee request.",
            "status": "pending",
        },
    ],
    "current_step": 1,
    "plan_valid": True,
    "step_results": {
        "step_1": {
            "status": "completed",
            "result": {
                "customer_exists": True,
                "customer_id": "CUST-0001",
            },
        },
    },
    "replan_reason": (
        "Sales order creation failed because "
        "the item code is unknown."
    ),
    "replan_count": 0,
    "facts": {},
    "artifacts": {},
    "history": [],
}


def revised_plan():
    """
    Simulate a valid LLM-generated replacement plan.
    """

    return Plan.model_validate({
        "goal": "A sales order for Example GmbH exists.",
        "steps": [
            {
                "id": "find_croissant",
                "tool": "find_item",
                "description": "Resolve the croissant item.",
                "depends_on": [],
                "execution_condition": None,
                "reason": "The item code is unknown.",
            },
            {
                "id": "retry_sales_order",
                "tool": "create_sales_order",
                "description": "Create the sales order.",
                "depends_on": [
                    "step_1",
                    "find_croissant",
                ],
                "execution_condition": {
                    "all": [
                        {
                            "source_step": "step_1",
                            "field": "customer_exists",
                            "operator": "eq",
                            "value": True,
                        },
                        {
                            "source_step": "find_croissant",
                            "field": "item_exists",
                            "operator": "eq",
                            "value": True,
                        },
                    ],
                    "any": [],
                },
                "reason": (
                    "Use the verified customer and item."
                ),
            },
        ],
    })


def test_replanner_to_action_preparer(monkeypatch):
    """
    Verify the complete recovery path up to
    preparation of the next ERPNext tool call.
    """

    monkeypatch.setattr(
        replanner_node,
        "llm",
        MockLLM(revised_plan()),
    )

    prepared = PreparedAction(
        tool="find_item",
        args={"search": "Croissant"},
        missing_info=[],
        reason="Resolve the requested item.",
        confidence=0.95,
    )

    monkeypatch.setattr(
        action_preparer_node,
        "llm",
        MockLLM(prepared),
    )

    graph = build_integration_graph()
    result = graph.invoke(deepcopy(BASE_STATE))

    assert result["status"] == "action_prepared"
    assert result["plan_valid"] is True
    assert result["validation_errors"] == []
    assert result["replan_count"] == 1

    assert result["plan"][0]["id"] == "step_1"
    assert result["plan"][0]["status"] == "completed"

    assert result["plan"][1]["id"] == "r1_find_croissant"

    assert result["plan"][2]["depends_on"] == [
        "step_1",
        "r1_find_croissant",
    ]

    assert result["prepared_action"]["step_id"] == (
        "r1_find_croissant"
    )
    assert result["prepared_action"]["tool"] == "find_item"
    assert result["prepared_action"]["args"] == {
        "search": "Croissant"
    }

    events = [
        entry["event"] for entry in result["history"]
    ]

    assert "plan_replanned" in events
    assert "plan_validated" in events
    assert "condition_evaluated" in events
    assert "action_prepared" in events

    assert "process_finalized" not in events


def test_replan_limit_routes_to_finalizer(monkeypatch):
    """
    Verify that the Finalizer handles an exhausted
    replanning budget without invoking an LLM.
    """

    class FailingLLM:
        def with_structured_output(self, *args, **kwargs):
            raise AssertionError(
                "The LLM must not be called."
            )

    monkeypatch.setattr(
        replanner_node,
        "llm",
        FailingLLM(),
    )

    state = deepcopy(BASE_STATE)
    state["replan_count"] = replanner_node.MAX_REPLANS

    graph = build_integration_graph()
    result = graph.invoke(state)

    assert result["status"] == "process_aborted"

    assert result["final_result"]["outcome"] == "aborted"
    assert result["final_result"]["last_status"] == (
        "replan_limit_reached"
    )

    events = [
        entry["event"] for entry in result["history"]
    ]

    assert "replan_failed" in events
    assert "process_finalized" in events
