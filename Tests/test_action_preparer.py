
"""
Unit tests for the generic Action Preparer Node.

These tests do not require ERPNext or an LLM API request.
"""

from copy import deepcopy

from Agent.models import PreparedAction
from Agent.nodes import action_preparer_node


BASE_STATE = {
    "instruction": (
        "Create a customer named Example GmbH."
    ),
    "goal": "Customer Example GmbH exists.",
    "plan_valid": True,
    "current_step": 0,
    "plan": [
        {
            "id": "step_1",
            "tool": "find_customer",
            "description": "Find customer Example GmbH.",
            "depends_on": [],
            "execution_condition": None,
            "reason": "Avoid creating duplicate customers.",
            "status": "pending"
        }
    ],
    "available_tools": [
        {
            "name": "find_customer",
            "description": "Find an existing customer.",
            "parameters": {
                "customer_name": "str"
            }
        }
    ],
    "facts": {},
    "artifacts": {},
    "step_results": {},
    "history": []
}


class MockStructuredLLM:
    def __init__(self, action):
        self.action = action

    def invoke(self, prompt):
        return {
            "parsed": self.action,
            "parsing_error": None,
            "raw": None
        }


class MockLLM:
    def __init__(self, action):
        self.action = action

    def with_structured_output(self, *args, **kwargs):
        return MockStructuredLLM(self.action)


def make_action(
    args=None,
    missing_info=None,
    tool="find_customer"
):
    return PreparedAction(
        tool=tool,
        args=args if args is not None else {
            "customer_name": "Example GmbH"
        },
        missing_info=missing_info or [],
        reason="The customer name was provided by the employee.",
        confidence=0.95
    )


def test_valid_action(monkeypatch):
    monkeypatch.setattr(
        action_preparer_node,
        "llm",
        MockLLM(make_action())
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_prepared"
    assert result["prepared_action"]["tool"] == "find_customer"
    assert result["prepared_action"]["step_id"] == "step_1"
    assert result["prepared_action"]["args"] == {
        "customer_name": "Example GmbH"
    }


def test_plan_must_be_validated():
    state = deepcopy(BASE_STATE)
    state["plan_valid"] = False

    result = action_preparer_node.action_preparer(state)

    assert result["status"] == "action_invalid"
    assert result["prepared_action"] == {}


def test_unknown_argument(monkeypatch):
    monkeypatch.setattr(
        action_preparer_node,
        "llm",
        MockLLM(
            make_action(
                args={"unknown_field": "Example GmbH"}
            )
        )
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_invalid"
    assert result["prepared_action"] == {}


def test_missing_information(monkeypatch):
    monkeypatch.setattr(
        action_preparer_node,
        "llm",
        MockLLM(
            make_action(
                args={},
                missing_info=["customer_name"]
            )
        )
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "needs_human"
    assert result["prepared_action"] == {}
    assert "customer_name" in result["missing_info"]


def test_wrong_tool(monkeypatch):
    monkeypatch.setattr(
        action_preparer_node,
        "llm",
        MockLLM(
            make_action(tool="create_customer")
        )
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_invalid"
    assert result["prepared_action"] == {}


def test_invalid_current_step():
    state = deepcopy(BASE_STATE)
    state["current_step"] = 99

    result = action_preparer_node.action_preparer(state)

    assert result["status"] == "action_invalid"
