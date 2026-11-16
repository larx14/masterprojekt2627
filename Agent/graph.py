"""
Preliminary graph with the nodes already implemented 
"""

from typing import Literal

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState
from Agent.nodes.planner_node import planner
from Agent.nodes.plan_validator_node import plan_validator



from typing import Literal

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState
from Agent.nodes.planner_node import planner
from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.action_preparer_node import action_preparer


def route_after_planner(
    state: PlanningState
) -> Literal["validate", "end"]:
    """
    Route successful planning results to the validator.
    """

    if state.get("status") == "planned":
        return "validate"

    return "end"


def route_after_validation(
    state: PlanningState
) -> Literal["prepare", "end"]:
    """
    Prepare an action only after successful validation.
    """

    if (
        state.get("status") == "plan_valid"
        and state.get("plan_valid") is True
    ):
        return "prepare"

    return "end"


def build_planning_graph(checkpointer=None):
    """
    Build and compile the preliminary agent graph.
    """

    builder = StateGraph(PlanningState)

    builder.add_node("planner", planner)
    builder.add_node("plan_validator", plan_validator)
    builder.add_node("action_preparer", action_preparer)

    builder.add_edge(START, "planner")

    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "validate": "plan_validator",
            "end": END
        }
    )

    builder.add_conditional_edges(
        "plan_validator",
        route_after_validation,
        {
            "prepare": "action_preparer",
            "end": END
        }
    )

    builder.add_edge("action_preparer", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_planning_graph()