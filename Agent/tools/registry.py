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
    "Purchase Order": ["name", "supplier", "status", "transaction_date", "grand_total"],
    "Sales Order": ["name", "customer", "status", "transaction_date", "delivery_date", "grand_total"],
    "BOM": ["name", "item", "quantity", "is_active", "is_default"],
    "Work Order": ["name", "production_item", "status", "qty", "produced_qty"],
}


def render_registry_overview() -> str:
    """Eine Zeile pro DocType, wird in die Tool-Beschreibung eingefügt."""
    lines = ["Available DocTypes and their fields:"]
    for doctype, fields in AVAILABLE_DOCTYPES.items():
        lines.append(f"- {doctype}: {', '.join(fields)}")
    return "\n".join(lines)