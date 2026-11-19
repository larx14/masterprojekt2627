"""
State fields required by the governance nodes.

LangGraph only keeps keys declared in the state schema, so
PlanningState must inherit these fields:

    class PlanningState(GovernanceFields, total=False): ...
"""

from typing import Any, TypedDict


class GovernanceFields(TypedDict, total=False):

    # Context
    process_id: str                   # process_list.id (uuid)
    scenario_id: str                  # test scenario, for ground truth
    autonomy_level: str               # "L1" | "L2" | "L3"
    trigger: str                      # "chat" | "auto"

    # Action preparer -> gate
    candidates: list[dict[str, Any]]  # one entry per sample

    # Gate -> action preparer (adaptive sampling)
    n_requested: int

    # Gate / review -> executor and log
    governance: dict[str, Any]
