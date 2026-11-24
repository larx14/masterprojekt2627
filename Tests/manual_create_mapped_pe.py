"""Create one real Payment Entry draft after explicit user confirmation."""
import argparse
from pprint import pprint

from Agent.tools.erp_create import run_create_tool
from Agent.tools.erpnext_client import get_doc
from Tests.manual_prepare_pi_to_pe import prepare_payment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoice", required=True)
    parser.add_argument("--bank-account", required=True)
    parser.add_argument("--reference-no", required=True)
    parser.add_argument("--reference-date", required=True)
    args = parser.parse_args()
    create_args = prepare_payment(args.invoice, args.bank_account,
                                  args.reference_no, args.reference_date)
    pprint(create_args)
    if input("Type CREATE to save a Payment Entry draft: ") != "CREATE":
        print("Cancelled.")
        return
    response = run_create_tool("erp_create", create_args)
    if response.get("status") != "completed":
        raise RuntimeError(
            f"Creation failed or is unconfirmed. Inspect ERPNext before retrying: {response}"
        )
    name = response["result"]["name"]
    saved = get_doc("Payment Entry", name)
    if not saved or saved.get("docstatus") != 0:
        raise RuntimeError("Payment Entry draft was not confirmed.")
    if saved.get("party") != create_args["data"]["party"]:
        raise RuntimeError("Saved payment party does not match.")
    if not any(
        row.get("reference_doctype") == "Purchase Invoice"
        and row.get("reference_name") == args.invoice
        for row in saved.get("references", [])
    ):
        raise RuntimeError("The saved payment does not reference the expected invoice.")
    print("PAYMENT ENTRY DRAFT VERIFIED:", name)
    print("No submit was performed.")


if __name__ == "__main__":
    main()
