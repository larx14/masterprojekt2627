"""Manually submit a verified Purchase Receipt in a test instance.

Submitting changes inventory stock ledgers. Requires explicit confirmation.
"""
from Agent.tools.erpnext_client import get_doc
from Agent.tools.erp_submit import run_submit_tool

PR_NAME = "MAT-PRE-2026-00031"
PO_NAME = "PUR-ORD-2026-00046"


def main():
    if PR_NAME.startswith("REPLACE_"):
        raise RuntimeError("Set PR_NAME to the newly created Purchase Receipt name.")
    receipt = get_doc("Purchase Receipt", PR_NAME)
    if receipt is None or receipt.get("docstatus") != 0:
        raise RuntimeError("Purchase Receipt not found or not in draft status.")
    for item in receipt.get("items") or []:
        if item.get("purchase_order") != PO_NAME:
            raise RuntimeError("Receipt references an unexpected Purchase Order.")
    print("PURCHASE RECEIPT:", PR_NAME)
    print("SUPPLIER:", receipt.get("supplier"))
    print("ITEMS:", [(x.get("item_code"), x.get("qty"), x.get("warehouse")) for x in receipt.get("items") or []])
    if input("Type SUBMIT to post this receipt to ERPNext stock: ") != "SUBMIT":
        print("Cancelled.")
        return
    response = run_submit_tool("erp_submit", {"doctype": "Purchase Receipt", "name": PR_NAME})
    if response.get("status") != "completed":
        raise RuntimeError(f"Submission failed or unconfirmed. Inspect ERPNext before retrying: {response}")
    updated = get_doc("Purchase Receipt", PR_NAME)
    if updated is None or updated.get("docstatus") != 1:
        raise RuntimeError("Purchase Receipt submission could not be verified.")
    print("SUBMITTED PURCHASE RECEIPT:", PR_NAME)

if __name__ == "__main__":
    main()