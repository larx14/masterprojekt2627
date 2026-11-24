"""Unit tests for generic ERPNext document submission.

Only the ERPNext client is mocked. No network requests or writes occur.
"""

import pytest

from Agent.tools import erp_submit
from Agent.tools.erpnext_client import ERPNextError


DOCTYPES = [
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Payment Entry",
]


def make_args(doctype="Material Request", name="TEST-DRAFT-001"):
    return {"doctype": doctype, "name": name}


@pytest.mark.parametrize("doctype", DOCTYPES)
def test_submit_supported_doctypes(monkeypatch, doctype):
    calls = []

    def fake_get_doc(actual_doctype, name):
        calls.append(("get", actual_doctype, name))
        return {"name": name, "docstatus": 0}

    def fake_submit_doc(actual_doctype, name):
        calls.append(("submit", actual_doctype, name))
        return {"name": name, "docstatus": 1}

    monkeypatch.setattr(erp_submit.client, "get_doc", fake_get_doc)
    monkeypatch.setattr(erp_submit.client, "submit_doc", fake_submit_doc, raising=False)
    response = erp_submit.run_submit_tool("erp_submit", make_args(doctype))

    assert response == {
        "status": "completed",
        "result": {
            "submitted": True,
            "doctype": doctype,
            "name": "TEST-DRAFT-001",
            "docstatus": 1,
        },
    }
    assert calls == [
        ("get", doctype, "TEST-DRAFT-001"),
        ("submit", doctype, "TEST-DRAFT-001"),
    ]


def test_submit_tool_spec_matches_result_contract():
    spec, = erp_submit.get_submit_tool_specs()
    assert spec["name"] == "erp_submit"
    assert spec["risk"] == "submit"
    assert spec["parameters"] == {"doctype": "str", "name": "str"}
    assert spec["result_fields"] == erp_submit.RESULT_FIELDS


@pytest.mark.parametrize("args", [
    {"doctype": "User", "name": "TEST-001"},
    {"doctype": "Purchase Order", "name": ""},
    {"doctype": "Purchase Order", "name": "   "},
    {"doctype": "Purchase Order", "name": None},
    {"doctype": "Purchase Order", "name": 123},
    {"doctype": "Purchase Order"},
    {"doctype": "Purchase Order", "name": "TEST-001", "data": {}},
    None,
])
def test_submit_rejects_invalid_arguments_without_call(monkeypatch, args):
    calls = []
    monkeypatch.setattr(erp_submit.client, "get_doc", lambda *a: calls.append(a))
    response = erp_submit.run_submit_tool("erp_submit", args)
    assert response["status"] == "failed"
    assert response["result"] is None
    assert response["errors"]
    assert calls == []


def test_submit_rejects_unknown_tool_without_call(monkeypatch):
    calls = []
    monkeypatch.setattr(erp_submit.client, "get_doc", lambda *a: calls.append(a))
    response = erp_submit.run_submit_tool("wrong_tool", make_args())
    assert response["status"] == "failed"
    assert "Unknown tool" in response["errors"][0]
    assert calls == []


@pytest.mark.parametrize("existing", [
    None,
    {},
    {"name": "WRONG-001", "docstatus": 0},
    {"name": "TEST-DRAFT-001", "docstatus": 1},
    {"name": "TEST-DRAFT-001", "docstatus": 2},
    {"name": "TEST-DRAFT-001", "docstatus": "0"},
])
def test_submit_rejects_non_draft_without_submitting(monkeypatch, existing):
    calls = []
    monkeypatch.setattr(erp_submit.client, "get_doc", lambda *a: existing)
    monkeypatch.setattr(
        erp_submit.client, "submit_doc",
        lambda *a: calls.append(a), raising=False,
    )
    response = erp_submit.run_submit_tool("erp_submit", make_args())
    assert response["status"] == "failed"
    assert response["result"] is None
    assert calls == []


@pytest.mark.parametrize("stage", ["get", "submit"])
def test_submit_client_error_does_not_trigger_retry(monkeypatch, stage):
    calls = []

    def fake_get_doc(doctype, name):
        calls.append("get")
        if stage == "get":
            raise ERPNextError("Request timed out")
        return {"name": name, "docstatus": 0}

    def fake_submit_doc(doctype, name):
        calls.append("submit")
        raise ERPNextError("Request timed out")

    monkeypatch.setattr(erp_submit.client, "get_doc", fake_get_doc)
    monkeypatch.setattr(erp_submit.client, "submit_doc", fake_submit_doc, raising=False)
    response = erp_submit.run_submit_tool("erp_submit", make_args())

    assert response["status"] == "unconfirmed"
    assert response["result"] is None
    assert "Reconcile before retrying" in response["errors"][0]
    assert calls == (["get"] if stage == "get" else ["get", "submit"])


@pytest.mark.parametrize("server_response", [
    None,
    [],
    {},
    {"name": "OTHER-001", "docstatus": 1},
    {"name": "TEST-DRAFT-001", "docstatus": 0},
    {"name": "TEST-DRAFT-001", "docstatus": "1"},
])
def test_submit_unconfirmed_response_requires_reconciliation(monkeypatch, server_response):
    monkeypatch.setattr(
        erp_submit.client, "get_doc",
        lambda doctype, name: {"name": name, "docstatus": 0},
    )
    monkeypatch.setattr(
        erp_submit.client, "submit_doc",
        lambda doctype, name: server_response, raising=False,
    )
    response = erp_submit.run_submit_tool("erp_submit", make_args())
    assert response["status"] == "unconfirmed"
    assert response["result"] is None
    assert "reconcil" in response["errors"][0].lower()