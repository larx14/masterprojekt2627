"""Create and verify a Purchase Receipt draft after explicit confirmation.

Run only in a dedicated ERPNext test environment. Never blindly retry a
write if ERPNext returns an error or an unconfirmed response.
"""

from pprint import pprint

from Agent.tools.erpnext_client import get_doc
from Agent.tools.erp_map import run_map_tool
from Agent.tools.erp_create import run_create_tool
from Agent.tools.mapped_document_preparer import prepare_mapped_document

PO_NAME = "PUR-ORD-2026-00046"
WAREHOUSE = "Raw Materials Store - MP"


def main():
    po = get_doc("Purchase Order", PO_NAME)
    if not isinstance(po, dict) or po.get("docstatus") != 1:
        raise RuntimeError("Purchase Order is missing or not submitted.")

    mapped = run_map_tool("erp_map_document", {
        "source_doctype": "Purchase Order",
        "source_name": PO_NAME,
        "target_doctype": "Purchase Receipt",
        "mapping_args": {},
    })
    if mapped.get("status") != "completed":
        raise RuntimeError(f"Mapping failed: {mapped}")

    args = prepare_mapped_document(
        mapped["result"], source_document=po,
        verified_values={"warehouse": WAREHOUSE},
    )
    print("CREATE ARGUMENTS:")
    pprint(args)
    print("Check in ERPNext that no Purchase Receipt draft already exists for this PO.")
    if input("Type CREATE to save a real Purchase Receipt draft: ") != "CREATE":
        print("Cancelled.")
        return

    created = run_create_tool("erp_create", args)
    if created.get("status") != "completed":
        raise RuntimeError(
            f"Create was not confirmed: {created}. Check ERPNext before retrying."
        )
    name = created["result"]["name"]
    receipt = get_doc("Purchase Receipt", name)
    if not isinstance(receipt, dict) or receipt.get("docstatus") != 0:
        raise RuntimeError("Saved Purchase Receipt could not be verified.")

    expected_items = {
        item["purchase_order_item"]: item for item in args["data"]["items"]
    }
    actual_items = receipt.get("items", [])
    if len(actual_items) != len(expected_items):
        raise RuntimeError("Saved receipt item count does not match.")
    for item in actual_items:
        expected = expected_items.get(item.get("purchase_order_item"))
        if (
            expected is None or item.get("purchase_order") != PO_NAME
            or item.get("item_code") != expected["item_code"]
            or abs(float(item.get("qty", 0)) - expected["qty"]) > 1e-9
            or item.get("warehouse") != WAREHOUSE
        ):
            raise RuntimeError("Saved receipt reference or item data mismatch.")
    print("VERIFIED PURCHASE RECEIPT DRAFT:", name)
    print("No submit was performed.")


if __name__ == "__main__":
    main()