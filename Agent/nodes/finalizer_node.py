
"""
Implement the Finalizer Node.

The node summarizes every run and closes the process.
It does not call an LLM, so the summary cannot invent results.
"""

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from Agent.state import PlanningState


logger = logging.getLogger(__name__)


FINISHED_STATUSES = ("completed", "skipped")

# Labels for the chat message.
STATUS_LABELS = {
    "completed": "done",
    "skipped": "skipped",
    "pending": "open",
}

HUMAN_LABELS = {
    "approve": "approved",
    "select": "other option selected",
    "edit": "corrected",
    "reject": "rejected",
    "provide_info": "information provided",
}

# Process status in public.process_list per outcome.
# Special case: "incomplete" is stored as CANCELLED (no own status yet).
PROCESS_STATUS = {
    "completed": "COMPLETED",
    "incomplete": "CANCELLED",
    "rejected": "CANCELLED",
    "aborted": "CANCELLED",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def determine_outcome(
    state: PlanningState,
    steps: list[dict[str, Any]]
) -> str:
    """
    Classify the run as completed, incomplete,
    rejected or aborted.

    A skipped last step is reported as incomplete,
    because the last step usually reaches the goal.
    """

    # All steps were executed or skipped.
    if steps and all(s["status"] in FINISHED_STATUSES for s in steps):

        # Special case: last step skipped = goal not confirmed.
        # A skipped step in the middle (e.g. create_customer) is fine.
        if steps[-1]["status"] == "skipped":
            return "incomplete"
        return "completed"

    if state.get("status") == "rejected":
        return "rejected"

    return "aborted"


def abort_reason(state: PlanningState) -> str:
    """
    Explain why the run ended without
    completing the plan.
    """

    status = state.get("status") or "unknown"

    # Special case: the comment comes from the Human Review node.
    if status == "rejected":
        comment = (state.get("governance") or {}).get("human_comment")
        return "Rejected by a human" + (f": {comment}" if comment else ".")

    if status == "needs_human" and state.get("missing_info"):
        return "Missing information: " + ", ".join(state["missing_info"])

    if status == "plan_invalid" and state.get("validation_errors"):
        return "The plan is invalid: " + "; ".join(state["validation_errors"])

    if status == "condition_unknown" and state.get("condition_reason"):
        return "Condition could not be evaluated: " + state["condition_reason"]

    # Special case: a failed step has no own status, the error
    # is only in replan_reason.
    if status == "replan_limit_reached":
        last_error = state.get("replan_reason") or "unknown"
        return ("Not solved even after replanning, a human has to decide. "
                f"Last error: {last_error}")

    if state.get("abort_reason"):
        return state["abort_reason"]

    return f"The run ended with status '{status}'."


def describe_condition(
    step: dict[str, Any],
    step_results: dict[str, Any]
) -> str:
    """
    Describe a step condition with the actual values,
    e.g. "r1_a.item_exists = False (condition: = True)".
    """

    condition = step.get("execution_condition") or {}
    comparisons = (condition.get("all") or []) + (condition.get("any") or [])
    parts = []

    for comparison in comparisons:
        source = comparison.get("source_step")
        field = comparison.get("field")
        result = (step_results.get(source) or {}).get("result") or {}
        actual = result.get(field, "unknown")
        operator = "=" if comparison.get("operator") == "eq" else "!="
        parts.append(
            f"{source}.{field} = {actual} "
            f"(condition: {operator} {comparison.get('value')})"
        )

    return "; ".join(parts)


def incomplete_reason(state: PlanningState, steps: list[dict[str, Any]]) -> str:
    """
    Explain which last step was skipped and why.
    """

    last = steps[-1]
    plan_step = next(
        (s for s in state.get("plan") or [] if s.get("id") == last["id"]), {}
    )
    reason = f"The last step {last['id']} ({last['tool']}) was skipped"
    condition = describe_condition(plan_step, state.get("step_results") or {})

    return reason + (f" because {condition}" if condition else "")


def summarize_steps(state: PlanningState) -> list[dict[str, Any]]:
    """
    Return one entry per plan step with its
    status and result.
    """

    step_results = state.get("step_results") or {}
    steps = []

    for step in state.get("plan") or []:
        # Special case: the executor may only write step_results,
        # so the recorded status is preferred over the plan status.
        record = step_results.get(step.get("id")) or {}
        steps.append({
            "id": step.get("id"),
            "tool": step.get("tool"),
            "description": step.get("description", ""),
            "status": record.get("status") or step.get("status", "pending"),
            "result": record.get("result"),
            "reason": record.get("reason"),
        })

    return steps


def summarize_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Count governance decisions, human reviews
    and replans.
    """

    decisions = Counter()
    human = Counter()
    replans = 0

    for entry in history or []:
        event = entry.get("event")

        if event == "governance_decision":
            decisions[entry.get("decision")] += 1
        elif event == "human_review":
            human[entry.get("answer")] += 1
        elif event == "plan_replanned":
            replans += 1

    return {
        "governance_decisions": dict(decisions),
        "human_reviews": dict(human),
        "replans": replans,
    }


def build_message(
    outcome: str,
    goal: str,
    reason: str | None,
    steps: list[dict[str, Any]],
    counts: dict[str, Any]
) -> str:
    """
    Build the chat message for the employee.
    """

    done = sum(1 for s in steps if s["status"] == "completed")
    skipped = sum(1 for s in steps if s["status"] == "skipped")

    if outcome == "completed":
        head = "Process completed."
    elif outcome == "incomplete":
        head = ("Process finished, but the goal is not confirmed: "
                f"{reason}. Please check.")
    elif outcome == "rejected":
        head = "Process ended: " + (reason or "rejected.")
    else:
        head = "Process aborted: " + (reason or "unknown reason.")

    lines = [head]

    if goal:
        lines.append(f"Goal: {goal}")

    if steps:
        summary = f"{done} of {len(steps)} steps done"
        if skipped:
            summary += f", {skipped} skipped"
        lines.append(summary + ".")

        for s in steps:
            label = STATUS_LABELS.get(s["status"], s["status"])
            line = f"- {s['id']} ({s['tool']}): {label}"

            result = s.get("result")
            if isinstance(result, dict):
                ids = [f"{k}={v}" for k, v in result.items() if k.endswith("_id") and v]
                if ids:
                    line += " [" + ", ".join(ids) + "]"

            lines.append(line)

    parts = []
    decisions = counts["governance_decisions"]
    if decisions.get("auto"):
        parts.append(f"{decisions['auto']}x executed automatically")
    escalated = decisions.get("escalate", 0) + decisions.get("needs_human", 0)
    if escalated:
        parts.append(f"{escalated}x escalated to a human")
    for answer, n in counts["human_reviews"].items():
        parts.append(f"{n}x {HUMAN_LABELS.get(answer, answer)}")
    if counts["replans"]:
        parts.append(f"{counts['replans']}x replanned")

    if parts:
        lines.append("Decisions: " + ", ".join(parts) + ".")

    return "\n".join(lines)


def _update_process_status(process_id: str, status: str) -> None:
    """
    Write the final status into public.process_list.
    """

    # Import lazily, the process manager connects to the database on import.
    from Process.process_manager import update_status

    update_status(process_id, status)


def finalizer(state: PlanningState) -> dict:
    """
    Summarize the run and close the process.
    """

    steps = summarize_steps(state)
    outcome = determine_outcome(state, steps)

    if outcome == "completed":
        reason = None
    elif outcome == "incomplete":
        reason = incomplete_reason(state, steps)
    else:
        reason = abort_reason(state)
    counts = summarize_history(state.get("history") or [])
    goal = state.get("goal") or ""

    # Create the structured summary.
    final_result = {
        "outcome": outcome,
        "goal": goal,
        "reason": reason,
        "last_status": state.get("status"),
        "steps": steps,
        **counts,
        "message": build_message(outcome, goal, reason, steps, counts),
    }

    # Closing the process must not fail because of the database.
    # Special case: without a process_id there is no database update.
    process_id = state.get("process_id")
    process_status = PROCESS_STATUS[outcome]
    db_error = None

    if process_id:
        try:
            _update_process_status(process_id, process_status)
        except Exception as exc:
            db_error = f"{type(exc).__name__}: {exc}"

            # Special case: database error. Logged as a warning so it is
            # not silently lost, the run still ends normally.
            logger.warning(
                "Finalizer could not save status %s for process %s: %s",
                process_status, process_id, db_error
            )

    final_result["process_status"] = process_status if process_id else None
    final_result["process_status_error"] = db_error

    # Return LangGraph state updates.
    return {
        "final_result": final_result,
        "prepared_action": {},
        "status": f"process_{outcome}",
        "history": [{
            "event": "process_finalized",
            "outcome": outcome,
            "reason": reason,
            "last_status": state.get("status"),
            "process_id": process_id,
            "process_status": final_result["process_status"],
            "process_status_error": db_error,
            "timestamp": _now(),
        }]
    }
