"""Preview a mapped Purchase Invoice from a submitted Purchase Receipt.

Does not create or submit any ERPNext document.
"""

from datetime import date
from pprint import pprint

from Agent.tools.erpnext_client import get_doc
from Agent.tools.erp_map import run_map_tool
from Agent.tools.mapped_document_preparer import prepare_mapped_document

PR_NAME = "MAT-PRE-2026-00031"
BILL_NO = "MVP-TEST-INV-001"  # Replace with a unique, verified test invoice number.
BILL_DATE = date.today().isoformat()  # Replace with the actual test invoice date.


def prepare_invoice():
    if PR_NAME.startswith("REPLACE_"):
        raise RuntimeError("Set PR_NAME to your submitted Purchase Receipt number.")
    source = get_doc("Purchase Receipt", PR_NAME)
    if not isinstance(source, dict) or source.get("docstatus") != 1:
        raise RuntimeError("Purchase Receipt is missing or not submitted.")

    mapping = run_map_tool("erp_map_document", {
        "source_doctype": "Purchase Receipt",
        "source_name": PR_NAME,
        "target_doctype": "Purchase Invoice",
        "mapping_args": {},
    })
    if mapping.get("status") != "completed":
        raise RuntimeError(f"Mapping failed: {mapping}")

    args = prepare_mapped_document(
        mapping["result"],
        source_document=source,
        verified_values={"bill_no": BILL_NO, "bill_date": BILL_DATE},
    )
    return args


def main():
    args = prepare_invoice()
    print("VALIDATED ERP_CREATE ARGUMENTS:")
    pprint(args)
    print("No Purchase Invoice was created or submitted.")


if __name__ == "__main__":
    main()