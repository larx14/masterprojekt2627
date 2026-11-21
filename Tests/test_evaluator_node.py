
import sys
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from Agent.nodes.evaluator_node import evaluator


# Alle Tests verwenden einen bekannten Supplier.
identity = {"supplier_name": "Kettwig Farm"}

tests = [
    {
        "name": "Create - Dokument existiert",
        "expected_state": {
            "doctype": "Supplier",
            "identity": {"supplier_name": "Kettwig Farm"},
            "expected_fields": {"supplier_name": "Kettwig Farm"},
            "expected_exists": True
        },
        "expected_result": "verification_success"
    },
    {
        "name": "Update - Feld wurde geändert",
        "expected_state": {
            "doctype": "Supplier",
            "identity": {"name": "Kettwig Farm"},
            "expected_fields": {"supplier_name": "Kettwig Farm Updated"},
            "expected_exists": True
        },
        "expected_result": "verification_success"
    },
    {
        "name": "Delete - Dokument existiert nicht mehr",
        "expected_state": {
            "doctype": "Supplier",
            "identity": {"supplier_name": "EVALUATOR_TEST_NOT_EXISTS"},
            "expected_exists": False
        },
        "expected_result": "verification_success"
    },
]


for test in tests:
    result = evaluator({
        "expected_state": test["expected_state"]
    })

    actual = result["status"]
    expected = test["expected_result"]

    print(f"\n{test['name']}")
    print(f"Erwartet: {expected}")
    print(f"Erhalten: {actual}")
    print("PASS" if actual == expected else "FAIL")
