
"""
Unit tests for the governance-aware Executor Node.

The tests verify execution authorization, tool invocation,
result handling, error handling and duplicate protection.
No LLM or ERPNext connection is required.
"""

from copy import deepcopy

from Agent.nodes.executor_node import executor

from Tests.mock_executor_tools import (
    MockFindCustomer,
    MockFailingTool,
    MockBusinessFailureTool,
    MockInvalidResultTool,
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


BASE_STATE = {
    "status": "auto",
    "plan_valid": True,
    "current_step": 0,
    "plan": [
        {
            "id": "step1",
            "tool": "find_customer",
            "description": "Find the customer.",
            "depends_on": [],
            "execution_condition": None,
            "reason": "Resolve the customer.",
            "status": "pending",
        }
    ],
    "prepared_action": ACTION,
    "governance": {
        "decision": "auto",
        "final_action": ACTION,
    },
    "available_tools": MOCK_TOOLS,
    "step_results": {},
    "candidates": [],
    "n_requested": 0,
    "history": [],
}


def test_auto_approved_execution():
    """
    Verify that an automatically authorized tool is executed.
    """

    tool = MockFindCustomer()

    result = executor(
        deepcopy(BASE_STATE),
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_succeeded"
    assert len(tool.calls) == 1

    record = result["step_results"]["step1"]

    assert record["status"] == "completed"

    assert record["result"] == {
        "customer_exists": True,
        "customer_id": "CUST-0001",
    }

    assert result["prepared_action"] == {}
    assert result["candidates"] == []
    assert result["n_requested"] == 0


def test_execution_without_governance_is_blocked():
    """
    Reject execution without a Governance decision.
    """

    state = deepcopy(BASE_STATE)
    state["governance"] = {}

    tool = MockFindCustomer()

    result = executor(
        state,
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_blocked"
    assert tool.calls == []


def test_rejected_action_is_blocked():
    """
    Reject an action that Governance did not approve.
    """

    state = deepcopy(BASE_STATE)
    state["status"] = "rejected"

    tool = MockFindCustomer()

    result = executor(
        state,
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_blocked"
    assert tool.calls == []


def test_mismatched_action_is_blocked():
    """
    Reject execution when the authorized arguments differ.
    """

    state = deepcopy(BASE_STATE)

    state["governance"]["final_action"] = {
        "step_id": "step1",
        "tool": "find_customer",
        "args": {
            "customer_name": "Different GmbH"
        },
    }

    tool = MockFindCustomer()

    result = executor(
        state,
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_blocked"
    assert tool.calls == []


def test_human_approved_execution():
    """
    Verify execution with an explicit human approval record.
    """

    state = deepcopy(BASE_STATE)

    state["status"] = "approved"

    state["governance"] = {
        "decision": "escalate",
        "human_action": "approve",
        "final_action": ACTION,
    }

    tool = MockFindCustomer()

    result = executor(
        state,
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_succeeded"
    assert len(tool.calls) == 1


def test_tool_failure_is_recorded():
    """
    Record exceptions raised by the tool.
    """

    tool = MockFailingTool()

    result = executor(
        deepcopy(BASE_STATE),
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_failed"

    record = result["step_results"]["step1"]

    assert record["status"] == "failed"
    assert record["result"] is None

    assert "ERPNext API unavailable" in (
        result["execution_error"]
    )

    assert len(tool.calls) == 1


def test_business_failure_is_recorded():
    """
    Record an explicit unsuccessful tool response.
    """

    tool = MockBusinessFailureTool()

    result = executor(
        deepcopy(BASE_STATE),
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_failed"
    assert result["step_results"]["step1"]["status"] == "failed"
    assert len(tool.calls) == 1


def test_duplicate_execution_is_blocked():
    """
    Prevent execution when the step already has a result.
    """

    state = deepcopy(BASE_STATE)

    state["step_results"]["step1"] = {
        "status": "completed",
        "result": {
            "customer_exists": True
        },
    }

    tool = MockFindCustomer()

    result = executor(
        state,
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_blocked"
    assert tool.calls == []


def test_unknown_tool_is_blocked():
    """
    Reject tool names missing from the executable registry.
    """

    result = executor(
        deepcopy(BASE_STATE),
        registry={},
    )

    assert result["status"] == "execution_blocked"


def test_successful_negative_lookup():
    """
    A successful lookup without a match is not an error.
    """

    tool = MockFindCustomer(exists=False)

    result = executor(
        deepcopy(BASE_STATE),
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_succeeded"

    record = result["step_results"]["step1"]

    assert record["status"] == "completed"
    assert record["result"]["customer_exists"] is False
    assert record["result"]["customer_id"] == ""


def test_invalid_result_type_is_recorded():
    """
    Reject tool results incompatible with result_fields.
    """

    tool = MockInvalidResultTool()

    result = executor(
        deepcopy(BASE_STATE),
        registry={"find_customer": tool},
    )

    assert result["status"] == "execution_failed"

    record = result["step_results"]["step1"]

    assert record["status"] == "failed"

    assert "Invalid type for result field" in (
        result["execution_error"]
    )

    assert len(tool.calls) == 1
