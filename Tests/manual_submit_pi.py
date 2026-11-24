"""Submit a reviewed Purchase Invoice in a dedicated ERPNext test instance."""

from Agent.tools.erpnext_client import get_doc
from Agent.tools.erp_submit import run_submit_tool

PI_NAME = "ACC-PINV-2026-00032"


def main():
    if PI_NAME.startswith("REPLACE_"):
        raise RuntimeError("Set PI_NAME to the actual Purchase Invoice number.")
    invoice = get_doc("Purchase Invoice", PI_NAME)
    if not isinstance(invoice, dict) or invoice.get("docstatus") != 0:
        raise RuntimeError("Purchase Invoice is missing or not a draft.")
    print("Purchase Invoice:", PI_NAME)
    print("Supplier:", invoice.get("supplier"))
    print("Supplier invoice number:", invoice.get("bill_no"))
    print("Grand total:", invoice.get("grand_total"), invoice.get("currency"))
    print("Items:", [(x.get("item_code"), x.get("qty"), x.get("rate")) for x in invoice.get("items", [])])
    if input("Type SUBMIT to post this Purchase Invoice: ") != "SUBMIT":
        print("Cancelled.")
        return
    response = run_submit_tool("erp_submit", {
        "doctype": "Purchase Invoice", "name": PI_NAME,
    })
    if response.get("status") != "completed":
        raise RuntimeError(f"Submission not confirmed: {response}. Verify ERPNext before retrying.")
    submitted = get_doc("Purchase Invoice", PI_NAME)
    if not isinstance(submitted, dict) or submitted.get("docstatus") != 1:
        raise RuntimeError("Submitted Purchase Invoice could not be verified.")
    print("SUBMITTED PURCHASE INVOICE VERIFIED:", PI_NAME)


if __name__ == "__main__":
    main()
