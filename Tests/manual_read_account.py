"""Verify read access to the ERPNext bank GL account."""

from pprint import pprint

from Agent.tools.read_tools import run_read_tool


def main() -> None:
    result = run_read_tool(
        "erp_search",
        {
            "doctype": "Account",
            "filters": [
                ["name", "=", "1810 - Bank 1 - MP"],
                ["company", "=", "Masterprojekt"],
                ["is_group", "=", 0],
                ["disabled", "=", 0],
            ],
        },
    )

    pprint(result)

    assert result["status"] == "completed", (
        "Account search failed."
    )

    assert result["result"]["found"] is True, (
        "Bank account was not found."
    )

    account = result["result"]["data"][0]

    assert account["account_type"] in {"Bank", "Cash"}, (
        "Account is not a bank or cash GL account."
    )

    print("ACCOUNT VERIFICATION PASSED")


if __name__ == "__main__":
    main()