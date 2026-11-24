"""Unit tests for the profile-driven mapped-document preparer."""
from copy import deepcopy
import pytest

from Agent.tools.mapped_document_preparer import prepare_mapped_document

MR = {
    "doctype": "Material Request", "name": "MAT-MR-2026-00038", "docstatus": 1,
    "company": "Masterprojekt", "items": [{
        "name": "b5ac2m3ruu", "item_code": "RM-013", "qty": 1,
        "ordered_qty": 0,
    }],
}
PO_MAPPING = {
    "mapped": True, "source_doctype": "Material Request",
    "source_name": "MAT-MR-2026-00038", "target_doctype": "Purchase Order",
    "data": {
        "doctype": "Purchase Order", "docstatus": 0,
        "name": "TEMP", "owner": "ignored", "supplier": "Kettwig Farm",
        "company": "Masterprojekt", "items": [{
            "name": "TEMP-ROW", "item_code": "RM-013", "qty": 1,
            "schedule_date": "2026-12-08", "warehouse": "Raw Materials Store - MP",
            "material_request": "MAT-MR-2026-00038",
            "material_request_item": "b5ac2m3ruu",
        }],
    },
}
PO = {
    "doctype": "Purchase Order", "name": "PUR-ORD-2026-00046",
    "docstatus": 1, "supplier": "Kettwig Farm", "company": "Masterprojekt",
    "items": [{
        "name": "po-row-001", "item_code": "RM-013", "qty": 1,
        "rate": 1.5, "received_qty": 0,
    }],
}
PR_MAPPING = {
    "mapped": True, "source_doctype": "Purchase Order",
    "source_name": "PUR-ORD-2026-00046", "target_doctype": "Purchase Receipt",
    "data": {
        "doctype": "Purchase Receipt", "docstatus": 0,
        "supplier": "Kettwig Farm", "company": "Masterprojekt",
        "items": [{
            "name": "TEMP-ROW", "item_code": "RM-013", "qty": 1,
            "rate": 1.5, "received_qty": 1,
            "purchase_order": "PUR-ORD-2026-00046",
            "purchase_order_item": "po-row-001",
        }],
    },
}


def prepare_po(mapping=None, source=None, verified=None):
    return prepare_mapped_document(
        deepcopy(PO_MAPPING if mapping is None else mapping),
        source_document=deepcopy(MR if source is None else source),
        verified_values=deepcopy(
            {"supplier": "Kettwig Farm", "item_rates": {"RM-013": 1.5}}
            if verified is None else verified
        ),
    )


def prepare_pr(mapping=None, source=None, verified=None):
    return prepare_mapped_document(
        deepcopy(PR_MAPPING if mapping is None else mapping),
        source_document=deepcopy(PO if source is None else source),
        verified_values=deepcopy(
            {"warehouse": "Raw Materials Store - MP"} if verified is None else verified
        ),
    )


def test_po_success_and_strips_system_fields():
    args = prepare_po()
    assert args["doctype"] == "Purchase Order"
    assert args["data"]["items"][0]["rate"] == 1.5
    assert args["data"]["items"][0]["material_request_item"] == "b5ac2m3ruu"
    assert "owner" not in args["data"] and "name" not in args["data"]
    assert "name" not in args["data"]["items"][0]


def test_pr_success_and_strips_computed_fields():
    args = prepare_pr()
    assert args["doctype"] == "Purchase Receipt"
    item = args["data"]["items"][0]
    assert item["purchase_order"] == "PUR-ORD-2026-00046"
    assert item["purchase_order_item"] == "po-row-001"
    assert item["rate"] == 1.5 and item["warehouse"] == "Raw Materials Store - MP"
    assert "received_qty" not in item and "name" not in item


@pytest.mark.parametrize("field", ["mapped", "target_doctype"])
def test_invalid_mapping_status_or_target(field):
    mapping = deepcopy(PO_MAPPING)
    mapping[field] = False if field == "mapped" else "Supplier"
    with pytest.raises(ValueError):
        prepare_po(mapping=mapping)

def test_po_requires_supplier():
    with pytest.raises(ValueError, match="supplier"):
        prepare_po(verified={"supplier": "", "item_rates": {"RM-013": 1.5}})


@pytest.mark.parametrize("value", [None, 0, -1, "NaN", "Infinity", "oops"])
def test_po_rejects_bad_rate(value):
    with pytest.raises(ValueError):
        prepare_po(verified={"supplier": "Kettwig Farm", "item_rates": {"RM-013": value}})


@pytest.mark.parametrize("value", [None, 0, -1, "NaN", "oops"])
def test_pr_rejects_bad_qty(value):
    mapping = deepcopy(PR_MAPPING)
    mapping["data"]["items"][0]["qty"] = value
    with pytest.raises(ValueError):
        prepare_pr(mapping=mapping)


def test_po_rejects_wrong_source_reference():
    mapping = deepcopy(PO_MAPPING)
    mapping["data"]["items"][0]["material_request"] = "OTHER"
    with pytest.raises(ValueError, match="reference"):
        prepare_po(mapping=mapping)


def test_pr_rejects_unknown_po_item():
    mapping = deepcopy(PR_MAPPING)
    mapping["data"]["items"][0]["purchase_order_item"] = "UNKNOWN"
    with pytest.raises(ValueError, match="reference"):
        prepare_pr(mapping=mapping)


def test_pr_rejects_partially_received_po():
    source = deepcopy(PO)
    source["items"][0]["received_qty"] = 0.5
    with pytest.raises(ValueError, match="partially processed"):
        prepare_pr(source=source)


def test_pr_rejects_mismatched_supplier():
    mapping = deepcopy(PR_MAPPING)
    mapping["data"]["supplier"] = "Other Farm"
    with pytest.raises(ValueError, match="supplier"):
        prepare_pr(mapping=mapping)


def test_pr_rejects_excess_qty():
    mapping = deepcopy(PR_MAPPING)
    mapping["data"]["items"][0]["qty"] = 2
    with pytest.raises(ValueError, match="complete source quantity"):
        prepare_pr(mapping=mapping)


def test_pr_rejects_rate_mismatch():
    mapping = deepcopy(PR_MAPPING)
    mapping["data"]["items"][0]["rate"] = 100
    with pytest.raises(ValueError, match="rate"):
        prepare_pr(mapping=mapping)


def test_pr_rejects_rejected_goods():
    mapping = deepcopy(PR_MAPPING)
    mapping["data"]["items"][0]["rejected_qty"] = 0.5
    with pytest.raises(ValueError, match="Rejected"):
        prepare_pr(mapping=mapping)


def test_source_must_be_submitted():
    source = deepcopy(PO)
    source["docstatus"] = 0
    with pytest.raises(ValueError, match="submitted"):
        prepare_pr(source=source)


def test_pr_requires_warehouse():
    with pytest.raises(ValueError, match="warehouse"):
        prepare_pr(verified={})
