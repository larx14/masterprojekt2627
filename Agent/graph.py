"""
Preliminary graph with the nodes already implemented 


from typing import Literal

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState
from Agent.nodes.planner_node import planner
from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.condition_evaluator_node import condition_evaluator
from Agent.nodes.skip_step_node import skip_step
from Agent.nodes.action_preparer_node import action_preparer
from Agent.nodes.replanner_node import replanner, route_after_replanner
from Agent.nodes.finalizer_node import finalizer


def route_after_planner(
    state: PlanningState
) -> Literal["validate", "stop"]:

    if state.get("status") == "planned":
        return "validate"

    return "stop"


def route_after_validation(
    state: PlanningState
) -> Literal["conditions", "replan", "stop"]:

    if state.get("plan_valid") is True:
        return "conditions"

    # An invalid revised plan is revised again.
    if (state.get("replan_count") or 0) > 0 and state.get("status") == "plan_invalid":
        return "replan"

    return "stop"


def route_after_condition(
    state: PlanningState
) -> Literal["prepare", "skip", "stop"]:

    result = state.get("condition_result")

    if result == "true":
        return "prepare"

    if result == "false":
        return "skip"

    return "stop"


def build_planning_graph(checkpointer=None):
    
   # Build and compile the preliminary planning graph.
  

    builder = StateGraph(PlanningState)

    builder.add_node("planner", planner)
    builder.add_node("plan_validator", plan_validator)
    builder.add_node("condition_evaluator", condition_evaluator)
    builder.add_node("skip_step", skip_step)
    builder.add_node("action_preparer", action_preparer)
    builder.add_node("replanner", replanner)
    builder.add_node("finalizer", finalizer)

    builder.add_edge(START, "planner")

    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "validate": "plan_validator",
            "stop": "finalizer"
        }
    )

    builder.add_conditional_edges(
        "plan_validator",
        route_after_validation,
        {
            "conditions": "condition_evaluator",
            "replan": "replanner",
            "stop": "finalizer"
        }
    )

    builder.add_conditional_edges(
        "condition_evaluator",
        route_after_condition,
        {
            "prepare": "action_preparer",
            "skip": "skip_step",
            "stop": "finalizer"
        }
    )

    # Re-evaluate the next step after skipping.
    builder.add_edge("skip_step", "condition_evaluator")

    # Validate a revised plan again.
    builder.add_conditional_edges(
        "replanner",
        route_after_replanner,
        {
            "validate": "plan_validator",
            "stop": "finalizer"
        }
    )

    # Stop after preparing one action.
    builder.add_edge("action_preparer", END)

    # Summarize every run before it ends.
    builder.add_edge("finalizer", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_planning_graph()

from pathlib import Path

output_path = Path("planning_graph.png")

png_data = graph.get_graph().draw_mermaid_png()
output_path.write_bytes(png_data)

print(f"Graph saved to: {output_path.resolve()}")

""" 



"""
Complete governance-aware planning and execution graph.
"""

from pathlib import Path
from typing import Literal

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState

from Agent.nodes.planner_node import planner
from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.condition_evaluator_node import condition_evaluator
from Agent.nodes.skip_step_node import skip_step
from Agent.nodes.action_preparer_node import action_preparer
from Agent.nodes.replanner_node import replanner, route_after_replanner
from Agent.nodes.finalizer_node import finalizer

from Agent.nodes.governance_gate_node import governance_gate
from Agent.nodes.human_review_node import human_review
from Agent.nodes.executor_node import executor
from Agent.nodes.evaluator_node import evaluator
from Agent.nodes.responder_node import responder

from functools import partial

from Agent.tools.register_tools import create_tool_registry

tool_registry = create_tool_registry()


from Agent.nodes.governance_gate_node import (
    governance_gate,
    route_after_governance,
)

from Agent.nodes.human_review_node import (
    human_review,
    route_after_review,
)
# --------------------------------------------------
# Routing functions
# --------------------------------------------------

def route_after_planner(
    state: PlanningState
) -> Literal["validate", "stop"]:

    if state.get("status") == "planned":
        return "validate"

    return "stop"


def route_after_validation(
    state: PlanningState
) -> Literal["conditions", "replan", "stop"]:

    if state.get("plan_valid") is True:
        return "conditions"

    if (
        (state.get("replan_count") or 0) > 0
        and state.get("status") == "plan_invalid"
    ):
        return "replan"

    return "stop"


def route_after_condition(
    state: PlanningState
) -> Literal["prepare", "skip", "stop"]:

    result = state.get("condition_result")

    if result == "true":
        return "prepare"

    if result == "false":
        return "skip"

    return "stop"



def route_after_human_review(
    state: PlanningState
) -> Literal["execute", "prepare", "stop"]:

    decision = state.get("human_decision")

    if decision == "approved":
        return "execute"

    if decision == "revised":
        return "prepare"

    return "stop"


def route_after_evaluator(
    state: PlanningState
) -> Literal["next", "replan", "stop"]:

    result = state.get("evaluation_result")

    if result == "next":
        return "next"

    if result == "replan":
        return "replan"

    return "stop"


# --------------------------------------------------
# Graph construction
# --------------------------------------------------

def build_planning_graph(checkpointer=None):
    """
    Build and compile the complete governance-aware graph.
    """

    builder = StateGraph(PlanningState)

    # Register nodes
    builder.add_node("planner", planner)
    builder.add_node("plan_validator", plan_validator)
    builder.add_node("condition_evaluator", condition_evaluator)
    builder.add_node("skip_step", skip_step)
    builder.add_node("action_preparer", action_preparer)

    builder.add_node("governance_gate", governance_gate)
    builder.add_node("human_review", human_review)
    builder.add_node(
    "executor",
    partial(
        executor,
        registry=tool_registry.get_executors()
    )
    )
    builder.add_node("evaluator", evaluator)

    builder.add_node("replanner", replanner)
    builder.add_node("finalizer", finalizer)
    builder.add_node("responder", responder)

    # Entry point
    builder.add_edge(START, "planner")

    # Planner routing
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "validate": "plan_validator",
            "stop": "finalizer",
        }
    )

    # Plan validation
    builder.add_conditional_edges(
        "plan_validator",
        route_after_validation,
        {
            "conditions": "condition_evaluator",
            "replan": "replanner",
            "stop": "finalizer",
        }
    )

    # Condition evaluation
    builder.add_conditional_edges(
        "condition_evaluator",
        route_after_condition,
        {
            "prepare": "action_preparer",
            "skip": "skip_step",
            "stop": "finalizer",
        }
    )

    # Skip current step and evaluate next step
    builder.add_edge(
        "skip_step",
        "condition_evaluator"
    )

    # Prepare action and check authorization
    builder.add_edge(
        "action_preparer",
        "governance_gate"
    )

    # Governance decisions
    builder.add_conditional_edges(
        "governance_gate",
        route_after_governance,
        {
            "execute": "executor",
            "review": "human_review",
            "sample": "action_preparer",
            "stop": "finalizer",
        }
)

    # Human approval
    builder.add_conditional_edges(
    "human_review",
    route_after_review,
    {
        "execute": "executor",
        "prepare": "action_preparer",
        "stop": "finalizer",
    }
)

    # Execute approved action
    builder.add_edge(
        "executor",
        "evaluator"
    )

    # Evaluate execution result
    builder.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "next": "condition_evaluator",
            "replan": "replanner",
            "stop": "finalizer",
        }
    )

    # Replanning
    builder.add_conditional_edges(
        "replanner",
        route_after_replanner,
        {
            "validate": "plan_validator",
            "stop": "finalizer",
        }
    )

    # Finalization
    builder.add_edge("finalizer", "responder")
    builder.add_edge("responder", END)

    return builder.compile(checkpointer=checkpointer)


# Graph wird direkt beim Import erstellt
graph = build_planning_graph()


if __name__ == "__main__":
    print("Graph erfolgreich erstellt")

    output_path = Path("planning_graph_full.png")

    graph.get_graph().draw_mermaid_png(
        output_file_path=str(output_path)
    )

    print(f"Graph saved to: {output_path.resolve()}")
