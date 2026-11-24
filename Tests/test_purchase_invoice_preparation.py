"""Tests for receipt-to-invoice preparation; no ERPNext connection."""

from copy import deepcopy
from datetime import date

import pytest

from Agent.tools.mapped_document_preparer import prepare_mapped_document

SOURCE = {
    "doctype": "Purchase Receipt", "name": "MAT-PRE-2026-00001",
    "docstatus": 1, "supplier": "Kettwig Farm", "company": "Masterprojekt",
    "items": [{
        "name": "pr-row-001", "item_code": "RM-013", "qty": 1.0,
        "rate": 1.5, "billed_amt": 0.0,
        "purchase_order": "PUR-ORD-2026-00046",
        "purchase_order_item": "vt4o3re0u6",
    }],
}
MAPPING = {
    "mapped": True, "source_doctype": "Purchase Receipt",
    "source_name": SOURCE["name"], "target_doctype": "Purchase Invoice",
    "data": {
        "doctype": "Purchase Invoice", "docstatus": 0,
        "name": "TEMP-DOC", "owner": "ignored", "supplier": "Kettwig Farm",
        "company": "Masterprojekt", "update_stock": 0,
        "items": [{
            "name": "TEMP-ROW", "item_code": "RM-013", "qty": 1.0,
            "rate": 1.5, "purchase_receipt": SOURCE["name"],
            "pr_detail": "pr-row-001", "purchase_order": "PUR-ORD-2026-00046",
            "po_detail": "vt4o3re0u6",
        }],
},
}


def prepare(mapping=None, source=None, verified=None):
    return prepare_mapped_document(
        deepcopy(MAPPING if mapping is None else mapping),
        source_document=deepcopy(SOURCE if source is None else source),
        verified_values=deepcopy({
            "bill_no": "MVP-INV-TEST-001", "bill_date": date.today().isoformat(),
        } if verified is None else verified),
    )


def test_purchase_invoice_payload_preserves_receipt_links_and_drops_system_fields():
    args = prepare()
    assert args["doctype"] == "Purchase Invoice"
    assert args["data"]["bill_no"] == "MVP-INV-TEST-001"
    assert args["data"]["update_stock"] == 0
    item = args["data"]["items"][0]
    assert item["purchase_receipt"] == SOURCE["name"]
    assert item["pr_detail"] == "pr-row-001"
    assert item["po_detail"] == "vt4o3re0u6"
    assert item["rate"] == 1.5
    assert "name" not in args["data"] and "name" not in item


@pytest.mark.parametrize("verified", [
    {"bill_no": "", "bill_date": "2026-11-24"},
    {"bill_no": "MVP-INV-TEST-001", "bill_date": "no-date"},
    {"bill_no": "MVP-INV-TEST-001"},
])
def test_missing_or_invalid_invoice_metadata_is_blocked(verified):
    with pytest.raises(ValueError):
        prepare(verified=verified)


def test_unknown_receipt_item_is_blocked():
    mapping = deepcopy(MAPPING)
    mapping["data"]["items"][0]["pr_detail"] = "unknown"
    with pytest.raises(ValueError):
        prepare(mapping=mapping)


def test_partially_billed_receipt_is_blocked():
    source = deepcopy(SOURCE)
    source["items"][0]["billed_amt"] = 0.50
    with pytest.raises(ValueError, match="partially processed"):
        prepare(source=source)


def test_inconsistent_po_reference_is_blocked():
    mapping = deepcopy(MAPPING)
    mapping["data"]["items"][0]["po_detail"] = "different"
    with pytest.raises(ValueError):
        prepare(mapping=mapping)


def test_update_stock_is_blocked():
    mapping = deepcopy(MAPPING)
    mapping["data"]["update_stock"] = 1
    with pytest.raises(ValueError):
        prepare(mapping=mapping)


def test_missing_rate_is_blocked():
    source = deepcopy(SOURCE)
    source["items"][0]["rate"] = 0
    with pytest.raises(ValueError):
        prepare(source=source)


def test_wrong_supplier_is_blocked():
    mapping = deepcopy(MAPPING)
    mapping["data"]["supplier"] = "Other"
    with pytest.raises(ValueError):
        prepare(mapping=mapping)