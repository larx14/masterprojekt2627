
"""
Manual integration test for ERPNext-internal mapping.

Fetches a real Material Request and prepares a Purchase
Order without saving or submitting it.

Run against a dedicated ERPNext test instance.
"""

from pprint import pprint

from Agent.tools.erp_map import run_map_tool
from Agent.tools.erpnext_client import get_doc


SOURCE_NAME = "MAT-MR-2026-00038"


def main():
    source = get_doc(
        "Material Request",
        SOURCE_NAME,
    )

    if source is None:
        raise RuntimeError(
            "Source Material Request was not found."
        )

    if source.get("docstatus") != 1:
        raise RuntimeError(
            "Source Material Request must be submitted."
        )

    response = run_map_tool(
        "erp_map_document",
        {
            "source_doctype": "Material Request",
            "source_name": SOURCE_NAME,
            "target_doctype": "Purchase Order",
            "mapping_args": {
                "supplier": "Kettwig Farm",
            },
        },
    )

    if response.get("status") != "completed":
        raise RuntimeError(
            f"Mapping failed: {response}"
        )

    result = response["result"]
    document = result["data"]

    assert document["doctype"] == "Purchase Order"

    print("\nMAPPED PURCHASE ORDER")
    print("DocType:", document.get("doctype"))
    print("Supplier:", document.get("supplier"))
    print("Company:", document.get("company"))
    print("Docstatus:", document.get("docstatus"))

    print("\nMAPPED ITEMS")

    for item in document["items"]:
        pprint({
            "item_code": item.get("item_code"),
            "qty": item.get("qty"),
            "rate": item.get("rate"),
            "schedule_date": item.get("schedule_date"),
            "material_request": item.get(
                "material_request"
            ),
            "material_request_item": item.get(
                "material_request_item"
            ),
        })

    print("\nMAPPING COMPLETED SUCCESSFULLY")
    print("No Purchase Order was saved.")


if __name__ == "__main__":
    main()
