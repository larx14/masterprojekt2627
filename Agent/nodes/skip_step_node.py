
"""
Skip a plan step whose execution condition is false.
"""

from copy import deepcopy
from datetime import datetime, timezone

from Agent.state import PlanningState


def skip_step(state: PlanningState) -> dict:
    """
    Mark the current step as skipped and advance
    to the next plan step.
    """

    if state.get("condition_result") != "false":
        return {
            "status": "condition_unknown",
            "history": [{
                "event": "skip_rejected",
                "reason": "No false condition was recorded."
            }]
        }

    plan = deepcopy(state.get("plan", []))
    current = state.get("current_step", 0)

    if not isinstance(current, int) or isinstance(current, bool):
        return {
            "status": "condition_unknown",
            "history": [{
                "event": "skip_rejected",
                "reason": "Invalid current step index."
            }]
        }

    if not 0 <= current < len(plan):
        return {
            "status": "condition_unknown",
            "history": [{
                "event": "skip_rejected",
                "reason": "Current step is out of range."
            }]
        }

    step = plan[current]

    if step.get("status", "pending") != "pending":
        return {
            "status": "condition_unknown",
            "history": [{
                "event": "skip_rejected",
                "reason": "The current step is not pending."
            }]
        }

    step["status"] = "skipped"

    step_results = deepcopy(
        state.get("step_results", {})
    )

    step_results[step["id"]] = {
        "status": "skipped",
        "result": None,
        "reason": state.get("condition_reason", "")
    }

    return {
        "plan": plan,
        "step_results": step_results,
        "current_step": current + 1,
        "prepared_action": {},
        "status": "step_skipped",
        "history": [{
            "event": "step_skipped",
            "step_id": step["id"],
            "reason": state.get("condition_reason", ""),
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat()
        }]
    }
