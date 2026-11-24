"""Manually submit a previously verified Purchase Order in a test instance."""

from Agent.tools.erp_submit import run_submit_tool
from Agent.tools.erpnext_client import get_doc

# Replace with the actual name printed by manual_create_mapped_po.py.
PURCHASE_ORDER_NAME = "PUR-ORD-2026-00046"


def main():
    if PURCHASE_ORDER_NAME == "REPLACE_WITH_PURCHASE_ORDER_NAME":
        raise RuntimeError("Set PURCHASE_ORDER_NAME before running.")

    po = get_doc("Purchase Order", PURCHASE_ORDER_NAME)
    if not isinstance(po, dict) or po.get("docstatus") != 0:
        raise RuntimeError("Purchase Order must exist and be a draft.")
    print("Purchase Order:", po["name"])
    print("Supplier:", po.get("supplier"))
    print("Items:", [(i.get("item_code"), i.get("qty"), i.get("rate")) for i in po.get("items", [])])
    if input("Type SUBMIT to submit this Purchase Order: ") != "SUBMIT":
        print("Cancelled.")
        return

    response = run_submit_tool(
        "erp_submit", {"doctype": "Purchase Order", "name": PURCHASE_ORDER_NAME}
    )
    if response.get("status") != "completed":
        raise RuntimeError(f"Submit failed or is unconfirmed: {response}")

    verified = get_doc("Purchase Order", PURCHASE_ORDER_NAME)
    if not isinstance(verified, dict) or verified.get("docstatus") != 1:
        raise RuntimeError("Submission could not be verified.")
    print("Purchase Order submitted and verified:", PURCHASE_ORDER_NAME)


if __name__ == "__main__":
    main()
