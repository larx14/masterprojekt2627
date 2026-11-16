
"""
Implement the generic Action Preparer Node.

The node prepares arguments for exactly one plan step.
It does not execute tools or evaluate execution conditions.
"""

import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser

from Agent.models import PreparedAction
from Agent.state import PlanningState
from config.llm_connection import get_deepseek


llm = get_deepseek()


ACTION_PREPARER_PROMPT = """
You are the Action Preparer of a generic ERPNext AI agent.

Your responsibility is to prepare the arguments for exactly
one tool invocation based on a validated execution plan.

EMPLOYEE INSTRUCTION:
{instruction}

BUSINESS GOAL:
{goal}

CURRENT PLAN STEP:
{step}

SELECTED TOOL SPECIFICATION:
{tool}

KNOWN BUSINESS FACTS:
{facts}

EXISTING ERP DOCUMENTS:
{artifacts}

RESULTS OF PREVIOUS STEPS:
{step_results}

RULES:

1. Prepare arguments exclusively for the tool specified
   in the current plan step.

2. Use the exact tool name and parameter names from
   the selected tool specification.

3. Use only information explicitly provided in the
   instruction or available in the supplied context.

4. Prefer verified results from previous steps when
   selecting ERPNext identifiers and document references.

5. Do not invent customer identifiers, item codes,
   suppliers, quantities, prices, dates, document
   names, or any other business data.

6. Do not invent default values unless they are
   explicitly defined in the available information.

7. If required arguments cannot be determined,
   report them in missing_info.

8. Do not guess missing argument values.

9. Include only arguments defined by the tool specification.

10. Briefly explain the source and justification
    of the selected argument values in reason.

11. Report your confidence as a value between 0 and 1.
    This is a self-assessment, not a guarantee of correctness.

12. Do not execute the tool.

13. Do not evaluate execution conditions.
    Conditional execution is handled by a downstream component.

14. Do not modify the plan or select another plan step.

OUTPUT REQUIREMENTS:

Return a single JSON object matching the schema below.
Do not include additional explanations.

JSON SCHEMA:
{schema}
"""


def validate_arguments(
    args: dict[str, Any],
    parameters: dict[str, str]
) -> list[str]:
    """
    Validate argument names and simple parameter types.

    The current prototype uses mock tool specifications
    with parameter types represented as strings.
    """

    errors = []

    expected_types = {
        "str": str,
        "int": int,
        "float": (int, float),
        "bool": bool,
        "list": list,
        "dict": dict,
    }

    for name in args:
        if name not in parameters:
            errors.append(
                f"Unknown argument '{name}'."
            )

    for name, type_name in parameters.items():
        if type_name not in expected_types:
            errors.append(
                f"Unsupported parameter type '{type_name}' "
                f"for argument '{name}'."
            )
            continue

        if name not in args:
            errors.append(
                f"Missing required argument '{name}'."
            )
            continue

        value = args[name]
        expected_type = expected_types[type_name]

        # Booleans must not be accepted as numeric values.
        if type_name in ("int", "float") and isinstance(value, bool):
            errors.append(
                f"Argument '{name}' must be of type '{type_name}'."
            )
            continue

        if not isinstance(value, expected_type):
            errors.append(
                f"Argument '{name}' must be of type '{type_name}'."
            )

    return errors


def action_preparer(state: PlanningState) -> dict:
    """
    Prepare a single tool invocation from the current
    validated plan step and available context.
    """

    def make_event(event: str, **details) -> dict:
        """
        Create a timestamped decision log entry.
        """

        return {
            "event": event,
            **details,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat()
        }

    def reject(reason: str, status: str = "action_invalid") -> dict:
        """
        Return a failed preparation result without
        forwarding an executable action.
        """

        return {
            "prepared_action": {},
            "status": status,
            "history": [
                make_event(
                    "action_preparation_failed",
                    reason=reason,
                    status=status
                )
            ]
        }

    # Require a plan approved by the Plan Validator.
    if state.get("plan_valid") is not True:
        return reject(
            "The execution plan has not been validated."
        )

    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)

    if not isinstance(current_step, int) or isinstance(current_step, bool):
        return reject("The current step index is invalid.")

    if not isinstance(plan, list) or not 0 <= current_step < len(plan):
        return reject("No valid current plan step is available.")

    step = plan[current_step]
    tool_name = step.get("tool")

    # Locate the tool specification for the current step.
    matching_tools = [
        tool
        for tool in state.get("available_tools", [])
        if isinstance(tool, dict)
        and tool.get("name") == tool_name
    ]

    if len(matching_tools) != 1:
        return reject(
            f"Exactly one specification is required "
            f"for tool '{tool_name}'."
        )

    selected_tool = matching_tools[0]
    parameters = selected_tool.get("parameters")

    if not isinstance(parameters, dict):
        return reject(
            f"Tool '{tool_name}' has no valid parameter specification."
        )

    # Validate the mock tool specification.
    if not all(
        isinstance(name, str)
        and isinstance(type_name, str)
        for name, type_name in parameters.items()
    ):
        return reject("Invalid parameter specification.")

    parser = PydanticOutputParser(
        pydantic_object=PreparedAction
    )

    prompt = ACTION_PREPARER_PROMPT.format(
        instruction=state.get("instruction", ""),
        goal=state.get("goal", ""),
        step=json.dumps(
            step, ensure_ascii=False, indent=2
        ),
        tool=json.dumps(
            selected_tool, ensure_ascii=False, indent=2
        ),
        facts=json.dumps(
            state.get("facts", {}), ensure_ascii=False
        ),
        artifacts=json.dumps(
            state.get("artifacts", {}), ensure_ascii=False
        ),
        step_results=json.dumps(
            state.get("step_results", {}), ensure_ascii=False
        ),
        schema=parser.get_format_instructions()
    )

    # Ask the LLM to prepare arguments without tool execution.
    try:
        structured_llm = llm.with_structured_output(
            PreparedAction,
            method="json_mode",
            include_raw=True
        )

        response = structured_llm.invoke(prompt)
        action = response.get("parsed")

        if action is None:
            return reject(
                "The LLM returned an invalid structured action: "
                f"{response.get('parsing_error')}"
            )

    except Exception as exc:
        return reject(
            "The LLM request failed: "
            f"{type(exc).__name__}: {exc}"
        )

    # The model must not switch to another tool.
    if action.tool != tool_name:
        return reject(
            f"Prepared tool '{action.tool}' does not "
            f"match planned tool '{tool_name}'."
        )

    # Missing information must not be replaced by guesses.
    if action.missing_info:
        return {
            "prepared_action": {},
            "missing_info": action.missing_info,
            "status": "needs_human",
            "history": [
                make_event(
                    "action_missing_information",
                    step_id=step["id"],
                    tool=tool_name,
                    missing_info=action.missing_info,
                    reason=action.reason
                )
            ]
        }

    # Validate the prepared arguments against the mock schema.
    errors = validate_arguments(
        action.args,
        parameters
    )

    if errors:
        return {
            "prepared_action": {},
            "status": "action_invalid",
            "history": [
                make_event(
                    "action_validation_failed",
                    step_id=step["id"],
                    tool=tool_name,
                    errors=errors,
                    proposed_args=action.args
                )
            ]
        }

    prepared_action = {
        "step_id": step["id"],
        "tool": tool_name,
        "args": action.args,
        "reason": action.reason,
        "confidence": action.confidence
    }

    # Return a proposed action for downstream validation.
    return {
        "prepared_action": prepared_action,
        "missing_info": [],
        "status": "action_prepared",
        "history": [
            make_event(
                "action_prepared",
                **prepared_action
            )
        ]
    }
