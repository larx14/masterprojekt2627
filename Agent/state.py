
"""
Define the preliminary LangGraph state for planning,
validation and conditional action preparation.
"""

import operator
from typing import Annotated, Any, TypedDict


class PlanningState(TypedDict, total=False):

    # Employee instruction and tool definitions
    instruction: str
    available_tools: list[dict[str, Any]]

    # Planning
    goal: str
    proposed_steps: list[dict[str, Any]]
    plan: list[dict[str, Any]]
    current_step: int                   # Very inmportant so tha graph always knows what step it's on 
    missing_info: list[str]
    abort_reason: str

    # Plan validation
    plan_valid: bool
    validation_errors: list[str]

    # Business data and execution history
    facts: dict[str, Any]
    artifacts: dict[str, Any]
    step_results: dict[str, Any]        # Important for conditional routing !! , Tools need to return fields that report the results 

    # Conditional execution
    condition_result: str                       # Based on this it is routed to nodes in the LangGraph, after evalutaion 
    condition_reason: str

    # Action preparation
    prepared_action: dict[str, Any]

    # Workflow status
    status: str

    # Decision history
    history: Annotated[
        list[dict[str, Any]],
        operator.add
    ]
