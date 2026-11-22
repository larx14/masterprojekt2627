
"""
Central registry for executable ERPNext tools.
"""

from typing import Callable, Any


class ToolAdapter:
    """
    Adapt a Python function to the Executor's invoke interface.
    """

    def __init__(
        self,
        handler: Callable[[dict], dict]
    ):
        self.handler = handler

    def invoke(self, args: dict) -> dict:
        return self.handler(args)


class ToolRegistry:
    """
    Manage executable tools and their specifications.
    """

    def __init__(self):
        self._executors = {}
        self._specifications = {}

    def register(
        self,
        name: str,
        specification: dict,
        handler: Callable[[dict], dict],
    ):
        if name in self._executors:
            raise ValueError(
                f"Tool '{name}' is already registered."
            )

        if specification.get("name") != name:
            raise ValueError(
                "Tool specification name does not match."
            )

        self._executors[name] = ToolAdapter(handler)
        self._specifications[name] = specification.copy()

    def get_executors(self) -> dict:
        return self._executors.copy()

    def get_specs(self) -> list[dict]:
        return [
            spec.copy()
            for spec in self._specifications.values()
        ]
