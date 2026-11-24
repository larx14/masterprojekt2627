"""Payment Entry mapping and payload preparation tests (no live ERPNext)."""
from copy import deepcopy
import pytest

from Agent.tools import erp_map
from Agent.tools.mapped_document_preparer import prepare_mapped_document


INVOICE = {
    "doctype": "Purchase Invoice", "name": "ACC-PINV-TEST-001",
    "docstatus": 1, "company": "Masterprojekt", "supplier": "Kettwig Farm",
    "currency": "EUR", "company_currency": "EUR",
    "outstanding_amount": 1.5,
}
PE = {
    "doctype": "Payment Entry", "docstatus": 0,
    "payment_type": "Pay", "party_type": "Supplier",
    "company": "Masterprojekt", "party": "Kettwig Farm",
    "paid_from": "Test Bank - MP", "paid_to": "Creditors - MP",
    "paid_amount": 1.5, "received_amount": 1.5,
    "source_exchange_rate": 1, "target_exchange_rate": 1,
    "references": [{
        "reference_doctype": "Purchase Invoice",
        "reference_name": "ACC-PINV-TEST-001",
        "allocated_amount": 1.5,
    }],
    "name": "UNSAVED-ID", "owner": "system@example.org",
}
MAPPING = {
    "mapped": True, "source_doctype": "Purchase Invoice",
    "source_name": "ACC-PINV-TEST-001",
    "target_doctype": "Payment Entry", "data": PE,
}
VERIFIED = {
    "bank_account": "Test Bank - MP",
    "reference_no": "TEST-TRANSFER-001",
    "reference_date": "2026-11-24",
}


def prepare(mapped=None, invoice=None, verified=None):
    return prepare_mapped_document(
        deepcopy(MAPPING if mapped is None else mapped),
        source_document=deepcopy(INVOICE if invoice is None else invoice),
        verified_values=deepcopy(VERIFIED if verified is None else verified),
    )


def test_payment_entry_prepared_and_technical_fields_removed():
    result = prepare()
    assert result["doctype"] == "Payment Entry"
    d = result["data"]
    assert d["reference_no"] == VERIFIED["reference_no"]
    assert d["references"][0]["reference_name"] == INVOICE["name"]
    assert d["paid_from"] == VERIFIED["bank_account"]
    assert "owner" not in d and "name" not in d


@pytest.mark.parametrize("field,value", [
    ("payment_type", "Receive"), ("party", "Another Supplier"),
    ("paid_from", "Different Bank"), ("paid_amount", 0),
    ("source_exchange_rate", 1.2), ("references", []),
])
def test_invalid_payment_rejected(field, value):
    mapped = deepcopy(MAPPING)
    mapped["data"][field] = value
    with pytest.raises(ValueError):
        prepare(mapped=mapped)


def test_different_invoice_reference_rejected():
    mapped = deepcopy(MAPPING)
    mapped["data"]["references"][0]["reference_name"] = "DIFFERENT"
    with pytest.raises(ValueError):
        prepare(mapped=mapped)


def test_overallocation_rejected():
    mapped = deepcopy(MAPPING)
    mapped["data"]["references"][0]["allocated_amount"] = 3.0
    with pytest.raises(ValueError):
        prepare(mapped=mapped)


def test_draft_invoice_rejected():
    invoice = deepcopy(INVOICE)
    invoice["docstatus"] = 0
    with pytest.raises(ValueError):
        prepare(invoice=invoice)


def test_no_outstanding_balance_rejected():
    invoice = deepcopy(INVOICE)
    invoice["outstanding_amount"] = 0
    with pytest.raises(ValueError):
        prepare(invoice=invoice)


def test_missing_payment_reference_rejected():
    verified = deepcopy(VERIFIED)
    verified["reference_no"] = ""
    with pytest.raises(ValueError):
        prepare(verified=verified)


def test_rpc_mapping_uses_allowlisted_endpoint(monkeypatch):
    calls = []

    def fake_prepare(name, *, bank_account, reference_date=None):
        calls.append((name, bank_account, reference_date))
        return deepcopy(PE)

    monkeypatch.setattr(erp_map.client, "prepare_payment_entry", fake_prepare)
    result = erp_map.run_map_tool("erp_map_document", {
        "source_doctype": "Purchase Invoice", "source_name": INVOICE["name"],
        "target_doctype": "Payment Entry",
        "mapping_args": {
            "bank_account": VERIFIED["bank_account"],
            "reference_date": VERIFIED["reference_date"],
        },
    })
    assert result["status"] == "completed"
    assert calls == [(INVOICE["name"], VERIFIED["bank_account"], VERIFIED["reference_date"])]


def test_unsupported_rpc_option_rejected(monkeypatch):
    def prohibited(*args, **kwargs):
        pytest.fail("Unapproved request reached ERPNext")
    monkeypatch.setattr(erp_map.client, "prepare_payment_entry", prohibited)
    response = erp_map.run_map_tool("erp_map_document", {
        "source_doctype": "Purchase Invoice", "source_name": INVOICE["name"],
        "target_doctype": "Payment Entry",
        "mapping_args": {"bank_account": "Test Bank - MP", "method": "frappe.client.submit"},
    })
    assert response["status"] == "failed"
