"""
Graph test for the governance layer: fake preparer -> gate ->
human review (interrupt/resume) -> fake executor.

Uses an in-memory checkpointer and decision log.
No LLM, ERPNext or database connection is required.
"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from Agent.state import PlanningState
from Governance import decision_log
from Governance.channels import ScriptedChannel, run_with_escalation
from Agent.nodes.governance_gate_node import governance_gate, route_after_governance
from Agent.nodes.human_review_node import human_review, route_after_review
from Governance.state_fields import GovernanceFields


class State(PlanningState, GovernanceFields, total=False):
    pass


TOOLS = [{"name": "create_purchase_order", "risk": "draft",
          "parameters": {"supplier": "str", "items": "list"}}]

PLAN = [{"id": "step_1", "tool": "create_purchase_order",
         "description": "PO anlegen", "depends_on": [],
         "execution_condition": None, "reason": "test", "status": "pending"}]


def po(supplier="Mühle Schmidt", qty=50, missing=None):
    return {"tool": "create_purchase_order",
            "args": {"supplier": supplier,
                     "items": [{"item_code": "MEHL-550", "qty": qty, "rate": 0.8}]},
            "missing_info": missing or [], "valid": True,
            "confidence": 0.9, "reason": "test"}


def build(sample_rounds):
    """
    sample_rounds: list of candidate lists, one per preparer call.
    """

    rounds = list(sample_rounds)
    calls = {"preparer": 0}

    def fake_preparer(state):
        calls["preparer"] += 1
        new = rounds.pop(0)
        return {"candidates": (state.get("candidates") or []) + new,
                "status": "action_prepared"}

    def fake_executor(state):
        return {"status": "executed",
                "step_results": {"step_1": {"status": "completed",
                                            "result": state["prepared_action"]}},
                "candidates": []}

    b = StateGraph(State)
    b.add_node("action_preparer", fake_preparer)
    b.add_node("governance_gate", governance_gate)
    b.add_node("human_review", human_review)
    b.add_node("executor", fake_executor)

    b.add_edge(START, "action_preparer")
    b.add_edge("action_preparer", "governance_gate")
    b.add_conditional_edges("governance_gate", route_after_governance, {
        "sample": "action_preparer", "execute": "executor",
        "review": "human_review", "stop": END})
    b.add_conditional_edges("human_review", route_after_review, {
        "execute": "executor", "prepare": "action_preparer", "stop": END})
    b.add_edge("executor", END)

    return b.compile(checkpointer=InMemorySaver()), calls


@pytest.fixture
def log():
    backend = decision_log.MemoryBackend()
    old = decision_log.get_backend()
    decision_log.set_backend(backend)
    yield backend
    decision_log.set_backend(old)


def start(level, **extra):
    return {"plan": PLAN, "current_step": 0, "plan_valid": True,
            "available_tools": TOOLS, "autonomy_level": level,
            "trigger": "chat", "facts": {}, "history": [], **extra}


CONFIG = {"configurable": {"thread_id": "t1"}}


def test_unanimous_l2_executes_without_human(log):
    graph, calls = build([[po()] * 5])
    channel = ScriptedChannel([])

    result = run_with_escalation(graph, start("L2"), CONFIG, lambda p: channel)

    assert result["status"] == "executed"
    assert calls["preparer"] == 1
    assert channel.payloads == []
    (record,) = log.records.values()
    assert record["decision"] == "auto"
    assert record["conf_consistency"] == 1.0
    assert record["thread_id"] == "t1"


def test_disagreement_samples_more_then_escalates_and_human_selects(log):
    # 3/5 -> more samples -> 6/10 for submit-risk (0.8) -> escalate
    tools = [{**TOOLS[0], "risk": "submit"}]
    graph, calls = build([
        [po()] * 3 + [po(supplier="Bio-Mühle")] * 2,
        [po()] * 3 + [po(supplier="Bio-Mühle")] * 2,
    ])
    channel = ScriptedChannel([{"action": "select", "index": 1}])

    result = run_with_escalation(graph, start("L2", available_tools=tools),
                                 CONFIG, lambda p: channel)

    assert calls["preparer"] == 2
    assert result["status"] == "executed"
    assert result["prepared_action"]["args"]["supplier"] == "Bio-Mühle"

    payload = channel.payloads[0]
    assert payload["confidence"] == 0.6
    assert [o["votes"] for o in payload["options"]] == ["6/10", "4/10"]

    (record,) = log.records.values()
    assert record["n_samples"] == 10
    assert record["human_action"] == "select"
    assert record["corrected"] is True


def test_l1_escalates_and_reject_stops(log):
    graph, _ = build([[po()] * 5])
    channel = ScriptedChannel([{"action": "reject", "comment": "nicht bestellen"}])

    result = run_with_escalation(graph, start("L1"), CONFIG, lambda p: channel)

    assert result["status"] == "rejected"
    assert "step_results" not in result or not result["step_results"]


def test_missing_info_asks_human_and_prepares_again(log):
    graph, calls = build([
        [po(missing=["supplier"])] * 5,
        [po()] * 5,
    ])
    channel = ScriptedChannel([
        {"action": "approve"},                                  # invalid for needs_human
        {"action": "provide_info", "info": {"supplier": "Mühle Schmidt"}},
    ])

    result = run_with_escalation(graph, start("L2"), CONFIG, lambda p: channel)

    assert result["status"] == "executed"
    assert calls["preparer"] == 2
    assert result["facts"]["supplier"] == "Mühle Schmidt"
    assert "error" in channel.payloads[1]          # asked again after invalid answer
    decisions = [r["decision"] for r in log.records.values()]
    assert decisions == ["needs_human", "auto"]


def test_hard_rule_escalates_even_on_l3(log):
    graph, _ = build([[po(supplier="Neu GmbH")] * 5])
    channel = ScriptedChannel([{"action": "approve"}])

    result = run_with_escalation(
        graph, start("L3", facts={"known_suppliers": ["Mühle Schmidt"]}),
        CONFIG, lambda p: channel)

    assert result["status"] == "executed"
    assert channel.payloads[0]["rule_hits"] == ["new_supplier"]
    (record,) = log.records.values()
    assert record["human_action"] == "approve"
    assert record["corrected"] is False
