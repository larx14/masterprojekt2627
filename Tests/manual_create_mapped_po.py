"""Manually create one Purchase Order draft from an ERPNext-internal mapping.

Creates a real document only after the operator enters CREATE.
Do not run against a production ERPNext instance.
"""
from pprint import pprint

from Agent.tools.erp_create import run_create_tool
from Agent.tools.erp_map import run_map_tool
from Agent.tools.erpnext_client import get_doc
from Agent.tools.mapped_document_preparer import prepare_mapped_purchase_order

SOURCE_NAME = "MAT-MR-2026-00038"
SOURCE_ITEM_NAME = "b5ac2m3ruu"
SUPPLIER = "Kettwig Farm"
RATES = {"RM-013": 1.5}


def main():
    source = get_doc("Material Request", SOURCE_NAME)
    if not isinstance(source, dict) or source.get("docstatus") != 1:
        raise RuntimeError("Source Material Request is not submitted.")

    mapped = run_map_tool("erp_map_document", {
        "source_doctype": "Material Request",
        "source_name": SOURCE_NAME,
        "target_doctype": "Purchase Order",
        "mapping_args": {"supplier": SUPPLIER},
    })
    if mapped.get("status") != "completed":
        raise RuntimeError(f"Mapping failed: {mapped}")

    create_args = prepare_mapped_purchase_order(
        mapped["result"], supplier=SUPPLIER, rates=RATES
    )
    prepared_items = create_args["data"]["items"]
    if len(prepared_items) != 1:
        raise RuntimeError("Unexpected number of mapped items.")
    if prepared_items[0]["material_request_item"] != SOURCE_ITEM_NAME:
        raise RuntimeError("Unexpected source item reference.")

    print("Prepared Purchase Order arguments:")
    pprint(create_args)
    print("\nThis operation will create a real Purchase Order draft.")
    if input("Type CREATE to proceed: ") != "CREATE":
        print("Cancelled. No Purchase Order was created.")
        return

    response = run_create_tool("erp_create", create_args)
    if response.get("status") != "completed":
        raise RuntimeError(
            "Creation failed or is unconfirmed. Check ERPNext before retrying: "
            f"{response}"
        )

    name = response["result"]["name"]
    print("Created Purchase Order:", name)
    po = get_doc("Purchase Order", name)
    if not isinstance(po, dict):
        raise RuntimeError("Created Purchase Order could not be retrieved.")
    if po.get("docstatus") != 0 or po.get("supplier") != SUPPLIER:
        raise AssertionError("Unexpected Purchase Order status or supplier.")

    items = po.get("items") or []
    if len(items) != 1:
        raise AssertionError("Unexpected number of Purchase Order items.")
    item = items[0]
    assert item["material_request"] == SOURCE_NAME
    assert item["material_request_item"] == SOURCE_ITEM_NAME
    assert item["item_code"] == "RM-013"
    assert abs(float(item["qty"]) - 1.0) < 0.000001
    assert abs(float(item["rate"]) - 1.5) < 0.000001

    print("Purchase Order verified:", name)
    print("Draft only; no submission was performed.")


if __name__ == "__main__":
     main()
