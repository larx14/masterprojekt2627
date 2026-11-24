
"""
Unit tests for the generic ERPNext mapping tool.

No live ERPNext connection is required.
"""

from copy import deepcopy

import pytest

from Agent.tools import erp_map
from Agent.tools.erpnext_client import ERPNextError
from Agent.tools.register_tools import create_tool_registry
from Agent.tools.registry import MAPPING_METHODS


SOURCE = "MAT-MR-2026-00038"

ARGS = {
    "source_doctype": "Material Request",
    "source_name": SOURCE,
    "target_doctype": "Purchase Order",
    "mapping_args": {
        "supplier": "Kettwig Farm",
    },
}

MAPPED_DOCUMENT = {
    "doctype": "Purchase Order",
    "docstatus": 0,
    "supplier": "Kettwig Farm",
    "items": [
        {
            "item_code": "RM-013",
            "qty": 1,
            "material_request": SOURCE,
            "material_request_item": "b5ac2m3ruu",
        }
    ],
}


def test_mapping_tool_is_registered():
    registry = create_tool_registry()

    specs = {
        spec["name"]: spec
        for spec in registry.get_specs()
    }

    executors = registry.get_executors()

    assert "erp_map_document" in specs
    assert "erp_map_document" in executors

    assert callable(
        getattr(
            executors["erp_map_document"],
            "invoke",
            None,
        )
    )


def test_mapping_uses_approved_method(monkeypatch):
    calls = []

    def fake_map_document(
        method,
        source_name,
        mapping_args=None,
    ):
        calls.append({
            "method": method,
            "source_name": source_name,
            "mapping_args": mapping_args,
        })
        return deepcopy(MAPPED_DOCUMENT)

    monkeypatch.setattr(
        erp_map.client,
        "map_document",
        fake_map_document,
    )

    result = erp_map.run_map_tool(
        "erp_map_document",
        deepcopy(ARGS),
    )

    assert result["status"] == "completed"
    assert result["result"]["mapped"] is True

    assert result["result"]["data"]["items"][0][
        "material_request_item"
    ] == "b5ac2m3ruu"

    assert len(calls) == 1

    assert calls[0]["method"] == MAPPING_METHODS[
        ("Material Request", "Purchase Order")
    ]

    assert calls[0]["source_name"] == SOURCE


@pytest.mark.parametrize(
    "source,target",
    [
        ("Material Request", "Supplier"),
        ("Supplier", "Purchase Order"),
        ("Purchase Invoice", "Sales Order"),
    ],
)
def test_unsupported_mapping_is_blocked(
    monkeypatch,
    source,
    target,
):
    def unexpected_call(**kwargs):
        pytest.fail(
            "Unsupported mappings must not reach ERPNext."
        )

    monkeypatch.setattr(
        erp_map.client,
        "map_document",
        unexpected_call,
    )

    args = {
        **ARGS,
        "source_doctype": source,
        "target_doctype": target,
        "mapping_args": {},
    }

    result = erp_map.run_map_tool(
        "erp_map_document",
        args,
    )

    assert result["status"] == "failed"


def test_wrong_target_doctype_is_rejected(monkeypatch):
    document = deepcopy(MAPPED_DOCUMENT)
    document["doctype"] = "Sales Order"

    monkeypatch.setattr(
        erp_map.client,
        "map_document",
        lambda **kwargs: document,
    )

    result = erp_map.run_map_tool(
        "erp_map_document",
        deepcopy(ARGS),
    )

    assert result["status"] == "failed"


def test_empty_items_are_rejected(monkeypatch):
    document = deepcopy(MAPPED_DOCUMENT)
    document["items"] = []

    monkeypatch.setattr(
        erp_map.client,
        "map_document",
        lambda **kwargs: document,
    )

    result = erp_map.run_map_tool(
        "erp_map_document",
        deepcopy(ARGS),
    )

    assert result["status"] == "failed"


def test_client_error_is_reported(monkeypatch):
    def failing_client(**kwargs):
        raise ERPNextError("Mapping unavailable.")

    monkeypatch.setattr(
        erp_map.client,
        "map_document",
        failing_client,
    )

    result = erp_map.run_map_tool(
        "erp_map_document",
        deepcopy(ARGS),
    )

    assert result["status"] == "failed"

    assert "Mapping unavailable" in (
        result["errors"][0]
    )


def test_registered_adapter_returns_business_result(
    monkeypatch,
):
    monkeypatch.setattr(
        erp_map.client,
        "map_document",
        lambda **kwargs: deepcopy(MAPPED_DOCUMENT),
    )

    registry = create_tool_registry()

    tool = registry.get_executors()[
        "erp_map_document"
    ]

    result = tool.invoke(deepcopy(ARGS))

    assert result["mapped"] is True
    assert result["target_doctype"] == "Purchase Order"
    assert isinstance(result["data"], dict)
