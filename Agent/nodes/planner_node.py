
import json
from datetime import datetime, timezone

from langchain_core.output_parsers import PydanticOutputParser


from Agent.models import Plan
from Agent.state import PlanningState

from config.llm_connection import get_deepseek
from Agent.tools.read_tools import get_read_tool_specs

# Connect to LLM 
llm = get_deepseek() 
available_tools = get_read_tool_specs()


# THe planner prompt might need to change depending on autonomy level (because right now, it is not allowed to invent or assume values)
PLANNER_PROMPT = """
You are the planning component of a generic ERPNext AI agent.

Your task is to transform a natural-language employee
instruction into a structured business process plan.

EMPLOYEE INSTRUCTION:
{instruction}

AVAILABLE TOOLS:
{tools}

PLANNING RULES:

1. Identify the requested business goal.

2. Create only the steps required to achieve that goal.

3. Use exclusively tools listed in AVAILABLE TOOLS.

4. Use exact tool names from the provided catalog.

5. Do not extend a requested subprocess into a complete
   business process unless explicitly requested.

6. Assign a unique ID to each step.

7. List prerequisite step IDs in depends_on.

8. Order steps so that prerequisites appear before
   their dependent steps.

9. Include lookup operations when business entities
   must be resolved.

10. Do not invent customer IDs, item codes, document
    identifiers, prices, quantities or other business data.

11. If required information cannot be obtained, report
    it in missing_info.

12. If required tools are unavailable, explain the
    limitation in abort_reason.

13. If missing_info or abort_reason is populated,
    return an empty steps list.

14. Do not execute tools or prepare final tool arguments.

CONDITIONAL EXECUTION RULES:

15. Use execution_condition=null for unconditional steps.

16. Use structured execution conditions when a step
    depends on a previous tool result.

17. Each condition must reference a previous step
    using source_step.

18. The field must exist in the referenced tool's
    result_fields specification.

19. Use only the supported operators:
    - eq: equals the expected value
    - ne: does not equal the expected value

20. Use all when every listed comparison must be true.

21. Use any when at least one listed comparison
    must be true.

22. When both all and any contain comparisons,
    both groups must be satisfied.

23. Do not create conditions as natural-language strings.

24. A dependency controls execution order. It does
    not automatically imply that the predecessor's
    business operation was performed.

25. A conditional predecessor may be skipped.
    Downstream steps must still verify that all
    required business data is available.

26. If required data can come from alternative paths,
    represent those alternatives using any.

27. Only reference result fields explicitly declared
    in the corresponding tool specification.

28. Do not use arbitrary Python expressions or code
    inside execution conditions.

29. Every source_step referenced in an execution_condition
    must also appear in the step's depends_on list.

FOR EACH STEP:

- Provide a description of the intended operation.
- Provide a brief reason for including the step.
- Specify prerequisite step IDs in depends_on.
- Define execution_condition only when necessary.

OUTPUT REQUIREMENTS:

Return one JSON object matching the schema below.

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

    available_tools = state.get("available_tools") or get_read_tool_specs()
    

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