
"""
Unit tests for the Finalizer Node.

The tests verify the outcome, the chat message and the
process status for completed and interrupted runs.

No LLM, ERPNext or database connection is required.
"""

from copy import deepcopy
from typing import Any

from langgraph.graph import END, START, StateGraph

from Agent.graph import route_after_planner, route_after_validation
from Agent.models import Plan
from Agent.nodes import finalizer_node, planner_node
from Agent.nodes.finalizer_node import finalizer
from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.planner_node import planner
from Agent.state import PlanningState


# final_result must be declared, otherwise LangGraph drops it.
class State(PlanningState, total=False):
    final_result: dict[str, Any]


def step(step_id, tool, status):
    return {
        "id": step_id,
        "tool": tool,
        "description": f"{tool} step",
        "depends_on": [],
        "execution_condition": None,
        "reason": "test",
        "status": status,
    }


COMPLETED_STATE = {
    "goal": "A sales order for Example GmbH exists.",
    "plan": [
        step("step_1", "find_customer", "completed"),
        step("step_2", "create_customer", "skipped"),
        step("step_3", "create_sales_order", "completed"),
    ],
    "current_step": 3,
    "step_results": {
        "step_1": {"status": "completed",
                   "result": {"customer_exists": True, "customer_id": "CUST-0001"}},
        "step_2": {"status": "skipped", "result": None,
                   "reason": "Customer already exists."},
        "step_3": {"status": "completed",
                   "result": {"sales_order_created": True, "sales_order_id": "SAL-ORD-0042"}},
    },
    "status": "plan_exhausted",
    "history": [
        {"event": "plan_created"},
        {"event": "governance_decision", "decision": "auto"},
        {"event": "governance_decision", "decision": "escalate"},
        {"event": "human_review", "answer": "approve"},
        {"event": "plan_replanned"},
    ],
}


def test_completed_process():
    result = finalizer(deepcopy(COMPLETED_STATE))
    final = result["final_result"]

    assert result["status"] == "process_completed"
    assert final["outcome"] == "completed"
    assert final["reason"] is None
    assert [s["status"] for s in final["steps"]] == ["completed", "skipped", "completed"]

    assert final["governance_decisions"] == {"auto": 1, "escalate": 1}
    assert final["human_reviews"] == {"approve": 1}
    assert final["replans"] == 1

    message = final["message"]
    assert message.startswith("Process completed.")
    assert "2 of 3 steps done, 1 skipped." in message
    assert "sales_order_id=SAL-ORD-0042" in message
    assert "1x executed automatically" in message
    assert "1x escalated to a human" in message
    assert "1x approved" in message
    assert "1x replanned" in message

    assert result["history"][0]["event"] == "process_finalized"


def test_step_status_is_taken_from_step_results():
    # The executor may only write step_results (Governance/INTEGRATION.md).
    state = deepcopy(COMPLETED_STATE)
    for s in state["plan"]:
        s["status"] = "pending"

    result = finalizer(state)

    assert result["final_result"]["outcome"] == "completed"


def test_last_step_skipped_is_not_reported_as_completed():
    # The item was not found, so the sales order was skipped.
    state = {
        "goal": "A sales order for Example GmbH exists.",
        "plan": [
            step("step_1", "find_customer", "completed"),
            step("r1_a", "find_item", "completed"),
            {**step("r1_b", "create_sales_order", "skipped"),
             "depends_on": ["r1_a"],
             "execution_condition": {"all": [{"source_step": "r1_a", "field": "item_exists",
                                              "operator": "eq", "value": True}], "any": []}},
        ],
        "step_results": {
            "step_1": {"status": "completed", "result": {"customer_exists": True,
                                                         "customer_id": "CUST-0001"}},
            "r1_a": {"status": "completed", "result": {"item_exists": False, "item_code": ""}},
            "r1_b": {"status": "skipped", "result": None,
                     "reason": "The execution condition is not satisfied."},
        },
        "status": "plan_exhausted",
        "history": [],
    }

    result = finalizer(state)
    final = result["final_result"]

    assert final["outcome"] == "incomplete"
    assert result["status"] == "process_incomplete"
    assert final["reason"] == ("The last step r1_b (create_sales_order) was skipped "
                               "because r1_a.item_exists = False (condition: = True)")
    assert final["message"].startswith("Process finished, but the goal is not confirmed")
    assert "Process completed" not in final["message"]


def test_skipped_step_in_the_middle_is_still_completed():
    # The customer already exists, the sales order was still created.
    final = finalizer(deepcopy(COMPLETED_STATE))["final_result"]

    assert COMPLETED_STATE["plan"][1]["status"] == "skipped"
    assert final["outcome"] == "completed"


def test_incomplete_process_is_cancelled(monkeypatch):
    calls = []
    monkeypatch.setattr(finalizer_node, "_update_process_status",
                        lambda pid, status: calls.append((pid, status)))

    state = {"plan": [step("step_1", "create_customer", "skipped")],
             "step_results": {"step_1": {"status": "skipped", "result": None}},
             "status": "plan_exhausted", "process_id": "p-4", "history": []}
    finalizer(state)

    assert calls == [("p-4", "CANCELLED")]


def test_rejected_by_human():
    state = deepcopy(COMPLETED_STATE)
    state["plan"][2]["status"] = "pending"
    del state["step_results"]["step_3"]
    state["status"] = "rejected"
    state["governance"] = {"human_comment": "Zu teuer"}

    final = finalizer(state)["final_result"]

    assert final["outcome"] == "rejected"
    assert final["reason"] == "Rejected by a human: Zu teuer"
    assert final["message"].startswith("Process ended: Rejected by a human")
    assert "2 of 3" not in final["message"]
    assert "1 of 3 steps done" in final["message"]


def test_planning_failed():
    state = {
        "goal": "",
        "plan": [],
        "status": "planning_failed",
        "abort_reason": "No tool can create invoices.",
        "history": [],
    }

    result = finalizer(state)

    assert result["status"] == "process_aborted"
    assert result["final_result"]["reason"] == "No tool can create invoices."
    assert result["final_result"]["steps"] == []


def test_missing_information():
    state = {"plan": [], "status": "needs_human",
             "missing_info": ["customer name", "quantity"], "history": []}

    final = finalizer(state)["final_result"]

    assert final["reason"] == "Missing information: customer name, quantity"


def test_invalid_plan():
    state = {"plan": [step("step_1", "find_product", "pending")],
             "status": "plan_invalid",
             "validation_errors": ["Unknown tool 'find_product' in step 'step_1'."],
             "history": []}

    final = finalizer(state)["final_result"]

    assert final["outcome"] == "aborted"
    assert final["reason"].startswith("The plan is invalid")


def test_replan_limit_shows_the_original_error():
    # The failed step stays pending, the reason is only in replan_reason.
    state = {"plan": [step("r2_y", "create_sales_order", "pending")],
             "step_results": {},
             "status": "replan_limit_reached",
             "replan_reason": "create_sales_order failed: Item 'PIZZA' not found.",
             "history": [{"event": "plan_replanned"}, {"event": "plan_replanned"}]}

    final = finalizer(state)["final_result"]

    assert final["outcome"] == "aborted"
    assert "Item 'PIZZA' not found" in final["reason"]
    assert "- r2_y (create_sales_order): open" in final["message"]
    assert "2x replanned" in final["message"]


def test_process_status_is_written(monkeypatch):
    calls = []
    monkeypatch.setattr(finalizer_node, "_update_process_status",
                        lambda pid, status: calls.append((pid, status)))

    state = {**deepcopy(COMPLETED_STATE), "process_id": "p-1"}
    result = finalizer(state)

    assert calls == [("p-1", "COMPLETED")]
    assert result["final_result"]["process_status"] == "COMPLETED"


def test_aborted_process_is_cancelled(monkeypatch):
    calls = []
    monkeypatch.setattr(finalizer_node, "_update_process_status",
                        lambda pid, status: calls.append((pid, status)))

    finalizer({"plan": [], "status": "planning_failed", "process_id": "p-2", "history": []})

    assert calls == [("p-2", "CANCELLED")]


def test_database_error_does_not_break_the_finalizer(monkeypatch, caplog):
    def broken(pid, status):
        raise ConnectionError("Supabase not reachable")

    monkeypatch.setattr(finalizer_node, "_update_process_status", broken)

    state = {**deepcopy(COMPLETED_STATE), "process_id": "p-3"}
    with caplog.at_level("WARNING"):
        result = finalizer(state)

    assert result["final_result"]["outcome"] == "completed"
    assert "Supabase not reachable" in result["final_result"]["process_status_error"]

    # The failure must be visible, not only stored in the state.
    assert "could not save status COMPLETED for process p-3" in caplog.text


def test_no_database_call_without_process_id(monkeypatch):
    def forbidden(pid, status):
        raise AssertionError("must not be called")

    monkeypatch.setattr(finalizer_node, "_update_process_status", forbidden)

    result = finalizer(deepcopy(COMPLETED_STATE))

    assert result["final_result"]["process_status"] is None


# Graph: an invalid first plan ends in the Finalizer.

class MockStructuredLLM:
    def __init__(self, plan):
        self.plan = plan

    def invoke(self, prompt):
        return {"parsed": self.plan, "parsing_error": None, "raw": None}


class MockLLM:
    def __init__(self, plan):
        self.plan = plan

    def with_structured_output(self, *args, **kwargs):
        return MockStructuredLLM(self.plan)


def build_planning_part():
    """
    Planner and Plan Validator from Lara, "stop" leads to the Finalizer.
    """

    builder = StateGraph(State)
    builder.add_node("planner", planner)
    builder.add_node("plan_validator", plan_validator)
    builder.add_node("finalizer", finalizer)

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", route_after_planner, {
        "validate": "plan_validator", "stop": "finalizer"})
    builder.add_conditional_edges("plan_validator", route_after_validation, {
        "conditions": END, "stop": "finalizer"})
    builder.add_edge("finalizer", END)

    return builder.compile()


def test_graph_ends_in_finalizer_when_plan_is_invalid(monkeypatch):
    from Tests.mock_tools import MOCK_TOOLS

    plan = Plan.model_validate({"goal": "Customer exists.", "steps": [{
        "id": "step_1", "tool": "find_product", "description": "Search.",
        "depends_on": [], "execution_condition": None, "reason": "Unknown tool.",
    }]})
    monkeypatch.setattr(planner_node, "llm", MockLLM(plan))

    result = build_planning_part().invoke({
        "instruction": "Find customer Example GmbH.",
        "available_tools": MOCK_TOOLS,
        "history": [],
    })

    assert result["status"] == "process_aborted"
    assert result["final_result"]["last_status"] == "plan_invalid"
    assert "find_product" in result["final_result"]["reason"]


def test_real_graph_ends_in_finalizer_when_plan_is_invalid(monkeypatch):
    from Agent.graph import build_planning_graph
    from Tests.mock_tools import MOCK_TOOLS

    plan = Plan.model_validate({"goal": "Customer exists.", "steps": [{
        "id": "step_1", "tool": "find_product", "description": "Search.",
        "depends_on": [], "execution_condition": None, "reason": "Unknown tool.",
    }]})
    monkeypatch.setattr(planner_node, "llm", MockLLM(plan))

    result = build_planning_graph().invoke({
        "instruction": "Find customer Example GmbH.",
        "available_tools": MOCK_TOOLS,
        "history": [],
    })

    assert result["status"] == "process_aborted"
    assert result["final_result"]["last_status"] == "plan_invalid"
