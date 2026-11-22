





import sys
from pathlib import Path


# Das hier muss man hinzufügen, weil er sonst nicht die Module aus anderen Projektordnern findet
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))


"""
Readable end-to-end integration test for the ERPNext agent.

Displays planning, validation, tool arguments, governance decisions,
execution results, verification and the final process outcome.
"""

import json
from uuid import uuid4

from Agent.graph import build_planning_graph
from Agent.tools.read_tools import get_read_tool_specs


TEST_INSTRUCTION = """
Gib mir eine Liste mit allen Suppliern aus.
"""


def heading(title: str):
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


def detail(label: str, value):
    if isinstance(value, (dict, list)):
        value = json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    print(f"  {label}: {value}")


def format_condition(condition):
    """Convert structured conditions into readable text."""

    if not condition:
        return "Unconditional"

    groups = []

    for group_name in ("all", "any"):
        comparisons = condition.get(group_name, [])

        expressions = [
            f"{item['source_step']}.{item['field']} "
            f"{'==' if item['operator'] == 'eq' else '!='} "
            f"{item['value']!r}"
            for item in comparisons
        ]

        if expressions:
            separator = " AND " if group_name == "all" else " OR "
            groups.append(f"({separator.join(expressions)})")

    return " AND ".join(groups) or "Unconditional"


def show_node_update(node_name, update, context):
    """Print a readable explanation of a node's output."""

    if not isinstance(update, dict):
        detail("Update", update)
        return

    if node_name == "planner":
        heading("PLANNER")

        detail("Goal", update.get("goal"))
        detail("Status", update.get("status"))

        plan = update.get("plan") or []
        detail("Planned steps", len(plan))

        for index, step in enumerate(plan, start=1):
            print(f"\n  Step {index}: {step['id']} / {step['tool']}")
            detail("Description", step.get("description"))
            detail("Reason", step.get("reason"))
            detail("Dependencies", step.get("depends_on"))
            detail(
                "Execution condition",
                format_condition(step.get("execution_condition")),
            )

        if update.get("abort_reason"):
            detail("Abort reason", update["abort_reason"])

        if update.get("missing_info"):
            detail("Missing information", update["missing_info"])

    elif node_name == "plan_validator":
        heading("PLAN VALIDATOR")

        detail(
            "Validation",
            "PASSED" if update.get("plan_valid") else "FAILED",
        )
        detail("Errors", update.get("validation_errors", []))

    elif node_name == "condition_evaluator":
        heading("CONDITION EVALUATOR")

        history = update.get("history") or []
        event = history[-1] if history else {}

        context["step_id"] = event.get("step_id")

        detail("Step", context["step_id"])
        detail("Result", update.get("condition_result"))
        detail("Reason", update.get("condition_reason"))

    elif node_name == "action_preparer":
        heading("ACTION PREPARER")

        candidates = update.get("candidates") or []

        detail("Step", context.get("step_id"))
        detail("Candidates generated", len(candidates))

        for index, candidate in enumerate(candidates, start=1):
            print(f"\n  Candidate {index}")
            detail("Tool", candidate.get("tool"))
            detail("Arguments", candidate.get("args"))
            detail("Valid", candidate.get("valid"))
            detail("Confidence", candidate.get("confidence"))
            detail("Reason", candidate.get("reason"))

            if candidate.get("errors"):
                detail("Errors", candidate["errors"])

    elif node_name == "governance_gate":
        heading("GOVERNANCE GATE")

        governance = update.get("governance") or {}
        action = update.get("prepared_action") or {}

        detail("Step", governance.get("step_id"))
        detail("Tool", governance.get("tool"))
        detail("Risk", governance.get("risk"))
        detail("Autonomy level", governance.get("autonomy_level"))
        detail("Decision", governance.get("decision"))
        detail("Reason", governance.get("reason"))
        detail("Consistency", governance.get("conf_consistency"))
        detail("Verbal confidence", governance.get("conf_verbal"))
        detail("Authorized arguments", action.get("args"))

        if governance.get("log_error"):
            warning = governance["log_error"].splitlines()[0]
            context["warnings"].append(warning)
            detail("Audit logging warning", warning)

    elif node_name == "human_review":
        heading("HUMAN REVIEW")

        detail("Status", update.get("status"))
        detail("Decision", update.get("human_decision"))

    elif node_name == "executor":
        heading("EXECUTOR")

        step_id = context.get("step_id")
        results = update.get("step_results") or {}
        execution = results.get(step_id) or {}

        detail("Step", step_id)
        detail("Execution status", update.get("status"))
        detail("Tool result status", execution.get("status"))
        detail("Result", execution.get("result"))

        if update.get("execution_error"):
            detail("Execution error", update["execution_error"])

    elif node_name == "evaluator":
        heading("EVALUATOR")

        verification = update.get("verification_result") or {}

        detail("Step", context.get("step_id"))
        detail("Verification", verification.get("result"))
        detail("Reason", verification.get("reason"))
        detail("Routing result", update.get("evaluation_result"))
        detail("Next step index", update.get("current_step"))
        detail("Status", update.get("status"))

    elif node_name == "skip_step":
        heading("SKIP STEP")
        detail("Step", context.get("step_id"))
        detail("Update", update)

    elif node_name == "replanner":
        heading("REPLANNER")
        detail("Status", update.get("status"))
        detail("Replan count", update.get("replan_count"))

    elif node_name == "finalizer":
        heading("FINALIZER")

        final = update.get("final_result") or {}
        steps = final.get("steps") or []

        detail("Outcome", final.get("outcome"))
        detail("Goal", final.get("goal"))

        for step in steps:
            print(
                f"  {step.get('id')} | "
                f"{step.get('tool')} | "
                f"{step.get('status')}"
            )

        detail(
            "Completed steps",
            sum(s.get("status") == "completed" for s in steps),
        )
        detail("Total steps", len(steps))
        detail(
            "Governance decisions",
            final.get("governance_decisions"),
        )
        detail("Human reviews", final.get("human_reviews"))
        detail("Replans", final.get("replans"))

        if final.get("reason"):
            detail("Final reason", final["reason"])


def test_complete_read_workflow():
    """Run and validate the complete ERPNext read workflow."""

    graph = build_planning_graph()

    initial_state = {
        "instruction": TEST_INSTRUCTION,
        "available_tools": get_read_tool_specs(),
    }

    config = {
        "configurable": {
            "thread_id": str(uuid4()),
        },
        "recursion_limit": 100,
    }

    visited_nodes = []
    latest_state = initial_state

    context = {
        "step_id": None,
        "warnings": [],
    }

    heading("ERPNext AGENT - INTEGRATION TEST")

    detail("Thread ID", config["configurable"]["thread_id"])
    detail(
        "Available tools",
        [tool["name"] for tool in initial_state["available_tools"]],
    )

    for mode, chunk in graph.stream(
        initial_state,
        config=config,
        stream_mode=["updates", "values"],
    ):
        if mode == "updates":
            for node_name, update in chunk.items():
                visited_nodes.append(node_name)
                show_node_update(node_name, update, context)

        elif mode == "values":
            latest_state = chunk

    heading("TEST ASSERTIONS")

    required_nodes = {
        "planner",
        "plan_validator",
        "condition_evaluator",
        "action_preparer",
        "governance_gate",
        "executor",
        "evaluator",
        "finalizer",
    }

    missing_nodes = required_nodes - set(visited_nodes)

    assert not missing_nodes, (
        f"Missing node executions: {missing_nodes}"
    )

    detail("Required nodes", "PASSED")

    assert latest_state.get("plan_valid") is True
    detail("Plan validation", "PASSED")

    assert latest_state.get("status") == "process_completed"
    detail("Process status", "PASSED")

    final = latest_state.get("final_result") or {}

    assert final.get("outcome") == "completed"
    detail("Final outcome", "PASSED")

    results = latest_state.get("step_results") or {}
    plan = latest_state.get("plan") or []

    assert len(plan) == 3, "Expected exactly three steps."

    expected_sequence = [
        "erp_search",
        "erp_count",
        "erp_get",
    ]

    actual_sequence = [step["tool"] for step in plan]

    assert actual_sequence == expected_sequence, (
        f"Unexpected tool sequence: {actual_sequence}"
    )

    for step in plan:
        step_id = step["id"]

        assert step["status"] == "completed", (
            f"Step {step_id} was not completed."
        )

        assert results.get(step_id, {}).get("status") == "completed", (
            f"Missing successful execution result for {step_id}."
        )

    assert visited_nodes.count("executor") == 3
    detail("Three tool executions", "PASSED")

    search_result = results["step1"]["result"]
    count_result = results["step2"]["result"]
    get_result = results["step3"]["result"]

    assert search_result["found"] is True
    assert count_result["count"] >= 1
    assert get_result["found"] is True

    assert search_result["name"] == get_result["name"], (
        "The retrieved supplier does not match the search result."
    )

    detail("Supplier result consistency", "PASSED")

    heading("BUSINESS RESULTS")

    detail("Total suppliers", count_result["count"])
    detail("First supplier", search_result["name"])
    detail("Document retrieved", get_result["found"])

    if context["warnings"]:
        heading("NON-FATAL WARNINGS")

        for warning in dict.fromkeys(context["warnings"]):
            print(f"  WARNING: {warning}")

    heading("TEST RESULT")
    print("  ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    test_complete_read_workflow()
