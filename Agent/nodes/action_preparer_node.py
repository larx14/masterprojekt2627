
"""
Implement the generic Action Preparer Node.

The node prepares arguments for exactly one plan step.
The Action Preparer generates one or more LLM candidates.
It does not select an action, execute tools, or approve
ERPNext operations.
"""

import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser

from Agent.models import PreparedAction
from Agent.state import PlanningState
from config.llm_connection import get_deepseek

from Governance.config import get_config
from Governance.risk import initial_samples


# llm = get_deepseek()


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

TODAY:
{today}

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


15. Dates without a year refer to the current year (see TODAY).
    If no transaction or posting date is given, use TODAY.

OUTPUT REQUIREMENTS:

Return a single JSON object matching the schema below.
Do not include additional explanations.

JSON SCHEMA:
{schema}
"""

# Helper function for logging
def make_event(event: str, **details: Any) -> dict[str, Any]:
    return {
        "event": event,
        **details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

# Formatting python to JSON for LLM 
def _dump(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


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

def invalid_candidate(
    tool_name: str,
    error: str,
) -> dict[str, Any]:
    """
    Return an invalid candidate without failing
    the entire sampling batch.
    """

    return {
        "tool": tool_name,
        "args": {},
        "missing_info": [],
        "valid": False,
        "errors": [error],
        "reason": "",
        "confidence": None,
    }


def to_candidate(
    response: Any,
    tool_name: str,
    parameters: dict[str, str],
) -> dict[str, Any]:
    """
    Convert one structured LLM response into a
    candidate compatible with the Governance Gate.
    """

    if not isinstance(response, dict):
        return invalid_candidate(
            tool_name,
            f"Invalid LLM response type: {type(response).__name__}",
        )

    action = response.get("parsed")

    if action is None:
        return invalid_candidate(
            tool_name,
            str(response.get("parsing_error") or "Parsing failed."),
        )

    errors = []

    if action.tool != tool_name:
        errors.append(
            f"Tool mismatch: expected '{tool_name}', "
            f"received '{action.tool}'."
        )

    if not action.missing_info:
        errors.extend(
            validate_arguments(action.args, parameters)
        )

    return {
        "tool": action.tool,
        "args": action.args,
        "missing_info": action.missing_info,
        "valid": not errors,
        "errors": errors,
        "reason": action.reason,
        "confidence": action.confidence,
    }


def action_preparer(state: PlanningState) -> dict[str, Any]:
    """
    Generate action candidates for the current plan step.

    Governance may request additional samples by setting
    n_requested to a positive integer.
    """

    def fail(reason: str) -> dict[str, Any]:
        return {
            "prepared_action": {},
            "status": "action_invalid",
            "history": [
                make_event(
                    "action_preparation_failed",
                    reason=reason,
                )
            ],
        }

    if state.get("plan_valid") is not True:
        return fail("The plan has not been validated.")

    plan = state.get("plan") or []
    current = state.get("current_step", 0)

    if (
        not isinstance(current, int)
        or isinstance(current, bool)
        or not 0 <= current < len(plan)
    ):
        return fail("Invalid current step index.")

    step = plan[current]

    if step.get("status", "pending") != "pending":
        return fail("The current step is not pending.")

    tool_name = step.get("tool")

    selected_tool = next(
        (
            tool
            for tool in state.get("available_tools", [])
            if (
                isinstance(tool, dict)
                and tool.get("name") == tool_name
            )
        ),
        None,
    )

    if selected_tool is None:
        return fail(
            f"Tool '{tool_name}' is not available."
        )

    parameters = selected_tool.get("parameters")

    if (
        not isinstance(parameters, dict)
        or not all(
            isinstance(name, str)
            and isinstance(type_name, str)
            for name, type_name in parameters.items()
        )
    ):
        return fail("Invalid tool parameter specification.")

    cfg = get_config()
    sampling = cfg["sampling"]

    existing = list(state.get("candidates") or [])
    requested = state.get("n_requested") or 0

    if requested:
        n = requested
    elif existing:
        return fail(
            "Existing candidates require an explicit "
            "sampling request."
        )
    else:
        n = initial_samples(selected_tool, cfg)

    max_samples = int(sampling["n_max"])

    if (
        not isinstance(n, int)
        or isinstance(n, bool)
        or n < 1
        or len(existing) + n > max_samples
    ):
        return fail("Invalid candidate sampling request.")

    temperature = (
        sampling["temperature"] if n > 1 else 0
    )

    parser = PydanticOutputParser(
        pydantic_object=PreparedAction
    )

    prompt = ACTION_PREPARER_PROMPT.format(
        instruction=state.get("instruction", ""),
        goal=state.get("goal", ""),
        step=_dump(step),
        tool=_dump(selected_tool),
        today=datetime.now(timezone.utc).date().isoformat(),
        facts=_dump(state.get("facts") or {}),
        artifacts=_dump(state.get("artifacts") or {}),
        step_results=_dump(
            state.get("step_results") or {}
        ),
        schema=parser.get_format_instructions(),
    )

    try:
        structured_llm = get_deepseek(
            temperature=temperature
        ).with_structured_output(
            PreparedAction,
            method="json_mode",
            include_raw=True,
        )

        responses = structured_llm.batch(
            [prompt] * n,
            return_exceptions=True,
        )

    except Exception as exc:
        responses = [exc] * n

    new_candidates = []

    for response in responses:
        if isinstance(response, dict):
            candidate = to_candidate(
                response,
                tool_name,
                parameters,
            )
        else:
            candidate = invalid_candidate(
                tool_name,
                f"{type(response).__name__}: {response}",
            )

        new_candidates.append(candidate)

    return {
        "candidates": existing + new_candidates,
        "n_requested": 0,
        "prepared_action": {},
        "status": "action_prepared",
        "history": [
            make_event(
                "candidates_prepared",
                step_id=step["id"],
                n=len(new_candidates),
                total_candidates=len(existing) + len(new_candidates),
                valid_candidates=sum(
                    1 for candidate in new_candidates
                    if candidate["valid"]
                ),
            )
        ],
    }

