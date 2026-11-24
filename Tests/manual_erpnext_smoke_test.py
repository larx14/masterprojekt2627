
"""
Manual ERPNext integration smoke test.

Creates one real Material Request draft and verifies
that it can be retrieved from ERPNext.

Run only against a dedicated test instance.
"""

from datetime import date, timedelta

from Agent.tools.erp_create import run_create_tool
from Agent.tools.erpnext_client import get_doc


def main():
    schedule_date = (
        date.today() + timedelta(days=14)
    ).isoformat()

    response = run_create_tool(
        "erp_create",
        {
            "doctype": "Material Request",
            "data": {
                "material_request_type": "Purchase",
                "items": [
                    {
                        "item_code": "RM-013",
                        "qty": 1,
                        "schedule_date": schedule_date,
                        "warehouse": "Raw Materials Store - MP",
                    }
                ],
            },
        },
    )

    print("CREATE RESPONSE:", response)

    if response.get("status") != "completed":
        raise RuntimeError(
            "Material Request creation failed or "
            "could not be confirmed."
        )

    result = response["result"]
    name = result["name"]

    document = get_doc("Material Request", name)

    if document is None:
        raise RuntimeError(
            "Created Material Request could not be retrieved."
        )

    assert document["name"] == name
    assert document["docstatus"] == 0

    print("VERIFIED MATERIAL REQUEST:", name)


if __name__ == "__main__":
    main()
