"""
LangGraph node: governance gate.

Runs after the action preparer and before the executor.
Deterministic, no LLM call. Clusters the sampled candidates,
computes the confidence, classifies the risk, checks hard
rules and decides according to the autonomy level.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig

from Governance import decision_log
from Governance.confidence import score
from Governance.config import get_config
from Governance.fingerprint import INVALID, MISSING
from Governance.policy import decide
from Governance.risk import classify_risk
from Governance.rules import check_rules, describe_hits


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _action(candidate: dict[str, Any], step_id: str | None) -> dict[str, Any]:
    """Shape of prepared_action as the executor expects it."""
    return {
        "step_id": step_id,
        "tool": candidate.get("tool"),
        "args": candidate.get("args", {}),
        "reason": candidate.get("reason", ""),
        "confidence": candidate.get("confidence"),
    }


def governance_gate(
    state: dict[str, Any],
    config: RunnableConfig | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict:
    """
    config: LangGraph RunnableConfig (passed automatically, holds thread_id).
    cfg:    governance configuration (defaults to config.yaml).
    """

    cfg = cfg or get_config()
    thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
    candidates = state.get("candidates") or []

    plan = state.get("plan", [])
    current = state.get("current_step", 0)
    step = plan[current] if isinstance(current, int) and 0 <= current < len(plan) else {}
    step_id = step.get("id")

    if not candidates:
        return {
            "prepared_action": {},
            "status": "governance_error",
            "history": [{
                "event": "governance_error",
                "step_id": step_id,
                "reason": "No candidates to evaluate.",
                "timestamp": _now(),
            }],
        }

    scored = score(candidates, cfg.get("ignore_fields", []))
    representative = scored["representative"]

    tool_spec = next(
        (t for t in state.get("available_tools", [])
         if isinstance(t, dict) and t.get("name") == representative.get("tool")),
        {"name": representative.get("tool")},
    )

    risk = classify_risk(tool_spec, representative.get("args", {}))
    rule_hits = check_rules(representative, risk, state.get("facts", {}), cfg.get("rules", {}))
    rule_details = describe_hits(rule_hits, representative, state.get("facts", {}), cfg.get("rules", {}))
    level = state.get("autonomy_level") or cfg["default_autonomy_level"]

    decision, reason, threshold = decide(scored, risk, rule_hits, level, cfg)

    # Adaptive sampling: ask the preparer for more candidates.
    if decision == "more_samples":
        return {
            "n_requested": int(cfg["sampling"]["n_max"]) - scored["n"],
            "status": "sampling",
            "history": [{
                "event": "governance_more_samples",
                "step_id": step_id,
                "n": scored["n"],
                "conf_consistency": scored["conf_consistency"],
                "reason": reason,
                "timestamp": _now(),
            }],
        }

    chosen = _action(representative, step_id)
    options = [
        {
            "index": i,
            "key": c["key"],
            "executable": c["key"] not in (MISSING, INVALID),
            "votes": f"{c['count']}/{scored['n']}",
            "action": _action(c["representative"], step_id),
            "missing_info": c["representative"].get("missing_info", []),
        }
        for i, c in enumerate(scored["clusters"][: int(cfg.get("max_options", 3))])
    ]

    record = decision_log.to_json({
        "process_id": state.get("process_id"),
        "thread_id": thread_id,
        "scenario_id": state.get("scenario_id"),
        "step_id": step_id,
        "tool": representative.get("tool"),
        "risk": risk,
        "autonomy_level": level,
        "trigger": state.get("trigger"),
        "n_samples": scored["n"],
        "distribution": scored["distribution"],
        "conf_consistency": scored["conf_consistency"],
        "conf_verbal": scored["conf_verbal"],
        "threshold": threshold,
        "rule_hits": rule_hits,
        "decision": decision,
        "reason": reason,
        "chosen_action": chosen,
        "final_action": chosen if decision == "auto" else None,
    })

    # The decision itself must not fail because of the log.
    try:
        log_id, log_error = decision_log.write(record), None
    except Exception as exc:
        log_id, log_error = None, f"{type(exc).__name__}: {exc}"

    missing = representative.get("missing_info", []) if decision == "needs_human" else []

    return {
        "prepared_action": chosen if decision == "auto" else {},
        "governance": {
            **record,
            "log_id": log_id,
            "log_error": log_error,
            "proposal": chosen,
            "options": options,
            "step_description": step.get("description"),
            "rule_details": rule_details,
        },
        "missing_info": missing,
        "n_requested": 0,
        "status": decision,
        "history": [{"event": "governance_decision", **record,
                     "log_id": log_id, "log_error": log_error, "timestamp": _now()}],
    }


def route_after_governance(
    state: dict[str, Any]
) -> Literal["sample", "execute", "review", "stop"]:

    status = state.get("status")

    if status == "sampling":
        return "sample"
    if status == "auto":
        return "execute"
    if status in ("escalate", "needs_human"):
        return "review"
    return "stop"
