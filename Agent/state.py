
"""
Define the preliminary LangGraph state for planning,
validation and conditional action preparation.
"""

import operator
from typing import Annotated, Any, TypedDict
from Governance.state_fields import GovernanceFields
from typing import Any, NotRequired
from typing import Literal, NotRequired

class PlanningState(GovernanceFields, total=False):

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

    # Replanning
    replan_count: int                   # Number of plan revisions so far (max. 2)
    replan_reason: str                  # Why the plan must be revised, set by the Evaluator

    # Execution
    execution_error: str

   

    # Final summary
    final_result: dict[str, Any]        # Outcome, step overview and chat message of the Finalizer
    process_id: str                     # process_list.id, the Finalizer sets the final status

    # Decision history
    history: Annotated[
        list[dict[str, Any]],
        operator.add]

    # Expected state and verification result for "evaluator.node". So it can compare "IST vs SOLL" and report differences.
    expected_state: dict[str, Any]
    verification_result: dict[str, Any]

    available_tools: NotRequired[list[dict[str, Any]]]
     
    evaluation_result: NotRequired[
        Literal["next", "replan", "completed", "stop"]
     ]