
"""
Manual integration test for the Replanner Node.

Uses the configured LLM but does not execute ERPNext tools.
Run from the project folder: python -m Tests.test_replanner_manual
"""

import json
from copy import deepcopy

from Agent.nodes.plan_validator_node import plan_validator
from Agent.nodes.replanner_node import replanner
from Tests.mock_tools import MOCK_TOOLS


STATE = {
    "instruction": "Create a sales order for Example GmbH: 5 croissants.",
    "goal": "A sales order for Example GmbH exists.",
    "available_tools": MOCK_TOOLS,
    "plan": [
        {
            "id": "step_1",
            "tool": "find_customer",
            "description": "Find customer Example GmbH.",
            "depends_on": [],
            "execution_condition": None,
            "reason": "Avoid duplicate customers.",
            "status": "completed",
        },
        {
            "id": "step_2",
            "tool": "create_sales_order",
            "description": "Create the sales order for 5 croissants.",
            "depends_on": ["step_1"],
            "execution_condition": None,
            "reason": "Requested by the employee.",
            "status": "pending",
        },
    ],
    "current_step": 1,
    "plan_valid": True,
    "step_results": {
        "step_1": {
            "status": "completed",
            "result": {"customer_exists": True, "customer_id": "CUST-0001"},
            "reason": "Customer found.",
        },
    },
    "replan_reason": "create_sales_order failed: Item 'Croissant' not found.",
    "history": [],
}


def show(title, value):
    print(f"\n{title}:")
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def main():
    result = replanner(deepcopy(STATE))

    print("STATUS:", result.get("status"))
    print("REPLAN COUNT:", result.get("replan_count"))

    if result.get("status") != "planned":
        print("ABORT REASON:", result.get("abort_reason"))
        show("HISTORY", result.get("history"))
        return

    show("REVISED PLAN", result["plan"])
    show("REPLAN EVENT", result["history"][0])

    validated = plan_validator({**deepcopy(STATE), **result})
    print("\nPLAN VALID:", validated["plan_valid"])
    if validated["validation_errors"]:
        show("VALIDATION ERRORS", validated["validation_errors"])

    assert result["plan"][0] == STATE["plan"][0], "step_1 must stay unchanged"


if __name__ == "__main__":
    main()
