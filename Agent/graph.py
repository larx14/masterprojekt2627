"""
Preliminary graph with the nodes already implemented 
"""

from typing import Literal

from langgraph.graph import StateGraph, START, END

from Agent.state import PlanningState
from Agent.nodes.planner_node import planner
from Agent.nodes.plan_validator_node import plan_validator


def route_after_planner(
    state: PlanningState
) -> Literal["validate", "end"]:
    """
    Route successfully planned tasks to the Plan Validator.

    Stop the workflow if planning failed or requires
    additional human information.
    """

    if state.get("status") == "planned":
        return "validate"

    return "end"


def build_planning_graph(checkpointer=None):
    """
    Build and compile the planning workflow.

    An optional checkpointer can be provided by
    the application's database integration.
    """

    builder = StateGraph(PlanningState)

    # Register the independent nodes.
    builder.add_node("planner", planner)
    builder.add_node("plan_validator", plan_validator)

    # Define the entry point.
    builder.add_edge(START, "planner")

    # Validate only successfully generated plans.
    builder.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "validate": "plan_validator",
            "end": END,
        }
    )

    # Stop after plan validation.
    builder.add_edge("plan_validator", END)

    return builder.compile(checkpointer=checkpointer)


graph = build_planning_graph()
