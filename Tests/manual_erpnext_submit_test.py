
"""
Manual ERPNext submission integration test.

Submits an existing Material Request and verifies
its status using the ERPNext API.

Run only against a dedicated test instance.
"""

from Agent.tools.erp_submit import run_submit_tool
from Agent.tools.erpnext_client import get_doc


DOCTYPE = "Material Request"
DOCUMENT_NAME = "MAT-MR-2026-00038"


def main():
    # Verify the document before submitting.
    document = get_doc(DOCTYPE, DOCUMENT_NAME)

    if document is None:
        raise RuntimeError(
            f"Document '{DOCUMENT_NAME}' was not found."
        )

    print("BEFORE SUBMIT")
    print("Document:", document["name"])
    print("Docstatus:", document["docstatus"])
    print("Status:", document.get("status"))

    if document["docstatus"] != 0:
        raise RuntimeError(
            "The document is not in draft status. "
            "Submission has been cancelled."
        )

    # Submit the existing Material Request.
    response = run_submit_tool(
        "erp_submit",
        {
            "doctype": DOCTYPE,
            "name": DOCUMENT_NAME,
        },
    )

    print("\nSUBMIT RESPONSE:", response)

    if response.get("status") != "completed":
        raise RuntimeError(
            "Submission failed or could not be confirmed. "
            f"Response: {response}"
        )

    # Independently verify the document in ERPNext.
    submitted_document = get_doc(
        DOCTYPE,
        DOCUMENT_NAME,
    )

    if submitted_document is None:
        raise RuntimeError(
            "Submitted document could not be retrieved."
        )

    assert submitted_document["docstatus"] == 1, (
        "ERPNext did not confirm the submitted status."
    )

    print("\nAFTER SUBMIT")
    print("Document:", submitted_document["name"])
    print("Docstatus:", submitted_document["docstatus"])
    print("Status:", submitted_document.get("status"))

    print("\nSUBMISSION VERIFIED SUCCESSFULLY")


if __name__ == "__main__":
    main()
