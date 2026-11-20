
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

    def batch(self, prompts, return_exceptions=False):
        return [
            {
                "parsed": self.action,
                "raw": None,
                "parsing_error": None,
            }
            for _ in prompts
        ]



class MockLLM:
    def __init__(self, action):
        self.action = action

    def with_structured_output(self, *args, **kwargs):
        return MockStructuredLLM(self.action)


def mock_action_preparer(monkeypatch, action):
    monkeypatch.setattr(
        action_preparer_node,
        "get_deepseek",
        lambda temperature=0: MockLLM(action),
    )

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
    mock_action_preparer(
        monkeypatch,
        make_action()
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_prepared"
    assert len(result["candidates"]) >= 1

    candidate = result["candidates"][0]

    assert candidate["valid"] is True
    assert candidate["tool"] == "find_customer"
    assert candidate["args"]["customer_name"] == "Example GmbH"
    assert result["prepared_action"] == {}

def test_plan_must_be_validated():
    state = deepcopy(BASE_STATE)
    state["plan_valid"] = False

    result = action_preparer_node.action_preparer(state)

    assert result["status"] == "action_invalid"
    assert result["prepared_action"] == {}


def test_unknown_argument(monkeypatch):
    mock_action_preparer(
        monkeypatch,
        make_action(
            args={"unknown_field": "Example GmbH"}
        )
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_prepared"

    candidate = result["candidates"][0]

    assert candidate["valid"] is False
    assert candidate["args"] == {
        "unknown_field": "Example GmbH"
    }

    assert any(
        "Unknown argument" in error
        for error in candidate["errors"]
    )


def test_missing_information(monkeypatch):
    mock_action_preparer(
        monkeypatch,
        make_action(
            args={},
            missing_info=["customer_name"]
        )
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_prepared"

    candidate = result["candidates"][0]

    assert candidate["missing_info"] == ["customer_name"]
    assert candidate["args"] == {}
    assert candidate["valid"] is True

    
def test_wrong_tool(monkeypatch):
    mock_action_preparer(
        monkeypatch,
        make_action(
            tool="create_customer"
        )
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_prepared"

    candidate = result["candidates"][0]

    assert candidate["valid"] is False
    assert candidate["tool"] == "create_customer"

    assert any(
        "Tool mismatch" in error
        for error in candidate["errors"]
    )

def test_invalid_current_step():
    state = deepcopy(BASE_STATE)
    state["current_step"] = 99

    result = action_preparer_node.action_preparer(state)

    assert result["status"] == "action_invalid"
