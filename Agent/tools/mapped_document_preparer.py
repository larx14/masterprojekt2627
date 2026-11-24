"""Prepare ERPNext-mapped documents for the generic erp_create tool.

This module never calls ERPNext and never saves a document.
It supports a deliberately restricted full-quantity MVP path.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from Agent.tools.registry import MAPPED_DOCUMENT_PROFILES


def _positive_number(value: Any, label: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a valid number.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a valid number.") from exc
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{label} must be {'non-negative' if allow_zero else 'positive'}.")
    return float(number)


def _copy_allowed(source: dict, allowed: tuple[str, ...]) -> dict:
    return {key: source[key] for key in allowed if source.get(key) is not None}

def _prepare_payment_entry(
    mapping_result: dict[str, Any],
    source_document: dict[str, Any],
    verified: dict[str, Any],
) -> dict[str, Any]:
    """Validate and sanitize a full, single-invoice supplier payment.

    For this MVP, foreign-currency payments, deductions, advances, and
    split payments are unsupported. The invoice is the authority for the
    outstanding amount, supplier, and company.
    """
    from datetime import date
    from Agent.tools.registry import PAYMENT_ENTRY_PROFILE

    invoice_name = source_document["name"]
    doc = mapping_result.get("data")
    if not isinstance(doc, dict) or doc.get("doctype") != "Payment Entry":
        raise ValueError("Mapped Payment Entry document is invalid.")
    if doc.get("docstatus", 0) != 0:
        raise ValueError("Mapped Payment Entry must be a draft.")
    if doc.get("payment_type") != "Pay" or doc.get("party_type") != "Supplier":
        raise ValueError("Expected a supplier outgoing payment.")
    if doc.get("party") != source_document.get("supplier"):
        raise ValueError("Payment supplier does not match the invoice.")
    if doc.get("company") != source_document.get("company"):
        raise ValueError("Payment company does not match the invoice.")

    bank_account = verified.get("bank_account")
    reference_no = verified.get("reference_no")
    reference_date = verified.get("reference_date")
    if not isinstance(bank_account, str) or not bank_account.strip():
        raise ValueError("A verified company bank/cash account is required.")
    if doc.get("paid_from") != bank_account:
        raise ValueError("Payment source account does not match verified account.")
    if not isinstance(doc.get("paid_to"), str) or not doc["paid_to"].strip():
        raise ValueError("Payment destination account is missing.")
    if not isinstance(reference_no, str) or not reference_no.strip():
        raise ValueError("A verified payment transaction reference is required.")
    if not isinstance(reference_date, str):
        raise ValueError("A verified payment reference date is required.")
    try:
        date.fromisoformat(reference_date)
    except ValueError as exc:
        raise ValueError("Payment reference date must be YYYY-MM-DD.") from exc

    if doc.get("reference_no") not in (None, "", reference_no):
        raise ValueError("Mapped payment reference conflicts with verified data.")
    if doc.get("reference_date") not in (None, "", reference_date):
        raise ValueError("Mapped payment reference date conflicts with verified data.")
    if doc.get("deductions") or doc.get("taxes"):
        raise ValueError("Deductions and payment taxes are not supported in this MVP.")
    for key in ("source_exchange_rate", "target_exchange_rate"):
        if doc.get(key) is not None and Decimal(str(doc[key])) != 1:
            raise ValueError("Foreign currency payments are not supported in this MVP.")
    if source_document.get("currency") and source_document.get("company_currency"):
        if source_document["currency"] != source_document["company_currency"]:
            raise ValueError("Foreign currency invoices are not supported in this MVP.")

    outstanding = Decimal(str(_positive_number(
        source_document.get("outstanding_amount"), "Invoice outstanding amount"
    )))
    references = doc.get("references")
    if not isinstance(references, list) or not references:
        raise ValueError("Payment Entry has no invoice references.")
    cleaned = []
    allocation = Decimal("0")
    for ref in references:
        if not isinstance(ref, dict):
            raise ValueError("Invalid Payment Entry reference row.")
        if ref.get("reference_doctype") != "Purchase Invoice" or ref.get("reference_name") != invoice_name:
            raise ValueError("Payment Entry references an unexpected invoice.")
        amount = Decimal(str(_positive_number(ref.get("allocated_amount"), "Allocated amount")))
        allocation += amount
        clean = _copy_allowed(ref, PAYMENT_ENTRY_PROFILE["reference_fields"])
        clean["allocated_amount"] = float(amount)
        cleaned.append(clean)
    if abs(allocation - outstanding) > Decimal("0.01"):
        raise ValueError("MVP requires full allocation of the outstanding invoice amount.")

    paid = _positive_number(doc.get("paid_amount"), "Paid amount")
    received = _positive_number(doc.get("received_amount"), "Received amount")
    if abs(Decimal(str(received)) - outstanding) > Decimal("0.01"):
        raise ValueError("Payment amount does not match the invoice outstanding amount.")
    if abs(Decimal(str(paid)) - Decimal(str(received))) > Decimal("0.01"):
        raise ValueError("MVP requires equal paid and received amounts.")
    header = _copy_allowed(doc, PAYMENT_ENTRY_PROFILE["header_fields"])
    header["paid_amount"] = paid
    header["received_amount"] = received
    header["reference_no"] = reference_no
    header["reference_date"] = reference_date
    header["references"] = cleaned
    return {"doctype": "Payment Entry", "data": header}

def prepare_mapped_document(
    mapping_result: dict[str, Any],
    *,
    source_document: dict[str, Any],
    verified_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return sanitized erp_create arguments from an approved mapped document.

    Source documents must be submitted. The first MVP only supports full
    quantities that have not already been ordered/received.
    """
    if not isinstance(mapping_result, dict) or mapping_result.get("mapped") is not True:
        raise ValueError("Mapping was not successful.")
    if not isinstance(source_document, dict):
        raise ValueError("Source document must be a dictionary.")
    verified = verified_values or {}
    if not isinstance(verified, dict):
        raise ValueError("Verified values must be a dictionary.")

    target = mapping_result.get("target_doctype")
    profile = MAPPED_DOCUMENT_PROFILES.get(target)
    if profile is None:
        raise ValueError(f"Unsupported mapped target DocType: {target!r}.")
    source_type = profile["source_doctype"]
    source_name = mapping_result.get("source_name")
    if (
        mapping_result.get("source_doctype") != source_type
        or source_document.get("doctype") != source_type
        or not isinstance(source_name, str)
        or not source_name
        or source_document.get("name") != source_name
    ):
        raise ValueError("Source document reference does not match.")
    if source_document.get("docstatus") != 1:
        raise ValueError("Source document must be submitted.")

    if target == "Payment Entry":
        return _prepare_payment_entry(mapping_result, source_document, verified)

    document = mapping_result.get("data")
    if not isinstance(document, dict) or document.get("doctype") != target:
        raise ValueError("Mapped document has an unexpected DocType.")
    if document.get("docstatus", 0) != 0:
        raise ValueError("Mapped document must be a draft.")

    if document.get("company") != source_document.get("company"):
        raise ValueError("Mapped company does not match source document.")
    if target == "Purchase Order":
        supplier = verified.get("supplier")
        rates = verified.get("item_rates")
        if not isinstance(supplier, str) or not supplier.strip():
            raise ValueError("A verified supplier is required.")
        if document.get("supplier") not in (None, "", supplier):
            raise ValueError("Mapped supplier does not match verified supplier.")
        if not isinstance(rates, dict):
            raise ValueError("Verified item rates are required.")
    else:
        if not document.get("supplier") or document.get("supplier") != source_document.get("supplier"):
            raise ValueError("Mapped supplier does not match source document.")
        if target == "Purchase Receipt":
            warehouse = verified.get("warehouse")
            if not isinstance(warehouse, str) or not warehouse.strip():
                raise ValueError("A verified warehouse is required.")
        elif target == "Purchase Invoice":
            from datetime import date

            bill_no = verified.get("bill_no")
            bill_date = verified.get("bill_date")
            if not isinstance(bill_no, str) or not bill_no.strip():
                raise ValueError("A verified supplier invoice number is required.")
            if not isinstance(bill_date, str):
                raise ValueError("A verified supplier invoice date is required.")
            try:
                date.fromisoformat(bill_date)
            except ValueError as exc:
                raise ValueError("Supplier invoice date must be YYYY-MM-DD.") from exc
            if document.get("bill_no") not in (None, "", bill_no):
                raise ValueError("Mapped supplier invoice number conflicts with verified data.")
            if document.get("bill_date") not in (None, "", bill_date):
                raise ValueError("Mapped supplier invoice date conflicts with verified data.")
            if document.get("update_stock") not in (None, 0, False):
                raise ValueError("Stock updates are not allowed for receipt-based invoices.")

    source_items = source_document.get("items")
    mapped_items = document.get("items")
    if not isinstance(source_items, list) or not source_items:
        raise ValueError("Source document has no items.")
    if not isinstance(mapped_items, list) or not mapped_items:
        raise ValueError("Mapped document has no items.")

    by_id = {}
    for source_item in source_items:
        if not isinstance(source_item, dict) or not source_item.get("name"):
            raise ValueError("Source item name is missing.")
        if source_item["name"] in by_id:
            raise ValueError("Duplicate source item identifiers.")
        by_id[source_item["name"]] = source_item

    header = _copy_allowed(document, profile["header_fields"])
    if target == "Purchase Order":
        header["supplier"] = supplier
    elif target == "Purchase Invoice":
        header["bill_no"] = bill_no
        header["bill_date"] = bill_date
        header["update_stock"] = 0
    prepared_items = []
    seen = set()
    for item in mapped_items:
        if not isinstance(item, dict):
            raise ValueError("Invalid mapped item.")
        if item.get(profile["source_reference"]) != source_name:
            raise ValueError("Mapped document reference does not match.")
        row_id = item.get(profile["source_item_reference"])
        if not isinstance(row_id, str) or row_id not in by_id:
            raise ValueError("Mapped item reference is missing or unknown.")
        if row_id in seen:
            raise ValueError("A source item is mapped more than once.")
        seen.add(row_id)
        original = by_id[row_id]
        if original.get("item_code") != item.get("item_code"):
            raise ValueError("Mapped item code does not match source item.")

        quantity = _positive_number(item.get("qty"), "Mapped quantity")
        source_qty = _positive_number(original.get("qty"), "Source quantity")
        if Decimal(str(quantity)) != Decimal(str(source_qty)):
            raise ValueError("MVP requires the complete source quantity.")
        already_used_field = profile["already_used_field"]
        already_used = _positive_number(
            original.get(already_used_field, 0),
            already_used_field,
            allow_zero=True,
        )
        if already_used != 0:
            raise ValueError("Source item has already been partially processed.")

        prepared = _copy_allowed(item, profile["item_fields"])
        prepared["qty"] = quantity
        if target == "Purchase Order":
            if not item.get("schedule_date"):
                raise ValueError("Schedule date is required.")
            if item["item_code"] not in rates:
                raise ValueError("Verified rate is missing for mapped item.")
            prepared["rate"] = _positive_number(rates[item["item_code"]], "Verified rate")
        elif target == "Purchase Receipt":
            # The recorded source PO rate is authoritative for this MVP.
            source_rate = _positive_number(original.get("rate"), "Source PO rate")
            prepared["rate"] = source_rate
            if item.get("rate") is not None:
                mapped_rate = _positive_number(item["rate"], "Mapped rate", allow_zero=True)
                if Decimal(str(mapped_rate)) not in (Decimal("0"), Decimal(str(source_rate))):
                    raise ValueError("Mapped rate differs from the Purchase Order.")
            prepared["warehouse"] = warehouse
            # Explicitly reject rejected goods in this first MVP.
            rejected_qty = _positive_number(item.get("rejected_qty", 0), "Rejected quantity", allow_zero=True)
            if rejected_qty:
                raise ValueError("Rejected goods are not supported in this MVP.")
            # Do not forward computed received_qty; ERPNext calculates it.
            prepared.pop("received_qty", None)
        elif target == "Purchase Invoice":
            source_rate = _positive_number(original.get("rate"), "Source PR rate")
            mapped_rate = item.get("rate")
            if mapped_rate is not None:
                mapped_value = _positive_number(mapped_rate, "Mapped invoice rate", allow_zero=True)
                if Decimal(str(mapped_value)) not in (Decimal("0"), Decimal(str(source_rate))):
                    raise ValueError("Mapped invoice rate differs from the Purchase Receipt.")
            prepared["rate"] = source_rate
            if item.get("purchase_order") and original.get("purchase_order"):
                if item["purchase_order"] != original["purchase_order"]:
                    raise ValueError("Mapped Purchase Order reference differs from the receipt.")
            if item.get("po_detail") and original.get("purchase_order_item"):
                if item["po_detail"] != original["purchase_order_item"]:
                    raise ValueError("Mapped Purchase Order item reference differs from the receipt.")
        prepared_items.append(prepared)

    if len(seen) != len(by_id):
        raise ValueError("MVP requires every source item to be mapped exactly once.")

    for field in profile["required_header_fields"]:
        if header.get(field) in (None, ""):
            raise ValueError(f"Required header field is missing: {field}.")
    for item in prepared_items:
        for field in profile["required_item_fields"]:
            if item.get(field) in (None, ""):
                raise ValueError(f"Required item field is missing: {field}.")

    header["items"] = prepared_items
    return {"doctype": target, "data": header}
