"""Unit tests for generic ERPNext draft creation.

Only the ERPNext client is mocked. No network requests or writes occur.
"""

from copy import deepcopy

import pytest

from Agent.tools import erp_create
from Agent.tools.erpnext_client import ERPNextError


DOCTYPES = [
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Payment Entry",
]


def make_args(doctype="Material Request"):
    return {
        "doctype": doctype,
        "data": {"custom_test_reference": "TEST-001"},
    }


@pytest.mark.parametrize("doctype", DOCTYPES)
def test_create_supported_doctypes(monkeypatch, doctype):
    calls = []

    def fake_create_doc(actual_doctype, data):
        calls.append((actual_doctype, deepcopy(data)))
        return {
            "name": "TEST-DRAFT-001",
            "doctype": actual_doctype,
            "docstatus": 0,
            **data,
        }

    monkeypatch.setattr(erp_create.client, "create_doc", fake_create_doc, raising=False)
    args = make_args(doctype)
    original = deepcopy(args)

    response = erp_create.run_create_tool("erp_create", args)

    assert response["status"] == "completed"
    result = response["result"]
    assert result["created"] is True
    assert result["doctype"] == doctype
    assert result["name"] == "TEST-DRAFT-001"
    assert result["docstatus"] == 0
    assert result["data"]["name"] == "TEST-DRAFT-001"
    assert calls == [(doctype, original["data"])]
    assert args == original


def test_create_tool_spec_matches_result_contract():
    spec, = erp_create.get_create_tool_specs()
    assert spec["name"] == "erp_create"
    assert spec["risk"] == "draft"
    assert spec["parameters"] == {"doctype": "str", "data": "dict"}
    assert spec["result_fields"] == erp_create.RESULT_FIELDS


@pytest.mark.parametrize("args", [
    {"doctype": "User", "data": {"first_name": "Test"}},
    {"doctype": "Purchase Order", "data": {}},
    {"doctype": "Purchase Order", "data": []},
    {"doctype": "Purchase Order", "data": {"docstatus": 1}},
    {"doctype": "Purchase Order", "data": {"name": "FAKE-001"}},
    {"doctype": "Purchase Order", "data": {"owner": "Administrator"}},
    {"doctype": "Purchase Order", "data": {"doctype": "Payment Entry"}},
    {"doctype": "Purchase Order"},
    {"doctype": "Purchase Order", "data": {"supplier": "Test"}, "unexpected": True},
    {"doctype": "Purchase Order", "data": {1: "invalid"}},
    None,
])
def test_create_rejects_invalid_arguments_without_call(monkeypatch, args):
    calls = []
    monkeypatch.setattr(
        erp_create.client, "create_doc",
        lambda *a, **kw: calls.append((a, kw)), raising=False,
    )
    response = erp_create.run_create_tool("erp_create", args)
    assert response["status"] == "failed"
    assert response["result"] is None
    assert response["errors"]
    assert calls == []


def test_create_rejects_unknown_tool_without_call(monkeypatch):
    calls = []
    monkeypatch.setattr(
        erp_create.client, "create_doc",
        lambda *a, **kw: calls.append((a, kw)), raising=False,
    )
    response = erp_create.run_create_tool("wrong_tool", make_args())
    assert response["status"] == "failed"
    assert "Unknown tool" in response["errors"][0]
    assert calls == []


def test_create_client_error_does_not_trigger_retry(monkeypatch):
    calls = []

    def fake_create_doc(doctype, data):
        calls.append((doctype, data))
        raise ERPNextError("Request timed out")

    monkeypatch.setattr(erp_create.client, "create_doc", fake_create_doc, raising=False)
    response = erp_create.run_create_tool("erp_create", make_args())
    assert response["status"] == "failed"
    assert response["result"] is None
    assert "outcome is unknown" in response["errors"][0]
    assert len(calls) == 1


@pytest.mark.parametrize("server_response", [
    None,
    [],
    {},
    {"name": "", "docstatus": 0},
    {"name": "TEST-001", "docstatus": 1},
    {"name": "TEST-001", "docstatus": "0"},
    {"name": "TEST-001"},
])
def test_create_unconfirmed_response_requires_reconciliation(monkeypatch, server_response):
    monkeypatch.setattr(
        erp_create.client, "create_doc",
        lambda doctype, data: server_response, raising=False,
    )
    response = erp_create.run_create_tool("erp_create", make_args())
    assert response["status"] == "unconfirmed"
    assert response["result"] is None
    assert "reconcil" in response["errors"][0].lower() or "check" in response["errors"][0].lower()