"""Verify a mapped Purchase Receipt payload without creating any documents."""

from pprint import pprint

from Agent.tools.erpnext_client import get_doc
from Agent.tools.erp_map import run_map_tool
from Agent.tools.mapped_document_preparer import prepare_mapped_document

PO_NAME = "PUR-ORD-2026-00046"
WAREHOUSE = "Raw Materials Store - MP"


def main():
    source = get_doc("Purchase Order", PO_NAME)
    if not isinstance(source, dict) or source.get("docstatus") != 1:
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
        mapped["result"],
        source_document=source,
        verified_values={"warehouse": WAREHOUSE},
    )
    print("VALIDATED ERP_CREATE ARGUMENTS:")
    pprint(args)
    print("No Purchase Receipt was created or submitted.")


if __name__ == "__main__":
    main()