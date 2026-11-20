
"""
Unit tests for the Replanner Node.

The tests verify that finished steps are kept, new steps
get unique IDs and the number of revisions is limited.

These tests do not require ERPNext or an LLM API request.
"""

from copy import deepcopy
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from Agent.models import Plan
from Agent.nodes import replanner_node
from Agent.nodes.finalizer_node import finalizer
from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.replanner_node import replanner, route_after_replanner
from Agent.state import PlanningState
from Tests.mock_tools import MOCK_TOOLS


# Own state and routing for the small test graph (same as in state.py and graph.py).
# LangGraph drops keys that are not declared, so the test graph needs them.
class State(PlanningState, total=False):
    replan_count: int
    replan_reason: str
    final_result: dict[str, Any]
    # Fields of the Governance Gate that the Replanner clears or the Finalizer reads.
    candidates: list[dict[str, Any]]
    n_requested: int
    governance: dict[str, Any]
    process_id: str


def route_after_validation(state: State) -> Literal["conditions", "replan", "stop"]:
    if state.get("plan_valid") is True:
        return "conditions"
    if (state.get("replan_count") or 0) > 0 and state.get("status") == "plan_invalid":
        return "replan"
    return "stop"



class MockStructuredLLM:
    def __init__(self, plans, prompts):
        self.plans = plans
        self.prompts = prompts

    def invoke(self, prompt):
        self.prompts.append(prompt)
        plan = self.plans.pop(0)
        if isinstance(plan, Exception):
            raise plan
        return {"parsed": plan, "parsing_error": None, "raw": None}


class MockLLM:
    """
    Return the given plans one after another
    and record the prompts.
    """

    def __init__(self, *plans):
        self.plans = list(plans)
        self.prompts = []

    def with_structured_output(self, *args, **kwargs):
        return MockStructuredLLM(self.plans, self.prompts)


class FailingLLM:
    def with_structured_output(self, *args, **kwargs):
        raise AssertionError("The LLM must not be called.")


# Scenario: customer found, sales order failed (item not found).

STEP_1 = {
    "id": "step_1",
    "tool": "find_customer",
    "description": "Find customer Example GmbH.",
    "depends_on": [],
    "execution_condition": None,
    "reason": "Avoid duplicate customers.",
    "status": "completed",
}

STEP_2 = {
    "id": "step_2",
    "tool": "create_sales_order",
    "description": "Create the sales order for 5 croissants.",
    "depends_on": ["step_1"],
    "execution_condition": None,
    "reason": "Requested by the employee.",
    "status": "pending",
}

BASE_STATE = {
    "instruction": "Create a sales order for Example GmbH: 5 croissants.",
    "goal": "A sales order for Example GmbH exists.",
    "available_tools": MOCK_TOOLS,
    "plan": [STEP_1, STEP_2],
    "current_step": 1,
    "plan_valid": True,
    "step_results": {
        "step_1": {
            "status": "completed",
            "result": {"customer_exists": True, "customer_id": "CUST-0001"},
            "reason": "Customer found.",
        },
    },
    "replan_reason": "create_sales_order failed: Item 'Croissant' not found.",
    "history": [],
}


def revised_plan(include_finished_step=False):
    """
    Return the plan the LLM would propose:
    find the item, then create the sales order.
    """

    steps = [
        {
            "id": "step_a",
            "tool": "find_item",
            "description": "Search for the croissant item.",
            "depends_on": [],
            "execution_condition": None,
            "reason": "The item code is unknown.",
        },
        {
            "id": "step_b",
            "tool": "create_sales_order",
            "description": "Create the sales order with the found item.",
            "depends_on": ["step_1", "step_a"],
            "execution_condition": {
                "all": [
                    {"source_step": "step_a", "field": "item_exists",
                     "operator": "eq", "value": True},
                    {"source_step": "step_1", "field": "customer_exists",
                     "operator": "eq", "value": True},
                ],
                "any": [],
            },
            "reason": "Retry with a verified item code.",
        },
    ]

    if include_finished_step:
        steps.insert(0, {**STEP_1, "reason": "Repeated by mistake."})
        steps[0].pop("status")

    return Plan.model_validate({"goal": "A sales order for Example GmbH exists.", "steps": steps})


def run(monkeypatch, llm, state=None):
    monkeypatch.setattr(replanner_node, "llm", llm)
    return replanner(deepcopy(state or BASE_STATE))


def test_keeps_finished_steps_and_prefixes_new_ones(monkeypatch):
    result = run(monkeypatch, MockLLM(revised_plan()))

    assert result["status"] == "planned"
    assert result["replan_count"] == 1
    assert result["current_step"] == 1

    ids = [s["id"] for s in result["plan"]]
    assert ids == ["step_1", "r1_step_a", "r1_step_b"]

    # The finished step is unchanged.
    assert result["plan"][0] == STEP_1

    # New steps are pending and point to the right steps.
    new_b = result["plan"][2]
    assert new_b["status"] == "pending"
    assert new_b["depends_on"] == ["step_1", "r1_step_a"]
    sources = [c["source_step"] for c in new_b["execution_condition"]["all"]]
    assert sources == ["r1_step_a", "step_1"]

    event = result["history"][0]
    assert event["event"] == "plan_replanned"
    assert event["kept_steps"] == ["step_1"]
    assert event["discarded_steps"] == ["step_2"]
    assert event["new_steps"] == ["r1_step_a", "r1_step_b"]


def test_revised_plan_passes_the_plan_validator(monkeypatch):
    result = run(monkeypatch, MockLLM(revised_plan()))

    state = {**deepcopy(BASE_STATE), **result}
    validated = plan_validator(state)

    assert validated["plan_valid"] is True, validated["validation_errors"]


def test_repeated_finished_step_is_dropped(monkeypatch):
    result = run(monkeypatch, MockLLM(revised_plan(include_finished_step=True)))

    ids = [s["id"] for s in result["plan"]]
    assert ids == ["step_1", "r1_step_a", "r1_step_b"]
    assert result["plan"][0] == STEP_1
    assert result["history"][0]["dropped_repeated_steps"] == ["step_1"]


def test_new_step_with_a_finished_id_is_kept(monkeypatch):
    # The LLM restarts the numbering: step_1 is a new step with another tool.
    answer = Plan.model_validate({"goal": "A sales order exists.", "steps": [
        {"id": "step_1", "tool": "find_item", "description": "Search the item.",
         "depends_on": [], "execution_condition": None, "reason": "test"},
        {"id": "step_2", "tool": "create_sales_order", "description": "Create the order.",
         "depends_on": ["step_1"], "execution_condition": None, "reason": "test"},
    ]})
    result = run(monkeypatch, MockLLM(answer))

    assert [(s["id"], s["tool"]) for s in result["plan"]] == [
        ("step_1", "find_customer"),
        ("r1_step_1", "find_item"),
        ("r1_step_2", "create_sales_order"),
    ]
    assert result["plan"][2]["depends_on"] == ["r1_step_1"]
    assert result["history"][0]["dropped_repeated_steps"] == []


def test_prompt_contains_failure_and_finished_results(monkeypatch):
    llm = MockLLM(revised_plan())
    run(monkeypatch, llm)

    prompt = llm.prompts[0]
    assert "Item 'Croissant' not found" in prompt
    assert "CUST-0001" in prompt
    assert "create_sales_order" in prompt


def test_facts_from_a_human_are_passed_on(monkeypatch):
    # A human may have provided missing information via Human Review.
    state = {**deepcopy(BASE_STATE),
             "facts": {"quantity": 5, "delivery_date": "2026-11-24"},
             "artifacts": {"customer": "CUST-0001"}}
    llm = MockLLM(revised_plan())
    run(monkeypatch, llm, state)

    prompt = llm.prompts[0]
    assert '"quantity": 5' in prompt
    assert '"delivery_date": "2026-11-24"' in prompt
    assert "KNOWN BUSINESS FACTS" in prompt
    assert "EXISTING ERP DOCUMENTS" in prompt


def test_no_facts_are_shown_as_none(monkeypatch):
    llm = MockLLM(revised_plan())
    run(monkeypatch, llm)

    prompt = llm.prompts[0]
    assert "KNOWN BUSINESS FACTS (confirmed, e.g. provided by a human):\nNone" in prompt


def test_validation_errors_of_a_revised_plan_are_passed_on(monkeypatch):
    state = {
        **deepcopy(BASE_STATE),
        "replan_count": 1,
        "status": "plan_invalid",
        "validation_errors": ["Unknown tool 'find_product' in step 'r1_step_a'."],
    }
    llm = MockLLM(revised_plan())
    result = run(monkeypatch, llm, state)

    assert result["replan_count"] == 2
    assert [s["id"] for s in result["plan"]][1:] == ["r2_step_a", "r2_step_b"]
    assert "Unknown tool 'find_product'" in llm.prompts[0]
    assert "Item 'Croissant' not found" in llm.prompts[0]


def test_limit_stops_without_calling_the_llm(monkeypatch):
    state = {**deepcopy(BASE_STATE), "replan_count": replanner_node.MAX_REPLANS}
    result = run(monkeypatch, FailingLLM(), state)

    assert result["status"] == "replan_limit_reached"
    assert "plan" not in result
    assert route_after_replanner(result) == "stop"


def test_llm_error_keeps_the_plan(monkeypatch):
    result = run(monkeypatch, MockLLM(RuntimeError("timeout")))

    assert result["status"] == "replanning_failed"
    assert "timeout" in result["abort_reason"]
    assert "plan" not in result


def test_missing_information_needs_a_human(monkeypatch):
    plan = Plan(goal="A sales order exists.", steps=[], missing_info=["Item code of the croissant"])
    result = run(monkeypatch, MockLLM(plan))

    assert result["status"] == "needs_human"
    assert result["missing_info"] == ["Item code of the croissant"]
    assert route_after_replanner(result) == "stop"


def test_unfinished_step_before_current_is_rejected(monkeypatch):
    state = deepcopy(BASE_STATE)
    state["plan"][0]["status"] = "pending"
    del state["step_results"]["step_1"]
    result = run(monkeypatch, FailingLLM(), state)

    assert result["status"] == "replanning_failed"


def test_finished_status_is_read_from_step_results(monkeypatch):
    # The executor may only write step_results (Governance/INTEGRATION.md).
    state = deepcopy(BASE_STATE)
    state["plan"][0]["status"] = "pending"
    result = run(monkeypatch, MockLLM(revised_plan()), state)

    assert result["status"] == "planned"
    assert result["plan"][0]["id"] == "step_1"
    assert result["plan"][0]["status"] == "completed"


def test_old_samples_of_the_failed_step_are_cleared(monkeypatch):
    # Old samples must not be mixed into the next governance decision.
    state = {**deepcopy(BASE_STATE), "candidates": [{"tool": "create_sales_order"}] * 5,
             "n_requested": 3}
    result = run(monkeypatch, MockLLM(revised_plan()), state)

    assert result["candidates"] == []
    assert result["n_requested"] == 0


# Graph: Replanner -> Plan Validator -> (Replanner | Finalizer).

def build_replan_graph():
    builder = StateGraph(State)

    # Wrapped: a node typed with PlanningState only sees the fields of
    # PlanningState. The wrapper passes the full test state, including the
    # governance fields that are not part of PlanningState yet.
    builder.add_node("replanner", lambda state: replanner(state))
    builder.add_node("plan_validator", plan_validator)
    builder.add_node("finalizer", lambda state: finalizer(state))

    builder.add_edge(START, "replanner")
    builder.add_conditional_edges("replanner", route_after_replanner, {
        "validate": "plan_validator", "stop": "finalizer"})
    builder.add_conditional_edges("plan_validator", route_after_validation, {
        "conditions": END, "replan": "replanner", "stop": "finalizer"})
    builder.add_edge("finalizer", END)

    return builder.compile()


def invalid_plan():
    return Plan.model_validate({"goal": "x", "steps": [{
        "id": "step_a", "tool": "find_product", "description": "Search.",
        "depends_on": [], "execution_condition": None, "reason": "Unknown tool.",
    }]})


def test_graph_retries_after_invalid_revision(monkeypatch):
    monkeypatch.setattr(replanner_node, "llm", MockLLM(invalid_plan(), revised_plan()))

    result = build_replan_graph().invoke(deepcopy(BASE_STATE))

    assert result["plan_valid"] is True
    assert result["replan_count"] == 2
    assert [s["id"] for s in result["plan"]] == ["step_1", "r2_step_a", "r2_step_b"]


def test_graph_stops_after_two_invalid_revisions(monkeypatch):
    monkeypatch.setattr(replanner_node, "llm", MockLLM(invalid_plan(), invalid_plan()))

    result = build_replan_graph().invoke(deepcopy(BASE_STATE))

    assert result["status"] == "process_aborted"
    assert result["final_result"]["last_status"] == "replan_limit_reached"
    assert result["final_result"]["replans"] == 2


def test_real_graph_contains_replanner_and_finalizer():
    from Agent.graph import build_planning_graph, route_after_validation as real_route

    nodes = build_planning_graph().get_graph().nodes
    assert "replanner" in nodes and "finalizer" in nodes

    # An invalid revised plan goes back to the Replanner, an invalid first plan does not.
    assert real_route({"plan_valid": False, "status": "plan_invalid", "replan_count": 1}) == "replan"
    assert real_route({"plan_valid": False, "status": "plan_invalid", "replan_count": 0}) == "stop"
