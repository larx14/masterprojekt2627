
import operator
from typing import Annotated, TypedDict, Any

"""
This is a prelimaniry state only used for testing, not the final AgentState
"""

"""
Define the preliminary LangGraph state for planning,
plan validation, and action preparation.

This is not the final AgentState of the ERPNext agent.
"""

import operator

from typing import Annotated, Any, TypedDict


class PlanningState(TypedDict, total=False):

    # Employee instruction and available capabilities
    instruction: str
    available_tools: list[dict[str, Any]]

    # Planning results
    goal: str
    proposed_steps: list[dict[str, Any]]
    plan: list[dict[str, Any]]
    current_step: int

    # Planning limitations
    missing_info: list[str]
    abort_reason: str

    # Plan validation
    plan_valid: bool
    validation_errors: list[str]

    # Data obtained during previous execution steps
    facts: dict[str, Any]
    artifacts: dict[str, Any]
    step_results: dict[str, Any]

    # Action preparation for action preparer node 
    prepared_action: dict[str, Any] 

    # Workflow status
    status: str

    # Decision history
    history: Annotated[
        list[dict[str, Any]],
        operator.add
    ]

