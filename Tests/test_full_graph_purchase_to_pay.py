"""
Manual end-to-end integration test for the complete
ERPNext Purchase-to-Pay workflow.

Run only against a dedicated ERPNext test environment.
"""

from datetime import date
from pprint import pprint
from uuid import uuid4

from config.db_connection import checkpointer
from langgraph.types import Command

from Agent.graph import build_planning_graph
from Agent.tools.register_tools import create_tool_registry
from Agent.tools.erpnext_client import get_doc

from Tests.test_full_graph_read_tools import (
    heading,
    detail,
    show_node_update,
)


def run_purchase_to_pay_integration():

    today = date.today().isoformat()
    run_id = uuid4().hex[:8]

    invoice_number = f"P2P-TEST-INV-{run_id}"
    payment_reference = f"P2P-TEST-PAY-{run_id}"

    instruction = f"""
    Execute the complete Purchase-to-Pay process
    in the ERPNext test environment.

    Purchase 1 kg of Apples from Kettwig Farm
    at a rate of 1.50 per kg.

    Use the warehouse:
    Raw Materials Store - MP

    Required delivery date: {today}

    Test invoice number: {invoice_number}
    Invoice date: {today}

    Bank GL account: 1810 - Bank 1 - MP
    Test payment reference: {payment_reference}
    Payment reference date: {today}

    Create and submit all five documents:

    1. Material Request
    2. Purchase Order
    3. Purchase Receipt
    4. Purchase Invoice
    5. Payment Entry

    Use approved ERPNext document mappings between
    consecutive documents.

    Preserve all source document and item references.

    Verify master data before executing write operations.
    Do not invent missing business or accounting data.
    """

    registry = create_tool_registry()

    graph = build_planning_graph(
       checkpointer=checkpointer
    )

    initial_state = {
        "instruction": instruction,
        "available_tools": registry.get_specs(),
        "current_step": 0,
        "facts": {},
        "artifacts": {},
        "step_results": {},
        "history": [],
        "replan_count": 0,
    }

    config = {
        "configurable": {
            "thread_id": str(uuid4()),
        },
        "recursion_limit": 300,
    }
    print(
    "Thread ID:",
    config["configurable"]["thread_id"]
)

    context = {
        "step_id": None,
        "warnings": [],
    }

    visited_nodes = []
    graph_input = initial_state

    heading("PURCHASE-TO-PAY INTEGRATION TEST")

    detail("Instruction", instruction)

    confirmation = input(
        "Type START to create real test documents: "
    )

    if confirmation != "START":
        print("Test cancelled.")
        return

    while True:

        for mode, chunk in graph.stream(
            graph_input,
            config=config,
            stream_mode=["updates", "values"],
        ):

            if mode == "updates":

                for node_name, update in chunk.items():

                    if node_name == "__interrupt__":
                        continue

                    visited_nodes.append(node_name)

                    show_node_update(
                        node_name,
                        update,
                        context,
                    )

        snapshot = graph.get_state(config)

        if not snapshot.interrupts:
            break

        payload = snapshot.interrupts[0].value

        heading("HUMAN REVIEW REQUIRED")
        pprint(payload)

        decision = input(
            "Type APPROVE or REJECT: "
        ).strip().upper()

        graph_input = Command(
            resume={
                "action": (
                    "approve"
                    if decision == "APPROVE"
                    else "reject"
                )
            }
        )

    final_state = graph.get_state(config).values

    heading("FINAL STATE")
    detail(
        "Expected state",
        final_state.get("expected_state")
    )

    detail(
        "Verification result",
        final_state.get("verification_result")
    )

    detail(
        "Execution error",
        final_state.get("execution_error")
    )
    detail("Status", final_state.get("status"))
    detail("Final result", final_state.get("final_result"))
    detail("Visited nodes", visited_nodes)

    heading("TEST ASSERTIONS")

    assert final_state.get("plan_valid") is True, (
        "Plan validation failed."
    )

    assert final_state.get("status") == "process_completed", (
        "The process was not completed."
    )

    assert final_state.get("final_result", {}).get(
        "outcome"
    ) == "completed"

    expected_doctypes = {
        "Material Request",
        "Purchase Order",
        "Purchase Receipt",
        "Purchase Invoice",
        "Payment Entry",
    }

    created_documents = {}

    for execution in final_state.get(
        "step_results", {}
    ).values():

        result = execution.get("result") or {}

        if result.get("created") is True:

            doctype = result.get("doctype")
            name = result.get("name")

            if doctype in expected_doctypes and name:

                assert doctype not in created_documents, (
                    f"Duplicate document created: {doctype}"
                )

                created_documents[doctype] = name

    assert set(created_documents) == expected_doctypes, (
        "Not all five required documents were created."
    )

    for doctype, name in created_documents.items():

        document = get_doc(doctype, name)

        assert document is not None, (
            f"Document not found: {name}"
        )

        assert document.get("docstatus") == 1, (
            f"Document was not submitted: {name}"
        )

        detail(
            f"{doctype} verification",
            f"{name} - SUBMITTED",
        )

    heading("TEST RESULT")
    print("ALL ASSERTIONS PASSED")


if __name__ == "__main__":
    run_purchase_to_pay_integration()