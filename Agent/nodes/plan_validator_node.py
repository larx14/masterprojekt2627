"""
Validate business process plans deterministically.

 Important: This node has no claim to validate correctness from a business perspective, but ony if the plan is structurally correct. 

No LLM or ERPNext connection is required.
"""

from datetime import datetime, timezone

from pydantic import ValidationError

from Agent.models import PlanStep
from Agent.state import PlanningState


PYTHON_TYPES = {
    "str": str,
    "bool": bool,
    "int": int,
    "float": (int, float),
}


def plan_validator(state: PlanningState) -> dict:
    """
    Validate the plan structure, dependencies, tool
    references and execution conditions.
    """

    if state.get("status") != "planned":
     return {
        "plan_valid": False,
        "status": state.get("status", "planning_failed"),
        "validation_errors": [],
        "history": [{
            "event": "plan_validation_skipped",
            "reason": "Planning was not successful.",
            "planning_status": state.get("status"),
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat()
        }]
    }

    errors = []
    raw_plan = state.get("plan", [])
    raw_tools = state.get("available_tools", [])

    if not isinstance(raw_plan, list) or not raw_plan:
        errors.append("The plan must contain at least one step.")
        raw_plan = []

    if not isinstance(raw_tools, list):
        errors.append("The tool catalog must be a list.")
        raw_tools = []

    if state.get("missing_info"):
        errors.append("Required information is missing.")

    if state.get("abort_reason"):
        errors.append("The planner reported an abort reason.")

    # Validate tool catalog entries.
    tools = {}

    for tool in raw_tools:
        if not isinstance(tool, dict):
            errors.append("Invalid tool catalog entry.")
            continue

        name = tool.get("name")

        if not isinstance(name, str) or not name.strip():
            errors.append("Tool name must be a non-empty string.")
            continue

        if name in tools:
            errors.append(f"Duplicate tool name: {name}")

        tools[name] = tool

    # Validate all steps against the Pydantic model.
    steps = []

    for index, raw_step in enumerate(raw_plan):
        try:
            step = PlanStep.model_validate(raw_step)
            steps.append(step)
        except ValidationError as exc:
            errors.append(
                f"Invalid step at index {index}: {exc}"
            )
            steps.append(None)

    positions = {}

    for index, step in enumerate(steps):
        if step is None:
            continue

        if not step.id.strip():
            errors.append("Step ID cannot be empty.")
            continue

        if step.id in positions:
            errors.append(f"Duplicate step ID: {step.id}")
        else:
            positions[step.id] = index

    # Check tools and dependencies.
    for index, step in enumerate(steps):
        if step is None:
            continue

        if not step.tool.strip() or step.tool not in tools:
            errors.append(
                f"Unknown tool '{step.tool}' in step '{step.id}'."
            )

        if not step.description.strip():
            errors.append(
                f"Missing description in step '{step.id}'."
            )

        if not step.reason.strip():
            errors.append(
                f"Missing reason in step '{step.id}'."
            )

        if len(step.depends_on) != len(set(step.depends_on)):
            errors.append(
                f"Duplicate dependencies in step '{step.id}'."
            )

        for dependency in step.depends_on:
            if dependency not in positions:
                errors.append(
                    f"Unknown dependency '{dependency}' "
                    f"in step '{step.id}'."
                )
            elif positions[dependency] >= index:
                errors.append(
                    f"Dependency '{dependency}' must precede "
                    f"step '{step.id}'."
                )

        if step.execution_condition is None:
            continue

        condition = step.execution_condition
        comparisons = condition.all + condition.any

        for comparison in comparisons:
            source_id = comparison.source_step

            # Require explicit control-flow dependency.
            if source_id not in step.depends_on:
                errors.append(
                    f"Condition source '{source_id}' must be "
                    f"listed in depends_on for step '{step.id}'."
                )

            if source_id not in positions:
                errors.append(
                    f"Unknown condition source '{source_id}' "
                    f"in step '{step.id}'."
                )
                continue

            source_index = positions[source_id]

            if source_index >= index:
                errors.append(
                    f"Condition source '{source_id}' must "
                    f"precede step '{step.id}'."
                )
                continue

            source_step = steps[source_index]

            if source_step is None:
                errors.append(
                    f"Invalid condition source '{source_id}'."
                )
                continue

            source_tool = tools.get(source_step.tool)

            if source_tool is None:
                errors.append(
                    f"Unknown source tool '{source_step.tool}'."
                )
                continue

            fields = source_tool.get("result_fields")

            if not isinstance(fields, dict):
                errors.append(
                    f"Tool '{source_step.tool}' must declare "
                    "result_fields for conditional execution."
                )
                continue

            field_type = fields.get(comparison.field)

            if field_type is None:
                errors.append(
                    f"Unknown result field '{comparison.field}' "
                    f"for tool '{source_step.tool}'."
                )
                continue

            expected_type = PYTHON_TYPES.get(field_type)

            if expected_type is None:
                errors.append(
                    f"Unsupported result field type '{field_type}'."
                )
                continue

            value = comparison.value

            # Avoid accepting bool as int or float.
            is_numeric = field_type in ("int", "float")

            if (
                not isinstance(value, expected_type)
                or (is_numeric and isinstance(value, bool))
            ):
                errors.append(
                    f"Condition value type mismatch for "
                    f"'{comparison.field}' in step '{step.id}'."
                )

    valid = len(errors) == 0
    result_status = "plan_valid" if valid else "plan_invalid"

    return {
        "plan_valid": valid,
        "validation_errors": errors,
        "status": result_status,
        "history": [{
            "event": "plan_validated",
            "valid": valid,
            "errors": errors,
            "step_count": len(raw_plan),
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat()
        }]
    }
