
"""
Test candidate generation for the Governance Gate.
"""

from copy import deepcopy

from Agent.models import PreparedAction
from Agent.nodes import action_preparer_node
from Tests.mock_tools import MOCK_TOOLS


class MockStructuredLLM:
    def __init__(self, responses):
        self.responses = responses

    def batch(self, prompts, return_exceptions=False):
        return self.responses[:len(prompts)]


class MockLLM:
    def __init__(self, responses):
        self.responses = responses

    def with_structured_output(self, *args, **kwargs):
        return MockStructuredLLM(self.responses)


def candidate_response():
    return {
        "parsed": PreparedAction(
            tool="find_customer",
            args={"customer_name": "Example GmbH"},
            missing_info=[],
            reason="Resolve the requested customer.",
            confidence=0.95,
        ),
        "raw": None,
        "parsing_error": None,
    }


BASE_STATE = {
    "instruction": "Find customer Example GmbH.",
    "goal": "Resolve the customer.",
    "plan_valid": True,
    "current_step": 0,
    "plan": [{
        "id": "step1",
        "tool": "find_customer",
        "description": "Find the customer.",
        "depends_on": [],
        "execution_condition": None,
        "reason": "Resolve customer identity.",
        "status": "pending",
    }],
    "available_tools": MOCK_TOOLS,
    "facts": {},
    "artifacts": {},
    "step_results": {},
    "candidates": [],
    "n_requested": 3,
    "history": [],
}


def test_generates_three_candidates(monkeypatch):
    responses = [candidate_response() for _ in range(3)]

    monkeypatch.setattr(
        action_preparer_node,
        "get_deepseek",
        lambda temperature=0: MockLLM(responses),
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_prepared"
    assert len(result["candidates"]) == 3

    assert all(
        candidate["valid"]
        for candidate in result["candidates"]
    )

    assert result["prepared_action"] == {}
    assert result["n_requested"] == 0


def test_failed_sample_does_not_abort_batch(monkeypatch):
    responses = [
        candidate_response(),
        RuntimeError("LLM timeout"),
        candidate_response(),
    ]

    monkeypatch.setattr(
        action_preparer_node,
        "get_deepseek",
        lambda temperature=0: MockLLM(responses),
    )

    result = action_preparer_node.action_preparer(
        deepcopy(BASE_STATE)
    )

    assert result["status"] == "action_prepared"

    assert len(result["candidates"]) == 3

    assert result["candidates"][0]["valid"] is True
    assert result["candidates"][1]["valid"] is False
    assert result["candidates"][2]["valid"] is True

    assert result["prepared_action"] == {}
