
"""
Unit tests for the generic Plan Validator Node.

The tests verify structural plan validation, tool references,
step dependencies, and deterministic execution conditions.

No LLM or ERPNext connection is required.
"""

from copy import deepcopy

from Agent.nodes.plan_validator_node import plan_validator


BASE_STATE = {
    "status": "planned",
    "goal": "A sales order is created.",
    "available_tools": [
        {
            "name": "find_customer",
            "result_fields": {
                "customer_exists": "bool",
                "customer_id": "str"
            }
        },
        {
            "name": "create_customer",
            "result_fields": {
                "customer_created": "bool",
                "customer_id": "str"
            }
        },
        {
            "name": "create_sales_order",
            "result_fields": {
                "sales_order_created": "bool",
                "sales_order_id": "str"
            }
        }
    ],
    "plan": [
        {
            "id": "step_1",
            "tool": "find_customer",
            "description": "Find the customer.",
            "reason": "The customer must be identified.",
            "depends_on": [],
            "execution_condition": None,
            "status": "pending"
        },
        {
            "id": "step_2",
            "tool": "create_customer",
            "description": "Create the customer if necessary.",
            "reason": "A customer record is required.",
            "depends_on": ["step_1"],
            "execution_condition": {
                "all": [
                    {
                        "source_step": "step_1",
                        "field": "customer_exists",
                        "operator": "eq",
                        "value": False
                    }
                ],
                "any": []
            },
            "status": "pending"
        },
        {
            "id": "step_3",
            "tool": "create_sales_order",
            "description": "Create the sales order.",
            "reason": "This fulfills the business instruction.",
            "depends_on": ["step_2"],
            "execution_condition": None,
            "status": "pending"
        }
    ],
    "missing_info": [],
    "abort_reason": "",
    "history": []
}


# --------------------------------------------------
# Existing structural validation tests
# --------------------------------------------------

def test_valid_plan():
    state = deepcopy(BASE_STATE)

    result = plan_validator(state)

    assert result["plan_valid"] is True
    assert result["status"] == "plan_valid"
    assert result["validation_errors"] == []


def test_unknown_tool():
    state = deepcopy(BASE_STATE)
    state["plan"][2]["tool"] = "unknown_tool"

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert result["status"] == "plan_invalid"
    assert any(
        "unknown tool" in error.lower()
        for error in result["validation_errors"]
    )


def test_duplicate_step_id():
    state = deepcopy(BASE_STATE)
    state["plan"][1]["id"] = "step_1"

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert any(
        "duplicate step id" in error.lower()
        for error in result["validation_errors"]
    )


def test_invalid_dependency():
    state = deepcopy(BASE_STATE)
    state["plan"][1]["depends_on"] = ["step_99"]

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert any(
        "unknown dependency" in error.lower()
        for error in result["validation_errors"]
    )


def test_dependency_order():
    state = deepcopy(BASE_STATE)
    state["plan"][0]["depends_on"] = ["step_2"]

    result = plan_validator(state)

    assert result["plan_valid"] is False


def test_missing_information():
    state = deepcopy(BASE_STATE)
    state["missing_info"] = ["Customer name"]

    result = plan_validator(state)

    assert result["plan_valid"] is False


def test_incomplete_planning():
    state = deepcopy(BASE_STATE)
    state["status"] = "needs_human"

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert result["status"] == "needs_human"


def test_empty_plan():
    state = deepcopy(BASE_STATE)
    state["plan"] = []

    result = plan_validator(state)

    assert result["plan_valid"] is False


# --------------------------------------------------
# New execution condition validation tests
# --------------------------------------------------

def test_unknown_condition_source():
    """
    Reject a condition referencing a nonexistent step.
    """
    state = deepcopy(BASE_STATE)

    state["plan"][1]["execution_condition"]["all"][0][
        "source_step"
    ] = "step_99"

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert any(
        "unknown condition source" in error.lower()
        for error in result["validation_errors"]
    )


def test_condition_source_not_in_dependencies():
    """
    Reject a condition referencing a step that is not
    declared as a prerequisite.
    """
    state = deepcopy(BASE_STATE)

    state["plan"][1]["depends_on"] = []

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert any(
        "must be listed in depends_on" in error.lower()
        for error in result["validation_errors"]
    )


def test_unknown_result_field():
    """
    Reject a condition referencing a result field
    that is not defined in the tool specification.
    """
    state = deepcopy(BASE_STATE)

    state["plan"][1]["execution_condition"]["all"][0][
        "field"
    ] = "unknown_field"

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert any(
        "unknown result field" in error.lower()
        for error in result["validation_errors"]
    )


def test_condition_value_type_mismatch():
    """
    Reject a comparison with an incompatible expected value.
    """
    state = deepcopy(BASE_STATE)

    state["plan"][1]["execution_condition"]["all"][0][
        "value"
    ] = "false"

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert any(
        "type mismatch" in error.lower()
        for error in result["validation_errors"]
    )


def test_invalid_condition_operator():
    """
    Reject unsupported comparison operators.
    """
    state = deepcopy(BASE_STATE)

    state["plan"][1]["execution_condition"]["all"][0][
        "operator"
    ] = "contains"

    result = plan_validator(state)

    assert result["plan_valid"] is False
    assert any(
        "invalid step" in error.lower()
        for error in result["validation_errors"]
    )
