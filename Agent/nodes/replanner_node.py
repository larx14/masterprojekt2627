
"""
Implement the Replanner Node.

The node revises a plan after a step could not be completed.
Finished steps are kept, only the remaining work is planned again.
It does not execute tools or evaluate execution conditions.
"""

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal

from langchain_core.output_parsers import PydanticOutputParser

from Agent.models import Plan
from Agent.state import PlanningState
from config.llm_connection import get_deepseek


# Connect to LLM
llm = get_deepseek()


# Maximum number of plan revisions per process.
MAX_REPLANS = 2

FINISHED_STATUSES = ("completed", "skipped")


REPLANNER_PROMPT = """
You are the replanning component of a generic ERPNext AI agent.

A previously validated plan could not be completed.
Your task is to create a revised plan for the REMAINING work.

EMPLOYEE INSTRUCTION:
{instruction}

BUSINESS GOAL:
{goal}

AVAILABLE TOOLS:
{tools}

FINISHED STEPS (already executed or skipped, with their results):
{finished}

STEP THAT COULD NOT BE COMPLETED:
{failed}

REASON FOR REPLANNING:
{reason}

KNOWN BUSINESS FACTS (confirmed, e.g. provided by a human):
{facts}

EXISTING ERP DOCUMENTS:
{artifacts}

REMAINING STEPS OF THE PREVIOUS PLAN (will be discarded):
{remaining}

REPLANNING RULES:

1. Never repeat a finished step. Its effects in ERPNext
   already exist.

2. Return only the steps for the remaining work.
   Do not include finished steps in your answer.

3. Address the reason for replanning. Do not repeat the
   failed step unchanged unless the reason indicates a
   temporary technical error.

4. Use exclusively tools listed in AVAILABLE TOOLS with
   their exact names.

5. Assign a unique ID to each new step.

6. New steps may depend on finished steps. Reference
   them by their existing IDs in depends_on and in
   execution conditions.

7. Order steps so that prerequisites appear before
   their dependent steps.

8. Do not invent customer IDs, item codes, document
   identifiers, prices, quantities or other business data.
   Use the KNOWN BUSINESS FACTS and EXISTING ERP DOCUMENTS.

9. If the goal cannot be reached with the available tools
   or information, return an empty steps list and explain
   it in missing_info or abort_reason. Do not report
   information as missing if it is listed in the
   KNOWN BUSINESS FACTS.

10. Keep the business goal of the original plan.

CONDITIONAL EXECUTION RULES:

11. Use execution_condition=null for unconditional steps.

12. Use structured execution conditions when a step
    depends on a previous tool result.

13. Each condition must reference a previous step using
    source_step, and that step must also appear in
    depends_on.

14. The field must exist in the referenced tool's
    result_fields specification.

15. Use only the operators eq and ne, grouped in all (AND)
    and any (OR). Do not use natural-language strings or
    code inside execution conditions.

OUTPUT REQUIREMENTS:

Return one JSON object matching the schema below.

JSON SCHEMA:
{schema}
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(event: str, **details) -> dict:
    return {"event": event, **details, "timestamp": _now()}


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def step_status(step: dict[str, Any], step_results: dict[str, Any]) -> str:
    """
    Return the status of a step, preferring the
    recorded step result over the plan status.
    """

    # Special case: the executor may only write step_results,
    # the plan status can still be "pending".
    record = step_results.get(step.get("id")) or {}
    return record.get("status") or step.get("status", "pending")


def fallback_reasons(state: PlanningState) -> list[str]:
    """
    Read the failure reason from the Executor and Evaluator
    fields when no replan_reason was set.
    """

    parts = []

    # Special case: the tool call itself failed (Executor).
    error = (state.get("execution_error") or "").strip()
    if error:
        parts.append(f"The last step failed: {error}")

    # Special case: the tool call worked, but the check afterwards
    # failed (Evaluator). The change already exists in ERPNext.
    verification = state.get("verification_result") or {}
    if state.get("status") == "verification_failed" and verification:
        expected = verification.get("expected_state") or {}
        doctype = expected.get("doctype")
        name = (expected.get("identity") or {}).get("name")
        differences = json.dumps(
            verification.get("differences") or [],
            ensure_ascii=False,
            default=str
        )

        target = f" ({doctype} '{name}')" if doctype and name else ""
        parts.append(
            f"The last step was executed{target}, but the check afterwards "
            f"failed: {verification.get('reason') or 'unknown'} {differences}. "
            "The change already exists in ERPNext. Do not repeat this step."
        )

    return parts


def collect_reason(state: PlanningState) -> str:
    """
    Combine the reported failure with the validation
    errors of a previously revised plan.
    """

    parts = []

    reason = (state.get("replan_reason") or "").strip()
    if reason:
        parts.append(reason)
    else:
        # Special case: Executor and Evaluator do not set replan_reason.
        parts.extend(fallback_reasons(state))

    # Special case: a revised plan was rejected by the Plan Validator.
    if state.get("status") == "plan_invalid":
        errors = state.get("validation_errors") or []
        if errors:
            parts.append(
                "The previously revised plan was invalid: "
                + "; ".join(str(error) for error in errors)
            )

    return " ".join(parts) or "No reason was provided."


def prefix_new_steps(
    steps: list[dict[str, Any]],
    finished_tools: dict[str, str],
    prefix: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Remove repeated finished steps and assign
    unique IDs to all new steps.

    A step is a repetition if it has the ID and the tool
    of a finished step. References to finished steps
    keep their IDs.
    """

    # Special case: same ID and same tool = repetition, it is dropped.
    # Same ID with another tool = new step, it is kept and renamed.
    def repeated(step: dict[str, Any]) -> bool:
        return finished_tools.get(step.get("id")) == step.get("tool")

    dropped = [s["id"] for s in steps if repeated(s)]
    kept = [deepcopy(s) for s in steps if not repeated(s)]

    new_ids = {s.get("id") for s in kept}

    # Special case: references to new steps are renamed as well,
    # references to finished steps keep their IDs.
    def rename(step_id: Any) -> Any:
        return f"{prefix}{step_id}" if step_id in new_ids else step_id

    for step in kept:
        step["id"] = rename(step["id"])
        step["depends_on"] = [rename(d) for d in step.get("depends_on", [])]

        condition = step.get("execution_condition")
        if isinstance(condition, dict):
            for group in ("all", "any"):
                for comparison in condition.get(group) or []:
                    comparison["source_step"] = rename(comparison.get("source_step"))

        step["status"] = "pending"

    return kept, dropped


def replanner(state: PlanningState) -> dict:
    """
    Create a revised plan for the remaining work
    while keeping all finished steps unchanged.
    """

    plan = state.get("plan") or []
    current = state.get("current_step", 0)
    attempt = int(state.get("replan_count") or 0) + 1
    reason = collect_reason(state)

    def stop(status: str, message: str, **details) -> dict:
        """
        Return a failed replanning result without
        changing the plan.
        """

        return {
            "status": status,
            "abort_reason": message,
            # Pass the reason on, the Finalizer shows it as last error.
            "replan_reason": reason,
            "prepared_action": {},
            "candidates": [],
            "n_requested": 0,
            "history": [_event(
                "replan_failed",
                attempt=attempt,
                reason=reason,
                status=status,
                message=message,
                **details
            )]
        }

    # Special case: limit reached, stop without calling the LLM.
    # The counter counts per run (the chat resets it for every new instruction).
    if attempt > MAX_REPLANS:
        return stop(
            "replan_limit_reached",
            f"The plan was already revised {MAX_REPLANS} times. "
            "A human has to decide how to continue. "
            f"Last error: {reason}"
        )

    # Validate the minimum required inputs.
    if (
        not isinstance(current, int)
        or isinstance(current, bool)
        or not 0 <= current <= len(plan)
    ):
        return stop("replanning_failed", "The current step index is invalid.")

    if not state.get("available_tools"):
        return stop("replanning_failed", "No tools are available for planning.")

    step_results = state.get("step_results") or {}

    # Steps before the current step are finished and remain unchanged.
    # Special case: the failed step is the current step. It has no own
    # status (stays "pending"), its reason is in replan_reason.
    finished = deepcopy(plan[:current])
    failed = deepcopy(plan[current]) if current < len(plan) else None
    remaining = deepcopy(plan[current + 1:]) if failed else []

    # Special case: every step before the current step must be finished.
    unfinished = []
    for step in finished:
        status = step_status(step, step_results)
        if status in FINISHED_STATUSES:
            step["status"] = status
        else:
            unfinished.append(step.get("id"))

    if unfinished:
        return stop(
            "replanning_failed",
            "Steps before the current step are not finished: "
            + ", ".join(map(str, unfinished))
        )

    # Build the prompt using finished steps, the failed step, the reason
    # and the facts a human may have provided in the meantime.
    finished_view = [
        {**step, "result": (step_results.get(step["id"]) or {}).get("result")}
        for step in finished
    ]

    failed_view = None
    if failed:
        failed_view = {**failed, "outcome": step_results.get(failed["id"])}

    parser = PydanticOutputParser(pydantic_object=Plan)

    prompt = REPLANNER_PROMPT.format(
        instruction=(state.get("instruction") or "").strip(),
        goal=state.get("goal") or "",
        tools=_dump(state.get("available_tools")),
        finished=_dump(finished_view) if finished_view else "None",
        failed=_dump(failed_view) if failed_view else "None",
        reason=reason,
        facts=_dump(state.get("facts")) if state.get("facts") else "None",
        artifacts=_dump(state.get("artifacts")) if state.get("artifacts") else "None",
        remaining=_dump(remaining) if remaining else "None",
        schema=parser.get_format_instructions()
    )

    structured_llm = llm.with_structured_output(
        Plan,
        method="json_mode",
        include_raw=True
    )

    # Request a structured plan from the LLM.
    try:
        response = structured_llm.invoke(prompt)
        result = response.get("parsed")

        if result is None:
            return stop(
                "replanning_failed",
                "The LLM did not return a valid plan. "
                f"Parsing error: {response.get('parsing_error')}"
            )

    except Exception as exc:
        return stop(
            "replanning_failed",
            f"The LLM request failed: {type(exc).__name__}: {exc}"
        )

    # Special case: missing information or an abort reason ends the run
    # in the Finalizer. No human is asked here (Miro: Human Approval).
    if result.abort_reason or result.missing_info:
        status = "planning_failed" if result.abort_reason else "needs_human"
        return {
            **stop(
                status,
                result.abort_reason or "Required information is missing.",
                missing_info=result.missing_info
            ),
            "missing_info": result.missing_info,
            "replan_count": attempt,
        }

    # Finished steps must never be planned a second time.
    finished_tools = {s["id"]: s.get("tool") for s in finished}

    new_steps, dropped = prefix_new_steps(
        [step.model_dump() for step in result.steps],
        finished_tools,
        prefix=f"r{attempt}_"
    )

    # Special case: the LLM only repeated finished steps.
    if not new_steps:
        return stop(
            "replanning_failed",
            "The revised plan contains no new steps.",
            dropped_steps=dropped
        )

    # Return LangGraph state updates.
    # Special case: status "planned" lets the Plan Validator check the
    # revised plan. candidates are cleared, so old samples of the failed
    # step never reach the Governance Gate.
    return {
        "goal": result.goal or state.get("goal", ""),
        "proposed_steps": new_steps,
        "plan": finished + new_steps,
        "current_step": len(finished),
        "missing_info": [],
        "abort_reason": "",
        "plan_valid": False,
        "validation_errors": [],
        "prepared_action": {},
        "candidates": [],
        "n_requested": 0,
        "replan_count": attempt,
        "replan_reason": state.get("replan_reason") or reason,
        "status": "planned",
        "history": [_event(
            "plan_replanned",
            attempt=attempt,
            reason=reason,
            failed_step=failed.get("id") if failed else None,
            kept_steps=[s["id"] for s in finished],
            discarded_steps=[s.get("id") for s in ([failed] if failed else []) + remaining],
            new_steps=[s["id"] for s in new_steps],
            dropped_repeated_steps=dropped
        )]
    }


def route_after_replanner(
    state: PlanningState
) -> Literal["validate", "stop"]:

    if state.get("status") == "planned":
        return "validate"

    return "stop"
