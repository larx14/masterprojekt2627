
"""
Unit tests for deterministic conditional execution.
"""

from Agent.nodes.condition_evaluator_node import (
    evaluate_execution_condition,
    condition_evaluator,
)
from Agent.nodes.skip_step_node import skip_step


CREATE_CUSTOMER_CONDITION = {
    "all": [{
        "source_step": "step_1",
        "field": "customer_exists",
        "operator": "eq",
        "value": False
    }],
    "any": []
}


SALES_ORDER_CONDITION = {
    "all": [{
        "source_step": "step_3",
        "field": "item_exists",
        "operator": "eq",
        "value": True
    }],
    "any": [
        {
            "source_step": "step_1",
            "field": "customer_exists",
            "operator": "eq",
            "value": True
        },
        {
            "source_step": "step_2",
            "field": "customer_created",
            "operator": "eq",
            "value": True
        }
    ]
}


def result(status, **fields):
    return {
        "status": status,
        "result": fields
    }


def test_customer_exists():
    results = {
        "step_1": result(
            "completed",
            customer_exists=True
        )
    }

    assert evaluate_execution_condition(
        CREATE_CUSTOMER_CONDITION,
        results
    ) == "false"


def test_customer_does_not_exist():
    results = {
        "step_1": result(
            "completed",
            customer_exists=False
        )
    }

    assert evaluate_execution_condition(
        CREATE_CUSTOMER_CONDITION,
        results
    ) == "true"


def test_lookup_failure():
    results = {
        "step_1": result(
            "failed",
            customer_exists=False
        )
    }

    assert evaluate_execution_condition(
        CREATE_CUSTOMER_CONDITION,
        results
    ) == "unknown"


def test_missing_lookup_result():
    assert evaluate_execution_condition(
        CREATE_CUSTOMER_CONDITION,
        {}
    ) == "unknown"


def test_existing_customer_allows_sales_order():
    results = {
        "step_1": result(
            "completed",
            customer_exists=True
        ),
        "step_2": {
            "status": "skipped",
            "result": None
        },
        "step_3": result(
            "completed",
            item_exists=True
        )
    }

    assert evaluate_execution_condition(
        SALES_ORDER_CONDITION,
        results
    ) == "true"


def test_created_customer_allows_sales_order():
    results = {
        "step_1": result(
            "completed",
            customer_exists=False
        ),
        "step_2": result(
            "completed",
            customer_created=True
        ),
        "step_3": result(
            "completed",
            item_exists=True
        )
    }

    assert evaluate_execution_condition(
        SALES_ORDER_CONDITION,
        results
    ) == "true"


def test_missing_item_blocks_sales_order():
    results = {
        "step_1": result(
            "completed",
            customer_exists=True
        ),
        "step_2": {
            "status": "skipped",
            "result": None
        },
        "step_3": result(
            "completed",
            item_exists=False
        )
    }

    assert evaluate_execution_condition(
        SALES_ORDER_CONDITION,
        results
    ) == "false"


def test_unknown_customer_blocks_decision():
    results = {
        "step_1": result(
            "failed"
        ),
        "step_2": {
            "status": "skipped",
            "result": None
        },
        "step_3": result(
            "completed",
            item_exists=True
        )
    }

    assert evaluate_execution_condition(
        SALES_ORDER_CONDITION,
        results
    ) == "unknown"


def test_skip_step_updates_state():
    state = {
        "plan": [
            {
                "id": "step_2",
                "status": "pending"
            }
        ],
        "current_step": 0,
        "condition_result": "false",
        "condition_reason": "Customer already exists.",
        "step_results": {}
    }

    updated = skip_step(state)

    assert updated["plan"][0]["status"] == "skipped"
    assert updated["current_step"] == 1
    assert updated["step_results"]["step_2"]["status"] == "skipped"
    assert updated["prepared_action"] == {}


def test_condition_evaluator_blocks_unresolved_dependency():
    state = {
        "plan_valid": True,
        "current_step": 1,
        "plan": [
            {
                "id": "step_1",
                "status": "pending"
            },
            {
                "id": "step_2",
                "status": "pending",
                "depends_on": ["step_1"],
                "execution_condition": None
            }
        ],
        "step_results": {}
    }

    updated = condition_evaluator(state)

    assert updated["condition_result"] == "unknown"
    assert updated["status"] == "condition_unknown"
