
"""
Integration tests for the Executor Node using LangGraph.

The tests simulate a Governance-approved action and print
the complete agent state after execution.

No real ERPNext operations or LLM calls are performed.
"""

import json
from copy import deepcopy
from typing import Any

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState
from Agent.nodes.executor_node import executor

from Tests.mock_executor_tools import (
    MockFindCustomer,
    MockFailingTool,
)
from Tests.mock_tools import MOCK_TOOLS


ACTION = {
    "step_id": "step1",
    "tool": "find_customer",
    "args": {
        "customer_name": "Example GmbH"
    },
    "reason": "Resolve the customer.",
    "confidence": 0.95,
}


INITIAL_STATE = {
    "instruction": "Find customer Example GmbH.",
    "goal": "Resolve the customer.",
    "status": "auto",
    "plan_valid": True,
    "current_step": 0,
    "plan": [
        {
            "id": "step1",
            "tool": "find_customer",
            "description": "Find customer Example GmbH.",
            "depends_on": [],
            "execution_condition": None,
            "reason": "Resolve customer identity.",
            "status": "pending",
        }
    ],
    "prepared_action": ACTION,
    "governance": {
        "decision": "auto",
        "final_action": deepcopy(ACTION),
    },
    "available_tools": MOCK_TOOLS,
    "facts": {},
    "artifacts": {},
    "step_results": {},
    "candidates": [],
    "n_requested": 0,
    "history": [],
}


def print_state(state: PlanningState) -> dict[str, Any]:
    """
    Display the complete state received after the Executor.

    This node is read-only and does not modify the state.
    """

    print("\n" + "=" * 75)
    print("STATE RECEIVED FROM EXECUTOR")
    print("=" * 75)

    print(
        json.dumps(
            dict(state),
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )

    print("=" * 75 + "\n")

    return {}


def build_executor_test_graph(tool):
    """
    Build an isolated Executor workflow.

    The tool registry contains only the selected mock tool.
    """

    def execute(state: PlanningState) -> dict[str, Any]:
        return executor(
            state,
            registry={
                "find_customer": tool
            },
        )

    builder = StateGraph(PlanningState)

    builder.add_node("executor", execute)
    builder.add_node("print_state", print_state)

    builder.add_edge(START, "executor")
    builder.add_edge("executor", "print_state")
    builder.add_edge("print_state", END)

    return builder.compile()


def test_executor_success_graph():
    """
    Verify successful execution and inspect the resulting state.
    """

    tool = MockFindCustomer()

    graph = build_executor_test_graph(tool)

    result = graph.invoke(
        deepcopy(INITIAL_STATE)
    )

    assert result["status"] == "execution_succeeded"

    assert result["step_results"]["step1"]["status"] == (
        "completed"
    )

    assert result["step_results"]["step1"]["result"] == {
        "customer_exists": True,
        "customer_id": "CUST-0001",
    }

    assert result["prepared_action"] == {}
    assert result["candidates"] == []
    assert result["n_requested"] == 0

    assert result["current_step"] == 0
    assert len(tool.calls) == 1


def test_executor_failure_graph():
    """
    Verify failed execution and inspect the resulting state.
    """

    tool = MockFailingTool()

    graph = build_executor_test_graph(tool)

    result = graph.invoke(
        deepcopy(INITIAL_STATE)
    )

    assert result["status"] == "execution_failed"

    assert result["step_results"]["step1"]["status"] == (
        "failed"
    )

    assert result["step_results"]["step1"]["result"] is None

    assert "ERPNext API unavailable" in (
        result["execution_error"]
    )

    assert result["current_step"] == 0
    assert len(tool.calls) == 1
