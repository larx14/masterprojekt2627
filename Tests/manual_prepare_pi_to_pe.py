"""Inspect an ERPNext-generated Payment Entry draft without saving it.

Example:
    python -m Tests.manual_prepare_pi_to_pe --invoice ACC-PINV-2026-XXXXX \
      --bank-account "Bank - MP" --reference-no TEST-PAY-001 \
      --reference-date 2026-11-24
"""
import argparse
from pprint import pprint

from Agent.tools.erp_map import run_map_tool
from Agent.tools.erpnext_client import get_doc
from Agent.tools.mapped_document_preparer import prepare_mapped_document


def prepare_payment(invoice_name: str, bank_account: str,
                    reference_no: str, reference_date: str) -> dict:
    invoice = get_doc("Purchase Invoice", invoice_name)
    if not invoice or invoice.get("docstatus") != 1:
        raise RuntimeError("The Purchase Invoice must exist and be submitted.")
    if not invoice.get("outstanding_amount") or invoice["outstanding_amount"] <= 0:
        raise RuntimeError("The Purchase Invoice has no outstanding balance.")
    mapped = run_map_tool("erp_map_document", {
        "source_doctype": "Purchase Invoice",
        "source_name": invoice_name,
        "target_doctype": "Payment Entry",
        "mapping_args": {"bank_account": bank_account, "reference_date": reference_date},
    })
    if mapped.get("status") != "completed":
        raise RuntimeError(f"Payment Entry mapping failed: {mapped}")
    return prepare_mapped_document(
        mapped["result"], source_document=invoice,
        verified_values={
            "bank_account": bank_account,
            "reference_no": reference_no,
            "reference_date": reference_date,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoice", required=True)
    parser.add_argument("--bank-account", required=True,
                        help="ERPNext company bank/cash GL Account name")
    parser.add_argument("--reference-no", required=True,
                        help="Verified TEST payment transaction reference")
    parser.add_argument("--reference-date", required=True,
                        help="YYYY-MM-DD")
    args = parser.parse_args()
    payload = prepare_payment(args.invoice, args.bank_account,
                              args.reference_no, args.reference_date)
    print("VALIDATED PAYMENT ENTRY CREATE ARGUMENTS:")
    pprint(payload)
    print("No Payment Entry was created or submitted.")


if __name__ == "__main__":
    main()
