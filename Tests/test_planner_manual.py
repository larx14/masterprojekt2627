
"""
Manual integration test for the generic Planner Node.
"""

import json

from Agent.nodes.planner_node import planner


state = {
    "instruction": (
        "Create a new customer named Example GmbH "
        "and prepare a sales order for 5 units of Item A."
    ),
    "available_tools": [
        {
            "name": "find_customer",
            "description": "Search for an existing customer",
            "parameters": {
                "customer_name": "str"
            }
        },
        {
            "name": "create_customer",
            "description": "Create a new customer record",
            "parameters": {
                "customer_name": "str"
            }
        },
        {
            "name": "find_item",
            "description": "Search for an existing item",
            "parameters": {
                "search": "str"
            }
        },
        {
            "name": "create_sales_order",
            "description": "Create a sales order",
            "parameters": {
                "customer": "str",
                "items": "list"
            }
        }
    ],
    "history": []
}


result = planner(state)


print("\nSTATUS:")
print(result["status"])

print("\nGOAL:")
print(result["goal"])

print("\nPROPOSED STEPS:")
print(json.dumps(
    result["proposed_steps"],
    indent=2,
    ensure_ascii=False
))

print("\nPLAN:")
print(json.dumps(
    result["plan"],
    indent=2,
    ensure_ascii=False
))

print("\nPLAN VALID:")
print(result["plan_valid"])

print("\nMISSING INFORMATION:")
print(result["missing_info"])

print("\nABORT REASON:")
print(result["abort_reason"])

print("\nDECISION LOG:")
print(json.dumps(
    result["history"],
    indent=2,
    ensure_ascii=False
))
