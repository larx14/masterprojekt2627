"""Create and verify a Purchase Invoice draft after explicit confirmation.

Only run against a dedicated ERPNext test instance. Do not retry uncertain writes.
"""

from pprint import pprint

from Agent.tools.erp_create import run_create_tool
from Agent.tools.erpnext_client import get_doc
from Tests.manual_prepare_pr_to_pi import prepare_invoice, PR_NAME


def main():
    args = prepare_invoice()
    print("PURCHASE INVOICE CREATE ARGUMENTS:")
    pprint(args)
    print("Verify there is no existing invoice for this receipt and supplier invoice number.")
    if input("Type CREATE to save a real Purchase Invoice draft: ") != "CREATE":
        print("Cancelled.")
        return

    response = run_create_tool("erp_create", args)
    if response.get("status") != "completed":
        raise RuntimeError(
            f"Create was not confirmed: {response}. Inspect ERPNext before retrying."
        )
    name = response["result"]["name"]
    invoice = get_doc("Purchase Invoice", name)
    if not isinstance(invoice, dict) or invoice.get("docstatus") != 0:
        raise RuntimeError("Created Purchase Invoice could not be verified.")
    if invoice.get("bill_no") != args["data"]["bill_no"]:
        raise RuntimeError("Supplier invoice number does not match.")
    if invoice.get("supplier") != args["data"]["supplier"]:
        raise RuntimeError("Supplier does not match.")
    expected_items = {item["pr_detail"]: item for item in args["data"]["items"]}
    actual_items = invoice.get("items", [])
    if len(actual_items) != len(expected_items):
        raise RuntimeError("Invoice item count does not match.")
    for actual in actual_items:
        expected = expected_items.get(actual.get("pr_detail"))
        if (
            expected is None
            or actual.get("purchase_receipt") != PR_NAME
            or actual.get("item_code") != expected["item_code"]
            or abs(float(actual.get("qty", 0)) - expected["qty"]) > 1e-9
            or abs(float(actual.get("rate", 0)) - expected["rate"]) > 1e-9
        ):
            raise RuntimeError("Invoice item links, quantities or rate do not match.")
    print("VERIFIED PURCHASE INVOICE DRAFT:", name)
    print("Grand total:", invoice.get("grand_total"))
    print("Currency:", invoice.get("currency"))
    print("No submit was performed.")


if __name__ == "__main__":
    main()
