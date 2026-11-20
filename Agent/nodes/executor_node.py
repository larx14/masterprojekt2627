
"""
Execute exactly one authorized ERPNext tool action.

The Executor receives an action selected by Governance.
It does not use an LLM, modify plans, or evaluate
business process conditions.
"""

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping

from Agent.state import PlanningState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(event: str, **details: Any) -> dict[str, Any]:
    return {
        "event": event,
        **details,
        "timestamp": _now(),
    }


def _identity(action: dict[str, Any]) -> dict[str, Any]:
    """
    Extract the fields identifying an executable action.
    """
    return {
        "step_id": action.get("step_id"),
        "tool": action.get("tool"),
        "args": action.get("args"),
    }


def _is_authorized(
    state: PlanningState,
    action: dict[str, Any],
) -> bool:
    """
    Verify that Governance authorized the exact action.

    Human approval requires an explicit final_action
    contract from the Human Review node.
    """

    governance = state.get("governance") or {}
    status = state.get("status")

    if status == "auto":
        if governance.get("decision") != "auto":
            return False

        approved = governance.get("final_action")
        return (
            isinstance(approved, dict)
            and _identity(approved) == _identity(action)
        )

    if status == "approved":
        if governance.get("human_action") not in (
            "approve",
            "select",
            "edit",
        ):
            return False

        approved = governance.get("final_action")

        return (
            isinstance(approved, dict)
            and _identity(approved) == _identity(action)
        )

    return False


def _normalize_result(
    raw_result: Any,
    specification: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate and normalize business fields returned by a tool.

    The prototype supports simple result_fields declarations.
    """

    if not isinstance(raw_result, dict):
        raise TypeError(
            "Tool output must be a dictionary."
        )

    if raw_result.get("success") is False:
        raise RuntimeError(
            str(
                raw_result.get("error")
                or "The tool reported an unsuccessful operation."
            )
        )

    if raw_result.get("error"):
        raise RuntimeError(str(raw_result["error"]))

    fields = specification.get("result_fields")

    if not isinstance(fields, dict):
        raise ValueError(
            "The tool specification must declare result_fields."
        )

    types = {
        "str": str,
        "bool": bool,
        "int": int,
        "float": (int, float),
        "list": list,
        "dict": dict,
    }

    normalized = {}

    for name, declared_type in fields.items():
        if name not in raw_result:
            continue

        value = raw_result[name]
        expected_type = types.get(declared_type)

        if expected_type is None:
            raise ValueError(
                f"Unsupported result type: {declared_type}"
            )

        if not isinstance(value, expected_type):
            raise TypeError(
                f"Invalid type for result field '{name}'."
            )

        if (
            declared_type in ("int", "float")
            and isinstance(value, bool)
        ):
            raise TypeError(
                f"Invalid numeric value for field '{name}'."
            )

        normalized[name] = deepcopy(value)

    return normalized


def executor(
    state: PlanningState,
    *,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Invoke one authorized tool and record its result.

    The Evaluator handles business success, plan progress,
    failure recovery, and selection of the next step.
    """

    plan = state.get("plan") or []
    current = state.get("current_step", 0)

    action = state.get("prepared_action") or {}
    results = deepcopy(state.get("step_results") or {})

    def blocked(reason: str) -> dict[str, Any]:
        return {
            "status": "execution_blocked",
            "execution_error": reason,
            "history": [
                _event("execution_blocked", reason=reason)
            ],
        }

    if state.get("plan_valid") is not True:
        return blocked("The plan has not been validated.")

    if (
        not isinstance(current, int)
        or isinstance(current, bool)
        or not 0 <= current < len(plan)
    ):
        return blocked("Invalid current step index.")

    step = plan[current]
    step_id = step.get("id")
    tool_name = step.get("tool")

    if step.get("status", "pending") != "pending":
        return blocked("The current step is not pending.")

    if step_id in results:
        return blocked(
            f"Step '{step_id}' already has an execution record."
        )

    if (
        not isinstance(action, dict)
        or action.get("step_id") != step_id
        or action.get("tool") != tool_name
        or not isinstance(action.get("args"), dict)
    ):
        return blocked(
            "The prepared action does not match the current step."
        )

    if not _is_authorized(state, action):
        return blocked(
            "Governance has not authorized this exact action."
        )

    specification = next(
        (
            item
            for item in state.get("available_tools", [])
            if (
                isinstance(item, dict)
                and item.get("name") == tool_name
            )
        ),
        None,
    )

    if specification is None:
        return blocked(
            f"Tool '{tool_name}' is not in the tool catalog."
        )

    tool = registry.get(tool_name)

    if tool is None:
        return blocked(
            f"Tool '{tool_name}' is not registered."
        )

    if not callable(getattr(tool, "invoke", None)):
        return blocked(
            f"Tool '{tool_name}' does not support invoke()."
        )

    try:
        raw_result = tool.invoke(deepcopy(action["args"]))

        normalized = _normalize_result(
            raw_result,
            specification,
        )

        results[step_id] = {
            "status": "completed",
            "result": normalized,
            "reason": "Tool invocation succeeded.",
        }

        return {
            "step_results": results,
            "prepared_action": {},
            "candidates": [],
            "n_requested": 0,
            "execution_error": "",
            "status": "execution_succeeded",
            "history": [
                _event(
                    "tool_executed",
                    step_id=step_id,
                    tool=tool_name,
                    status="completed",
                )
            ],
        }

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

        results[step_id] = {
            "status": "failed",
            "result": None,
            "reason": error,
        }

        return {
            "step_results": results,
            "prepared_action": {},
            "candidates": [],
            "n_requested": 0,
            "execution_error": error,
            "status": "execution_failed",
            "history": [
                _event(
                    "tool_execution_failed",
                    step_id=step_id,
                    tool=tool_name,
                    error=error,
                )
            ],
        }
