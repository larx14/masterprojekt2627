"""Integration tests for the real ToolRegistry -> Executor -> ERPNext write tools.

ERPNext client calls are mocked. No LLM, database, or ERPNext server is needed.
"""

from copy import deepcopy

import pytest

from Agent.nodes.executor_node import executor
from Agent.tools import erpnext_client
from Agent.tools.register_tools import create_tool_registry


DOCTYPES = [
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Payment Entry",
    "Supplier", 
]


def make_state(tool_name: str, args: dict, *, step_id: str = "step1") -> dict:
    """Build a state containing exactly one automatically approved action."""
    action = {
        "step_id": step_id,
        "tool": tool_name,
        "args": deepcopy(args),
        "reason": "Execute the approved ERPNext operation.",
        "confidence": 0.95,
    }
    return {
        "instruction": "Execute the approved ERPNext operation.",
        "status": "auto",
        "plan_valid": True,
        "current_step": 0,
        "plan": [{
            "id": step_id,
            "tool": tool_name,
            "description": "Execute the ERPNext operation.",
            "depends_on": [],
            "execution_condition": None,
            "reason": "Complete the current step.",
            "status": "pending",
        }],
        "prepared_action": deepcopy(action),
        "governance": {
            "decision": "auto",
            "final_action": deepcopy(action),
        },
        "available_tools": create_tool_registry().get_specs(),
        "step_results": {},
        "candidates": [],
        "n_requested": 0,
        "history": [],
    }


def run_executor(state: dict) -> dict:
    """Use the actual executable registry, not a hand-written tool stub."""
    registry = create_tool_registry()
    return executor(state, registry=registry.get_executors())


@pytest.mark.parametrize("doctype", DOCTYPES)
def test_executor_creates_draft_via_registered_tool(monkeypatch, doctype):
    """An authorized create reaches the client once and stores its result."""
    calls = []

    def fake_create_doc(actual_doctype, data):
        calls.append((actual_doctype, deepcopy(data)))
        return {
            "name": "DRAFT-0001",
            "docstatus": 0,
            "items": deepcopy(data.get("items", [])),
        }

    monkeypatch.setattr(erpnext_client, "create_doc", fake_create_doc, raising=False)
    data = {"items": [{"item_code": "RM-013", "qty": 1}]}
    state = make_state("erp_create", {"doctype": doctype, "data": data})

    result = run_executor(state)

    assert result["status"] == "execution_succeeded"
    assert calls == [(doctype, data)]
    record = result["step_results"]["step1"]
    assert record["status"] == "completed"
    assert record["result"]["created"] is True
    assert record["result"]["doctype"] == doctype
    assert record["result"]["name"] == "DRAFT-0001"
    assert record["result"]["docstatus"] == 0
    assert record["result"]["data"]["items"] == data["items"]
    assert result["prepared_action"] == {}



@pytest.mark.parametrize("doctype", DOCTYPES)
def test_executor_submits_draft_via_registered_tool(monkeypatch, doctype):
    """An authorized submit checks the draft and submits exactly once."""
    calls = []

    def fake_get_doc(actual_doctype, name):
        calls.append(("get", actual_doctype, name))
        return {"name": name, "docstatus": 0}

    def fake_submit_doc(actual_doctype, name):
        calls.append(("submit", actual_doctype, name))
        return {"name": name, "docstatus": 1}

    monkeypatch.setattr(erpnext_client, "get_doc", fake_get_doc)
    monkeypatch.setattr(erpnext_client, "submit_doc", fake_submit_doc, raising=False)
    state = make_state("erp_submit", {"doctype": doctype, "name": "DRAFT-0001"})

    result = run_executor(state)

    assert result["status"] == "execution_succeeded"
    assert calls == [
        ("get", doctype, "DRAFT-0001"),
        ("submit", doctype, "DRAFT-0001"),
    ]
    record = result["step_results"]["step1"]
    assert record["status"] == "completed"
    assert record["result"] == {
        "submitted": True,
        "doctype": doctype,
        "name": "DRAFT-0001",
        "docstatus": 1,
    }


@pytest.mark.parametrize("tool_name,args", [
    ("erp_create", {"doctype": "Material Request", "data": {"items": []}}),
    ("erp_submit", {"doctype": "Material Request", "name": "DRAFT-0001"}),
])
def test_executor_blocks_unapproved_write(monkeypatch, tool_name, args):
    """Neither creation nor submission may run without authorization."""

    def unexpected_call(*_args, **_kwargs):
        pytest.fail("ERPNext client must not be called for an unauthorized action.")

    monkeypatch.setattr(erpnext_client, "create_doc", unexpected_call, raising=False)
    monkeypatch.setattr(erpnext_client, "get_doc", unexpected_call)
    monkeypatch.setattr(erpnext_client, "submit_doc", unexpected_call, raising=False)

    state = make_state(tool_name, args)
    state["governance"] = {}

    result = run_executor(state)

    assert result["status"] == "execution_blocked"


@pytest.mark.parametrize("tool_name,args", [
    ("erp_create", {"doctype": "Material Request", "data": {"items": []}}),
    ("erp_submit", {"doctype": "Material Request", "name": "DRAFT-0001"}),
])
def test_executor_blocks_duplicate_write(monkeypatch, tool_name, args):
    """A recorded step result prevents executing a write twice."""

    def unexpected_call(*_args, **_kwargs):
        pytest.fail("ERPNext client must not be called for a duplicate step.")

    monkeypatch.setattr(erpnext_client, "create_doc", unexpected_call, raising=False)
    monkeypatch.setattr(erpnext_client, "get_doc", unexpected_call)
    monkeypatch.setattr(erpnext_client, "submit_doc", unexpected_call, raising=False)

    state = make_state(tool_name, args)
    state["step_results"]["step1"] = {"status": "completed", "result": {}}

    result = run_executor(state)

    assert result["status"] == "execution_blocked"


def test_executor_records_create_tool_validation_failure(monkeypatch):
    """Registry adapters turn rejected create arguments into executor failures."""

    def unexpected_create(*_args, **_kwargs):
        pytest.fail("Invalid input must be rejected before the client call.")

    monkeypatch.setattr(erpnext_client, "create_doc", unexpected_create, raising=False)
    state = make_state("erp_create", {
        "doctype": "Supplier",  # Not permitted as a write DocType.
        "data": {"supplier_name": "Example"},
    })

    result = run_executor(state)

    assert result["status"] == "execution_failed"
    assert result["step_results"]["step1"]["status"] == "failed"
    assert "not allowed" in result["execution_error"].lower()


def test_executor_records_create_tool_validation_failure(monkeypatch):
    """
    Reject a DocType that is not allowed for creation.
    """

    def unexpected_create(*_args, **_kwargs):
        pytest.fail(
            "Invalid input must be rejected before the client call."
        )

    monkeypatch.setattr(
        erpnext_client,
        "create_doc",
        unexpected_create,
        raising=False,
    )

    state = make_state(
        "erp_create",
        {
            "doctype": "User",
            "data": {
                "email": "example@example.com",
            },
        },
    )

    result = run_executor(state)

    assert result["status"] == "execution_failed"
    assert result["step_results"]["step1"]["status"] == "failed"
    assert "not allowed" in result["execution_error"].lower()