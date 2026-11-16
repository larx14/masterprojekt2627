
import json
from datetime import datetime, timezone

from langchain_core.output_parsers import PydanticOutputParser


from Agent.models import Plan
from Agent.state import PlanningState

from config.llm_connection import get_deepseek

# Connect to LLM 
llm = get_deepseek() 


PLANNER_PROMPT = """
You are the planning component of a generic AI agent
operating within the ERPNext enterprise resource planning system.

Your responsibility is to translate a natural-language
business instruction into a structured, executable plan.

EMPLOYEE INSTRUCTION:
{instruction}

AVAILABLE TOOLS:
{tools}

PLANNING OBJECTIVES:

1. Identify the business goal described in the instruction.

2. Decompose the instruction into the individual steps
   necessary to achieve that goal.

3. Select appropriate tools exclusively from the
   provided tool catalog.

4. Generate a plan that is applicable to different
   ERPNext business processes, including procurement,
   sales, inventory management, and master data operations.

PLANNING RULES:

1. Use only tools explicitly listed in AVAILABLE TOOLS.
   Tool names must match the catalog exactly.

2. Include only steps required to accomplish the
   employee's requested business goal.

3. Do not extend a requested subprocess into a complete
   business process unless explicitly requested.

4. Consider dependencies between operations.
   For example, a document must exist before it can
   be submitted or referenced by another document.

5. Assign a unique identifier to every step.

6. Specify the IDs of prerequisite steps in depends_on.

7. Arrange steps in a valid execution order.
   Prerequisite steps must appear before dependent steps.

8. Separate information retrieval from data modification.
   Use lookup tools when required to resolve business entities.

9. Do not invent business data, including customer IDs,
   item codes, supplier names, prices, quantities,
   document identifiers, or inventory information.

10. If required information can be obtained using an
    available lookup tool, include the corresponding
    lookup step instead of treating it as missing.

11. If required information cannot be obtained from the
    instruction or available tools, list it in missing_info.

12. If the requested goal cannot be achieved using the
    available tools, explain the limitation in abort_reason.

13. If missing_info is not empty or abort_reason is set,
    return an empty steps list.

14. Do not execute tools or generate final tool arguments.
    Tool argument preparation is handled by another component.

15. Do not assume that every business process requires
    document submission. Only include submission steps
    when required by the requested business goal or
    documented tool dependencies.

16. The plan must be sufficient to achieve the requested
    business goal without unnecessary additional actions.

FOR EACH STEP:

- Explain what the step should accomplish in description.
- Explain why the step is necessary in reason.
- Specify the IDs of prerequisite steps in depends_on.
- If execution depends on a previous result, specify
  an explicit execution_condition.
- Use null for execution_condition when the step
  does not require conditional execution.
- Do not assume that dependencies automatically imply
  conditional execution.

DEPENDENCY AND CONDITIONAL EXECUTION RULES:

1. A dependency indicates that a predecessor step must be
   resolved before the dependent step can proceed.

2. A predecessor may be completed successfully or skipped
   because its execution condition was not satisfied.

3. Skipping a step does not automatically guarantee that
   its expected business data exists.

4. When a step requires data that can originate from
   alternative paths, explicitly describe those alternatives
   in its execution condition.

5. Do not assume that a condition written in natural language
   is executable. Conditions must be evaluated by a
   downstream component before the corresponding tool runs.

OUTPUT REQUIREMENTS:

- Return a single JSON object matching the provided schema.
- goal: Describe the intended final business state.
- steps: List the planned operations in execution order.
- missing_info: List any required information that is unavailable.
- abort_reason: Explain why the goal cannot be planned, if applicable.
- Do not include explanations outside the JSON object.

JSON SCHEMA:
{schema}
"""


def planner(state: PlanningState) -> dict:
    """
    Generate a structured execution plan from an
    employee instruction and available tool definitions.

    The generated plan is not considered validated.
    """

    # Initialize the structured output parser.
    parser = PydanticOutputParser(
        pydantic_object=Plan
    )

    # Configure the LLM for structured JSON output.
    structured_llm = llm.with_structured_output(
        Plan,
        method="json_mode",
        include_raw=True
    )

    instruction = state.get(
        "instruction", ""
    ).strip()

    available_tools = state.get(
        "available_tools", []
    )

    def reject(reason: str) -> dict:
        """
        Return a failed planning result without
        producing executable steps.
        """

        return {
            "goal": "",
            "proposed_steps": [],
            "plan": [],
            "current_step": 0,
            "missing_info": [],
            "abort_reason": reason,
            "plan_valid": False,
            "validation_errors": [],
            "prepared_action": {},
            "status": "planning_failed",
            "history": [{
                "event": "plan_failed",
                "reason": reason,
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat()
            }]
        }

    # Validate the minimum required inputs.
    if not instruction:
        return reject(
            "No employee instruction was provided."
        )

    if not available_tools:
        return reject(
            "No tools are available for planning."
        )

    # Build the prompt using the employee instruction
    # and available tool definitions.
    prompt = PLANNER_PROMPT.format(
        instruction=instruction,
        tools=json.dumps(
            available_tools,
            ensure_ascii=False,
            indent=2
        ),
        schema=parser.get_format_instructions()
    )

    # Request a structured plan from the LLM.
    try:
        response = structured_llm.invoke(prompt)

        result = response.get("parsed")

        if result is None:
            error = response.get("parsing_error")

            return reject(
                "The LLM did not return a valid plan. "
                f"Parsing error: {error}"
            )

    except Exception as exc:
        return reject(
            "The LLM request failed: "
            f"{type(exc).__name__}: {exc}"
        )

    # Preserve the complete original LLM proposal.
    proposed_steps = [
        {
            **step.model_dump(),
            "status": "pending"
        }
        for step in result.steps
    ]

    # Only forward steps when planning is possible.
    # Preserve proposed_steps for traceability.
    if result.missing_info or result.abort_reason:
        steps = []
    else:
        steps = [
            step.copy()
            for step in proposed_steps
        ]

    # Determine the planning outcome.
    if result.abort_reason:
        status = "planning_failed"

    elif result.missing_info:
        status = "needs_human"

    else:
        status = "planned"

    # Create a structured decision log entry.
    decision_log = {
        "event": "plan_created",
        "goal": result.goal,
        "proposed_steps": proposed_steps,
        "forwarded_steps": steps,
        "missing_info": result.missing_info,
        "abort_reason": result.abort_reason,
        "status": status,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat()
    }

    # Return LangGraph state updates.
    return {
        "goal": result.goal,
        "proposed_steps": proposed_steps,
        "plan": steps,
        "current_step": 0,
        "missing_info": result.missing_info,
        "abort_reason": result.abort_reason,
        "plan_valid": False,
        "validation_errors": [],
        "prepared_action": {},
        "status": status,
        "history": [decision_log]
    }