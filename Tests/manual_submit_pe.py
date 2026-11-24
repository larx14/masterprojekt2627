"""Submit one verified Payment Entry draft in an ERPNext test environment."""
import argparse
from decimal import Decimal

from Agent.tools.erp_submit import run_submit_tool
from Agent.tools.erpnext_client import get_doc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payment-entry", required=True)
    parser.add_argument("--invoice", required=True)
    args = parser.parse_args()
    pe = get_doc("Payment Entry", args.payment_entry)
    invoice = get_doc("Purchase Invoice", args.invoice)
    if not pe or pe.get("docstatus") != 0:
        raise RuntimeError("The Payment Entry must exist as a draft.")
    if not invoice or invoice.get("docstatus") != 1:
        raise RuntimeError("The Purchase Invoice must be submitted.")
    if pe.get("payment_type") != "Pay" or pe.get("party_type") != "Supplier":
        raise RuntimeError("Not an outgoing supplier payment.")
    if pe.get("company") != invoice.get("company") or pe.get("party") != invoice.get("supplier"):
        raise RuntimeError("Payment party or company differs from the invoice.")
    refs = pe.get("references") or []
    if not refs or any(
        ref.get("reference_doctype") != "Purchase Invoice" or ref.get("reference_name") != args.invoice
        for ref in refs
    ):
        raise RuntimeError("Payment references do not match the requested invoice.")
    balance = Decimal(str(invoice.get("outstanding_amount", 0)))
    allocation = sum((Decimal(str(ref["allocated_amount"])) for ref in refs), Decimal(0))
    if balance <= 0 or abs(balance - allocation) > Decimal("0.01"):
        raise RuntimeError("Invoice outstanding amount changed; do not submit this draft.")
    print("PAYMENT ENTRY:", args.payment_entry)
    print("INVOICE:", args.invoice)
    print("BANK / CASH ACCOUNT:", pe.get("paid_from"))
    print("PAYMENT TYPE:", pe.get("payment_type"))
    print("PAID AMOUNT:", pe.get("paid_amount"))
    print("ALLOCATED AMOUNT:", allocation)
    print("PAYMENT REFERENCE:", pe.get("reference_no"), pe.get("reference_date"))
    print("Review accounting entries and confirm that this is a test transaction.")
    if input("Type SUBMIT to post this Payment Entry: ") != "SUBMIT":
        print("Cancelled.")
        return
    result = run_submit_tool("erp_submit", {
        "doctype": "Payment Entry", "name": args.payment_entry,
    })
    if result.get("status") != "completed":
        raise RuntimeError(f"Submit failed or is unconfirmed; inspect ERPNext: {result}")
    confirmed = get_doc("Payment Entry", args.payment_entry)
    if not confirmed or confirmed.get("docstatus") != 1:
        raise RuntimeError("Submitted Payment Entry could not be verified.")
    print("PAYMENT ENTRY SUBMITTED:", args.payment_entry)


if __name__ == "__main__":
    main()
