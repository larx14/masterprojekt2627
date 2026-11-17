
"""
Evaluate structured execution conditions deterministically.

The evaluator uses previously recorded step results.
It does not call an LLM or execute ERPNext tools.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from Agent.models import ExecutionCondition
from Agent.state import PlanningState


ConditionResult = Literal["true", "false", "unknown"]


def evaluate_comparison(
    comparison: dict[str, Any],
    step_results: dict[str, Any]
) -> ConditionResult:
    """
    Evaluate one comparison against a completed step result.
    """

    source = step_results.get(comparison["source_step"])

    if not isinstance(source, dict):
        return "unknown"

    if source.get("status") != "completed":
        return "unknown"

    data = source.get("result")

    if not isinstance(data, dict):
        return "unknown"

    field = comparison["field"]

    if field not in data:
        return "unknown"

    actual = data[field]
    expected = comparison["value"]
    operator = comparison["operator"]

    # Require matching runtime types.
    # bool is a subclass of int in Python.
    if type(actual) is not type(expected):
        if (
            not isinstance(actual, bool)
            and not isinstance(expected, bool)
            and isinstance(actual, (int, float))
            and isinstance(expected, (int, float))
        ):
            pass
        else:
            return "unknown"

    if operator == "eq":
        return "true" if actual == expected else "false"

    if operator == "ne":
        return "true" if actual != expected else "false"

    return "unknown"


def evaluate_all(
    results: list[ConditionResult]
) -> ConditionResult:
    """
    Evaluate a logical AND using three-valued logic.
    """

    if "false" in results:
        return "false"

    if "unknown" in results:
        return "unknown"

    return "true"


def evaluate_any(
    results: list[ConditionResult]
) -> ConditionResult:
    """
    Evaluate a logical OR using three-valued logic.
    """

    if "true" in results:
        return "true"

    if "unknown" in results:
        return "unknown"

    return "false"


def evaluate_execution_condition(
    condition: dict[str, Any] | None,
    step_results: dict[str, Any]
) -> ConditionResult:
    """
    Evaluate an optional structured execution condition.

    An absent condition is treated as unconditional.
    """

    if condition is None:
        return "true"

    try:
        validated = ExecutionCondition.model_validate(condition)
    except Exception:
        return "unknown"

    all_results = [
        evaluate_comparison(
            comparison.model_dump(),
            step_results
        )
        for comparison in validated.all
    ]

    any_results = [
        evaluate_comparison(
            comparison.model_dump(),
            step_results
        )
        for comparison in validated.any
    ]

    # Empty groups impose no restriction.
    all_result = evaluate_all(all_results)

    any_result = (
        evaluate_any(any_results)
        if any_results
        else "true"
    )

    return evaluate_all([all_result, any_result])


def condition_evaluator(state: PlanningState) -> dict:
    """
    Determine whether the current plan step should
    execute, be skipped, or require resolution.
    """

    def outcome(result: str, reason: str, step_id=None):
        return {
            "condition_result": result,
            "condition_reason": reason,
            "prepared_action": {},
            "status": (
                "condition_met" if result == "true"
                else "condition_not_met" if result == "false"
                else "condition_unknown"
            ),
            "history": [{
                "event": "condition_evaluated",
                "step_id": step_id,
                "result": result,
                "reason": reason,
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat()
            }]
        }

    if state.get("plan_valid") is not True:
        return outcome(
            "unknown",
            "The plan has not been validated."
        )

    plan = state.get("plan", [])
    current = state.get("current_step", 0)

    if (
        not isinstance(current, int)
        or isinstance(current, bool)
        or current < 0
    ):
        return outcome(
            "unknown",
            "The current step index is invalid."
        )

    if current >= len(plan):
        return {
            "status": "plan_exhausted",
            "condition_result": "unknown",
            "condition_reason": "No remaining plan steps.",
            "prepared_action": {}
        }

    step = plan[current]
    step_id = step["id"]
    step_results = state.get("step_results", {})

    if step.get("status", "pending") != "pending":
        return outcome(
            "unknown",
            "The current step is not pending.",
            step_id
        )

    # All prerequisites must have reached a terminal state.
    for dependency in step.get("depends_on", []):
        record = step_results.get(dependency, {})
        dependency_status = record.get("status")

        if dependency_status not in ("completed", "skipped"):
            return outcome(
                "unknown",
                f"Dependency '{dependency}' is not resolved.",
                step_id
            )

    result = evaluate_execution_condition(
        step.get("execution_condition"),
        step_results
    )

    reason = {
        "true": "The execution condition is satisfied.",
        "false": "The execution condition is not satisfied.",
        "unknown": (
            "The execution condition cannot be determined "
            "from the available step results."
        )
    }[result]

    return outcome(result, reason, step_id)
