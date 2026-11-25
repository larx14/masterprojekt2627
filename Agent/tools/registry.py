"""
Registry: welche DocTypes der Agent lesen darf, mit den Feldern,
die er sieht und filtern kann. Neuer DocType = eine Zeile.
"""

AVAILABLE_DOCTYPES: dict[str, list[str]] = {
    "Supplier": ["name", "supplier_name", "supplier_group", "country", "disabled"],
    "Customer": ["name", "customer_name", "customer_group", "territory", "disabled"],
    "Item": ["name", "item_code", "item_name", "item_group", "stock_uom", "disabled"],
    "Warehouse": ["name", "warehouse_name", "company", "disabled"],
    "Bin": ["name", "item_code", "warehouse", "actual_qty", "reserved_qty", "projected_qty"],
    "Purchase Order": ["name", "supplier", "status", "transaction_date", "grand_total", "docstatus",],
    "Sales Order": ["name", "customer", "status", "transaction_date", "delivery_date", "grand_total"],
    "BOM": ["name", "item", "quantity", "is_active", "is_default"],
    "Work Order": ["name", "production_item", "status", "qty", "produced_qty"],
    "Material Request": [ "name", "company", "material_request_type", "transaction_date", "schedule_date", "status", "docstatus", ],
    "Purchase Receipt": ["name", "supplier", "company", "posting_date", "status", "docstatus", ],
    "Purchase Invoice": ["name", "supplier", "company", "posting_date", "bill_no", "bill_date", "grand_total", "outstanding_amount", "status", "docstatus",],

"Payment Entry": [
    "name",
    "company",
    "payment_type",
    "party_type",
    "party",
    "posting_date",
    "reference_no",
    "reference_date",
    "paid_amount",
    "docstatus",
],
"Account": [
    "name",
    "account_name",
    "account_type",
    "company",
    "is_group",
    "disabled",
],

}

WRITE_DOCTYPES = {
    "Material Request",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Payment Entry",
    "Supplier",
}


def render_registry_overview() -> str:
    """Eine Zeile pro DocType, wird in die Tool-Beschreibung eingefügt."""
    lines = ["Available DocTypes and their fields:"]
    for doctype, fields in AVAILABLE_DOCTYPES.items():
        lines.append(f"- {doctype}: {', '.join(fields)}")
    return "\n".join(lines)

"""
Approved ERPNext document mapping methods.

Only explicitly registered source/target combinations
may be executed by the mapping tool.
"""

MAPPING_METHODS: dict[tuple[str, str], str] = {
    (
        "Material Request",
        "Purchase Order",
    ): (
        "erpnext.stock.doctype.material_request."
        "mapper.make_purchase_order"
    ),

    (
        "Purchase Order",
        "Purchase Receipt",
    ): (
        "erpnext.buying.doctype.purchase_order."
        "mapper.make_purchase_receipt"
    ),

    (
        "Purchase Order",
        "Purchase Invoice",
    ): (
        "erpnext.buying.doctype.purchase_order."
        "mapper.make_purchase_invoice"
    ),

    (
        "Purchase Receipt",
        "Purchase Invoice",
    ): (
        "erpnext.stock.doctype.purchase_receipt."
        "mapper.make_purchase_invoice"
    ),
}


def render_mapping_overview() -> str:
    """
    Return the available document transformations.
    """

    lines = ["Available document mappings:"]

    for source, target in MAPPING_METHODS:
        lines.append(f"- {source} -> {target}")

    return "\n".join(lines)
"""
Approved ERPNext document mapping methods.

Only explicitly registered source/target combinations
may be executed by the mapping tool.
"""

MAPPING_METHODS: dict[tuple[str, str], str] = {
    (
        "Material Request",
        "Purchase Order",
    ): (
        "erpnext.stock.doctype.material_request."
        "mapper.make_purchase_order"
    ),

    (
        "Purchase Order",
        "Purchase Receipt",
    ): (
        "erpnext.buying.doctype.purchase_order."
        "mapper.make_purchase_receipt"
    ),

    (
        "Purchase Order",
        "Purchase Invoice",
    ): (
        "erpnext.buying.doctype.purchase_order."
        "mapper.make_purchase_invoice"
    ),

    (
        "Purchase Receipt",
        "Purchase Invoice",
    ): (
        "erpnext.stock.doctype.purchase_receipt."
        "mapper.make_purchase_invoice"
    ),
}


def render_mapping_overview() -> str:
    """
    Return the available document transformations.
    """

    lines = ["Available document mappings:"]

    for source, target in MAPPING_METHODS:
        lines.append(f"- {source} -> {target}")

    return "\n".join(lines)


"""
Approved ERPNext document mapping methods.

Only explicitly registered source/target combinations
may be executed by the mapping tool.
"""

MAPPING_METHODS: dict[tuple[str, str], str] = {
    (
        "Material Request",
        "Purchase Order",
    ): (
        "erpnext.stock.doctype.material_request."
         "material_request.make_purchase_order"
    ),

    (
        "Purchase Order",
        "Purchase Receipt",
    ): (
        "erpnext.buying.doctype.purchase_order."
        "purchase_order.make_purchase_receipt"
    ),

    (
        "Purchase Order",
        "Purchase Invoice",
    ): (
        "erpnext.buying.doctype.purchase_order."
         "purchase_receipt.make_purchase_invoice"
    ),

    (
        "Purchase Receipt",
        "Purchase Invoice",
    ): (
        "erpnext.stock.doctype.purchase_receipt."
        "purchase_receipt.make_purchase_invoice"
    ),
}


def render_mapping_overview() -> str:
    """
    Return the available document transformations.
    """

    lines = ["Available document mappings:"]

    for source, target in MAPPING_METHODS:
        lines.append(f"- {source} -> {target}")

    return "\n".join(lines)

# Only approved create fields are forwarded from mapped ERPNext documents.

MAPPED_DOCUMENT_PROFILES = {
    "Purchase Order": {
        "source_doctype": "Material Request",
        "source_reference": "material_request",
        "source_item_reference": "material_request_item",
        "already_used_field": "ordered_qty",
        "header_fields": ("supplier", "company"),
        "item_fields": (
            "item_code", "qty", "schedule_date", "warehouse", "uom",
            "material_request", "material_request_item",
        ),
        "required_header_fields": ("supplier", "company"),
        "required_item_fields": (
            "item_code", "qty", "schedule_date", "material_request", "material_request_item",
        ),
    },
    "Purchase Receipt": {
        "source_doctype": "Purchase Order",
        "source_reference": "purchase_order",
        "source_item_reference": "purchase_order_item",
        "already_used_field": "received_qty",
        "header_fields": ("supplier", "company"),
        "item_fields": (
            "item_code", "qty", "rate", "warehouse", "uom",
            "purchase_order", "purchase_order_item",
        ),
        "required_header_fields": ("supplier", "company"),
        "required_item_fields": (
            "item_code", "qty", "rate", "warehouse",
            "purchase_order", "purchase_order_item",
        ),
    },
    
    "Purchase Invoice": {
        "source_doctype": "Purchase Receipt",
        "source_reference": "purchase_receipt",
        "source_item_reference": "pr_detail",
        "already_used_field": "billed_amt",
        "header_fields": ("supplier", "company", "currency"),
        "item_fields": (
            "item_code", "qty", "rate", "uom", "expense_account", "cost_center",
            "purchase_receipt", "pr_detail", "purchase_order", "po_detail",
        ),
        "required_header_fields": ("supplier", "company"),
        "required_item_fields": (
            "item_code", "qty", "rate", "purchase_receipt", "pr_detail",
        ),
        },
    "Payment Entry":{
        "source_doctype": "Purchase Invoice",
        },
        

}
PAYMENT_ENTRY_PROFILE = {
    "source_doctype": "Purchase Invoice",
    "header_fields": (
        "payment_type", "company", "party_type", "party",
        "paid_from", "paid_to", "paid_amount", "received_amount",
        "source_exchange_rate", "target_exchange_rate",
        "paid_from_account_currency", "paid_to_account_currency",
        "mode_of_payment", "posting_date", "cost_center",
    ),
    "reference_fields": (
        "reference_doctype", "reference_name", "allocated_amount", "payment_term",
    ),
}
