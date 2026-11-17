
# Tests/mock_tools.py

MOCK_TOOLS = [
    {
        "name": "find_customer",
        "description": "Search for an existing customer",
        "parameters": {"customer_name": "str"},
        "result_fields": {
            "customer_exists": "bool",   # these fields are very important for decisions within the graph !!, e.g., if a certain customer exists upon check, 
            "customer_id": "str"            # a step that would create the same customer will be skipped 
        }
    },
    {
        "name": "create_customer",
        "description": "Create a customer record",
        "parameters": {"customer_name": "str"},
        "result_fields": {
            "customer_created": "bool", #!! 
            "customer_id": "str"
        }
    },
    {
        "name": "find_item",
        "description": "Search for an existing item",
        "parameters": {"search": "str"},
        "result_fields": {
            "item_exists": "bool",
            "item_code": "str"
        }
    },
    {
        "name": "create_sales_order",
        "description": "Create a sales order",
        "parameters": {
            "customer": "str",
            "items": "list"
        },
        "result_fields": {
            "sales_order_created": "bool",
            "sales_order_id": "str"
        }
    }
]
