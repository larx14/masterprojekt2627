
"""
Register all supported executable ERPNext tools.

The registry exposes tool specifications to the Planner
and executable adapters to the Executor.
"""

from typing import Any, Callable

from Agent.tools.tool_registry import ToolRegistry

from Agent.tools.read_tools import (
    get_read_tool_specs,
    run_read_tool,
)

from Agent.tools.erp_create import (
    get_create_tool_specs,
    run_create_tool,
)

from Agent.tools.erp_submit import (
    get_submit_tool_specs,
    run_submit_tool,
)

from Agent.tools.erp_map import (
    get_map_tool_specs,
    run_map_tool,
)


def _register_group(
    registry: ToolRegistry,
    specifications: list[dict[str, Any]],
    runner: Callable[[str, dict], dict],
) -> None:
    """
    Register tools using the shared status/result contract.
    """

    for spec in specifications:
        name = spec["name"]

        def handler(
            args: dict,
            tool_name: str = name,
        ) -> dict:
            response = runner(tool_name, args)

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


def create_tool_registry() -> ToolRegistry:
    """
    Register all supported ERPNext tools.
    """

    registry = ToolRegistry()

    _register_group(
        registry,
        get_read_tool_specs(),
        run_read_tool,
    )

    _register_group(
        registry,
        get_create_tool_specs(),
        run_create_tool,
    )

    _register_group(
        registry,
        get_submit_tool_specs(),
        run_submit_tool,
    )

    _register_group(
        registry,
        get_map_tool_specs(),
        run_map_tool,
    )

    return registry
