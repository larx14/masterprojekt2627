
"""
Register executable ERPNext tools.
"""

from Agent.tools.tool_registry import ToolRegistry
from Agent.tools.read_tools import (
    get_read_tool_specs,
    run_read_tool,
)


def create_tool_registry() -> ToolRegistry:
    """
    Register all supported ERPNext read tools.
    """

    registry = ToolRegistry()

    for spec in get_read_tool_specs():
        name = spec["name"]

        def handler(args: dict, tool_name=name) -> dict:
            response = run_read_tool(tool_name, args)

            if response.get("status") != "completed":
                errors = response.get("errors") or [
                    "Tool execution failed."
                ]
                raise RuntimeError(
                    "; ".join(map(str, errors))
                )

            result = response.get("result")

            if not isinstance(result, dict):
                raise TypeError(
                    "Tool returned an invalid business result."
                )

            return result

        registry.register(
            name=name,
            specification=spec,
            handler=handler,
        )

    return registry
