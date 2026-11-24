
"""
Verify that read and write tools share one registry.

No ERPNext requests are performed.
"""

from Agent.tools.register_tools import create_tool_registry


def test_write_tools_are_registered():
    registry = create_tool_registry()

    specs = {
        spec["name"]: spec
        for spec in registry.get_specs()
    }

    executors = registry.get_executors()

    expected = {
        "erp_search",
        "erp_get",
        "erp_count",
        "erp_create",
        "erp_submit",
    }

    assert expected.issubset(specs.keys())
    assert expected.issubset(executors.keys())

    for name in expected:
        assert callable(
            getattr(executors[name], "invoke", None)
        )

    assert specs["erp_create"]["parameters"] == {
        "doctype": "str",
        "data": "dict",
    }

    assert specs["erp_submit"]["parameters"] == {
        "doctype": "str",
        "name": "str",
    }