"""
Preliminary graph with the nodes already implemented 
"""

from typing import Literal

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState
from Agent.nodes.planner_node import planner
from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.condition_evaluator_node import condition_evaluator
from Agent.nodes.skip_step_node import skip_step
from Agent.nodes.action_preparer_node import action_preparer


def route_after_planner(
    state: PlanningState
) -> Literal["validate", "stop"]:

    if state.get("status") == "planned":
        return "validate"

    return "stop"


def route_after_validation(
    state: PlanningState
) -> Literal["conditions", "stop"]:

    if state.get("plan_valid") is True:
        return "conditions"

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
    """
    Build and compile the preliminary planning graph.
    """

    builder = StateGraph(PlanningState)

    builder.add_node("planner", planner)
    builder.add_node("plan_validator", plan_validator)
    builder.add_node("condition_evaluator", condition_evaluator)
    builder.add_node("skip_step", skip_step)
    builder.add_node("action_preparer", action_preparer)

    builder.add_edge(START, "planner")

    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "validate": "plan_validator",
            "stop": END
        }
    )

    builder.add_conditional_edges(
        "plan_validator",
        route_after_validation,
        {
            "conditions": "condition_evaluator",
            "stop": END
        }
    )

    builder.add_conditional_edges(
        "condition_evaluator",
        route_after_condition,
        {
            "prepare": "action_preparer",
            "skip": "skip_step",
            "stop": END
        }
    )

    # Re-evaluate the next step after skipping.
    builder.add_edge("skip_step", "condition_evaluator")

    # Stop after preparing one action.
    builder.add_edge("action_preparer", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_planning_graph()